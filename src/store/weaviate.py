"""Thin wrapper around the Weaviate client for basic vector-store operations.

Connection settings are read from environment variables (see .env):
    WEAVIATE_URL      Cloud cluster URL. If set, connects to Weaviate Cloud
                       and WEAVIATE_API_KEY is required.
    WEAVIATE_API_KEY   API key for Weaviate Cloud (required with WEAVIATE_URL).
    WEAVIATE_HOST      Local instance host (default: localhost).
    WEAVIATE_PORT      Local instance REST port (default: 8080).
    WEAVIATE_GRPC_PORT Local instance gRPC port (default: 50051).
"""

import os
import uuid as uuid_module

import weaviate
from dotenv import load_dotenv
from weaviate.auth import Auth
from weaviate.classes.config import Configure, DataType, Property
from weaviate.collections.classes.config import _CollectionConfigCreate
from weaviate.collections.classes.internal import QueryReturn

load_dotenv()

# Mapping from simple type names to Weaviate property types, so callers can
# describe a schema with plain strings instead of importing DataType.
_PROPERTY_TYPES = {
    "text": DataType.TEXT,
    "int": DataType.INT,
    "number": DataType.NUMBER,
    "bool": DataType.BOOL,
    "date": DataType.DATE,
}

# Supported values for `create_collection`'s `vectorizer` argument.
# "text2vec-transformers" requires the self-hosted t2v-transformers container
# (see docker-compose.yml) and only works against a local Weaviate instance.
# "text2vec-weaviate" is Weaviate's own hosted embedding service, available
# on Weaviate Cloud with no extra API key.
_VECTORIZERS = {
    "text2vec-transformers": Configure.Vectors.text2vec_transformers,
    "text2vec-weaviate": Configure.Vectors.text2vec_weaviate,
}


def _connect_to_cloud() -> weaviate.WeaviateClient:
    """Connect to Weaviate Cloud using WEAVIATE_URL / WEAVIATE_API_KEY."""
    return weaviate.connect_to_weaviate_cloud(
        cluster_url=os.environ["WEAVIATE_URL"],
        auth_credentials=Auth.api_key(os.environ["WEAVIATE_API_KEY"]),
    )


def _connect_to_local() -> weaviate.WeaviateClient:
    """Connect to a local Weaviate instance using WEAVIATE_HOST / _PORT / _GRPC_PORT."""
    return weaviate.connect_to_local(
        host=os.environ.get("WEAVIATE_HOST", "localhost"),
        port=int(os.environ.get("WEAVIATE_PORT", "8080")),
        grpc_port=int(os.environ.get("WEAVIATE_GRPC_PORT", "50051")),
    )


def default_vectorizer() -> str:
    """Pick the vectorizer matching whichever instance `_connect` will use:
    "text2vec-weaviate" for Weaviate Cloud (WEAVIATE_URL set), otherwise
    "text2vec-transformers" for the local docker-compose instance."""
    return "text2vec-weaviate" if os.environ.get("WEAVIATE_URL") else "text2vec-transformers"


def default_vector_index_type() -> str | None:
    """Pick the vector index type matching whichever instance `_connect` will
    use. Some Weaviate Cloud clusters only allow the "hfresh" index type,
    which isn't in this project's pinned weaviate-client's typed
    Configure.VectorIndex helpers (client 4.16.2 predates it) — upgrading
    the client isn't possible here since every version above 4.16.2 requires
    grpcio<1.80, conflicting with langgraph-api's grpcio>=1.81,<1.82 pin. So
    `create_collection` accepts this as a raw string and injects it directly
    into the collection config dict. Local instances use the client's
    default ("hnsw"), so this returns None there.
    """
    return "hfresh" if os.environ.get("WEAVIATE_URL") else None


def _connect() -> weaviate.WeaviateClient:
    """Open a new connection to Weaviate, local or cloud depending on env vars."""
    if os.environ.get("WEAVIATE_URL"):
        return _connect_to_cloud()
    return _connect_to_local()


class WeaviateStore:
    """Basic CRUD-style operations against a Weaviate instance."""

    def __init__(self, client: weaviate.WeaviateClient | None = None) -> None:
        self._client = client if client is not None else _connect()

    @classmethod
    def connect_to_cloud(cls) -> "WeaviateStore":
        """Explicitly connect to Weaviate Cloud (WEAVIATE_URL / WEAVIATE_API_KEY),
        regardless of what `_connect`'s local/cloud auto-detection would pick."""
        return cls(client=_connect_to_cloud())

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "WeaviateStore":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def is_ready(self) -> bool:
        return self._client.is_ready()

    def collection_exists(self, name: str) -> bool:
        return self._client.collections.exists(name)

    def create_collection(
        self,
        name: str,
        properties: dict[str, str],
        vectorizer: str | None = None,
        vector_index_type: str | None = None,
    ) -> None:
        """Create a collection with the given properties.

        `properties` maps property name to a simple type name: one of
        "text", "int", "number", "bool", "date". `vectorizer`, if given, must
        be one of `_VECTORIZERS` and enables semantic search via
        `semantic_search`; leave it as None for a collection with no
        vectors, searchable only via `search_records`.

        `vector_index_type`, if given (e.g. "hfresh"), overrides the vector
        index type Weaviate picks by default ("hnsw"). See
        `default_vector_index_type` for why this is a raw string rather than
        one of `weaviate.classes.config.Configure.VectorIndex`'s typed
        options.
        """
        vector_config = _VECTORIZERS[vectorizer]() if vectorizer else None
        config = _CollectionConfigCreate(
            name=name,
            properties=[
                Property(name=prop_name, data_type=_PROPERTY_TYPES[prop_type])
                for prop_name, prop_type in properties.items()
            ],
            vector_config=vector_config,
        )
        config_dict = config._to_dict()
        if vector_index_type:
            for vector_settings in config_dict["vectorConfig"].values():
                vector_settings["vectorIndexType"] = vector_index_type
        self._client.collections._create_from_dict(config_dict)

    def delete_collection(self, name: str) -> None:
        self._client.collections.delete(name)

    def add_record(self, collection_name: str, properties: dict, vector: list[float] | None = None) -> str:
        """Insert a record into a collection and return its UUID."""
        collection = self._client.collections.get(collection_name)
        record_id = collection.data.insert(properties=properties, vector=vector)
        return str(record_id)

    def add_records(self, collection_name: str, records: list[dict], chunk_size: int = 200) -> int:
        """Bulk-insert records into a collection. Returns the number of failed inserts.

        Uses `insert_many` in chunks rather than the client's `batch.dynamic()`
        context manager, which fetches the collection's full config first —
        something this project's pinned weaviate-client version can't parse
        for collections using the "hfresh" vector index (see
        `default_vector_index_type`); `insert_many` skips that round-trip.
        """
        collection = self._client.collections.get(collection_name)
        failed = 0
        for start in range(0, len(records), chunk_size):
            chunk = records[start : start + chunk_size]
            result = collection.data.insert_many(chunk)
            failed += len(result.errors)
        return failed

    def search_records(self, collection_name: str, query: str, limit: int = 10) -> list[dict]:
        """Keyword (BM25) search for records matching `query`."""
        collection = self._client.collections.get(collection_name)
        response: QueryReturn = collection.query.bm25(query=query, limit=limit)
        return [
            {"uuid": str(obj.uuid), "properties": obj.properties} for obj in response.objects
        ]

    def semantic_search(self, collection_name: str, query: str, limit: int = 10) -> list[dict]:
        """Semantic (near-text) search for records matching `query`.

        Only works on a collection created with a `vectorizer` (see
        `create_collection`); otherwise there are no vectors to search over.
        """
        collection = self._client.collections.get(collection_name)
        response: QueryReturn = collection.query.near_text(query=query, limit=limit)
        return [
            {"uuid": str(obj.uuid), "properties": obj.properties} for obj in response.objects
        ]

    def hybrid_search(
        self, collection_name: str, query: str, limit: int = 10, alpha: float = 0.5
    ) -> list[dict]:
        """Hybrid (BM25 + vector) search for records matching `query`.

        `alpha` weights keyword vs. vector search, 0-1: 0 is pure BM25, 1 is
        pure vector search. Only works on a collection created with a
        `vectorizer` (see `create_collection`); otherwise there are no
        vectors to search over.
        """
        collection = self._client.collections.get(collection_name)
        response: QueryReturn = collection.query.hybrid(
            query=query, alpha=alpha, limit=limit, return_metadata=["score"]
        )
        return [
            {"uuid": str(obj.uuid), "properties": obj.properties, "score": obj.metadata.score}
            for obj in response.objects
        ]

    def delete_record(self, collection_name: str, record_id: str | uuid_module.UUID) -> bool:
        """Delete a record by UUID. Returns True if a record was deleted."""
        collection = self._client.collections.get(collection_name)
        return collection.data.delete_by_id(record_id)
