"""Retrieve documents from Weaviate via hybrid (BM25 + vector) search."""

from src.backfill.backfill_gitlab import GITLAB_COLLECTION
from src.store.weaviate import WeaviateStore


def retrieve_docs(
    query: str,
    collection_name: str = GITLAB_COLLECTION,
    limit: int = 5,
    alpha: float = 0.5,
) -> list[dict]:
    """Retrieve documents matching `query` via hybrid (BM25 + vector) search.

    Parameters:
    query (str): The text to search for.
    collection_name (str): Weaviate collection to search. Defaults to the
        GitLab handbook collection.
    limit (int): Maximum number of documents to return.
    alpha (float): Weighting between keyword and vector search, 0-1.
        0 is pure BM25, 1 is pure vector search.

    Returns:
    list[dict]: Each item has `uuid`, `properties` (the record's stored
        fields, e.g. `path`/`title`/`heading`/`content`), and `score` (the
        hybrid relevance score from Weaviate).
    """
    with WeaviateStore() as store:
        return store.hybrid_search(collection_name, query, limit=limit, alpha=alpha)
