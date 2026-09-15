# Retrieval Agent

## Summary

`retrieval_agent` is a Retrieval-Augmented Generation (RAG) chatbot that answers questions about the company using its handbook. The handbook content comes from a real source (the [GitLab handbook](https://gitlab.com/gitlab-com/content-sites/handbook)) but every mention of the real org name is replaced with a fictional one, **Wall-E Waste Solutions**, before it's indexed — see [Data note](#data-note).

It's an *agentic* RAG design rather than a fixed retrieve-then-answer pipeline:

1. **`query_rewriter`** — an LLM call that rewrites the latest message into a standalone, unambiguous question using conversation history. This is what lets a follow-up like "can you get it for Germany?" (after "what's the leave policy?") resolve correctly instead of being searched literally.
2. **`retrieval_agent`** — an LLM bound to a `search_handbook` tool. It decides for itself whether to search, what to search for, and whether to search again (e.g. to cover a multi-part question, or retry after an unhelpful result), looping through the `tools` node until it has enough information.
3. **`finalize_answer`** — extracts the model's final text answer once it stops calling the tool.

Search itself is **hybrid** (BM25 keyword + vector similarity, blended), running against a [Weaviate](https://weaviate.io/) collection populated by backfilling and embedding the handbook content.

## Setup

### 1. Prerequisites

- [uv](https://docs.astral.sh/uv/) and Python 3.13 (`uv sync` installs everything in `pyproject.toml`)
- Docker, for running Weaviate locally
- An Anthropic API key (the agent's LLM calls go through `AnthropicStore`/`LLMRepository`)

### 2. Environment variables

Add these to `.env` at the repo root:

```bash
# LLM
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Weaviate — local instance (matches docker-compose.yml's defaults)
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080
WEAVIATE_GRPC_PORT=50051

# Weaviate — OR use a Weaviate Cloud cluster instead of the local one:
# WEAVIATE_URL=https://your-cluster.weaviate.network
# WEAVIATE_API_KEY=your_weaviate_api_key
```

`src/store/weaviate.py` connects to Weaviate Cloud if `WEAVIATE_URL` is set, otherwise to the local instance via the `WEAVIATE_HOST`/`WEAVIATE_PORT`/`WEAVIATE_GRPC_PORT` vars (defaulting to `localhost`/`8080`/`50051` if unset).

### 3. Start Weaviate

`docker-compose.yml` defines a `weaviate` service paired with a `t2v-transformers` inference container (the `sentence-transformers/all-MiniLM-L6-v2` model), so embeddings are generated locally with no external embedding API needed:

```bash
docker compose up -d weaviate t2v-transformers
```

Confirm it's up and the `text2vec-transformers` module is enabled:

```bash
curl -s http://localhost:8080/v1/meta | grep text2vec-transformers
```

### 4. Backfill the handbook into Weaviate

```bash
uv run newbie backfill-gitlab
```

This clones (or updates) the handbook repo, parses every markdown file into heading-keyed sections, filters out noisy/boilerplate sections (empty stubs, "placeholder page" auto-generated pages, shortcode-only content), replaces the real org name with **Wall-E Waste Solutions**, then drops and recreates the `gitlab` Weaviate collection from scratch and bulk-inserts everything with a `text2vec-transformers` vectorizer attached. Each run is a full, clean reload — safe to re-run any time the handbook source or the processing logic changes.

### 5. Try retrieval directly (optional sanity check)

```bash
uv run newbie retrieve-docs "what is the leave policy" --limit 5 --alpha 0.5
```

`--alpha` blends keyword vs. vector search (`0` = pure BM25, `1` = pure vector, `0.5` = balanced).

### 6. Run the agent

**Via LangGraph Studio** — the graph is already registered in `langgraph.json` as `retrieval_agent`:

```bash
uv run langgraph dev
```

**Or programmatically**, with a checkpointer so multi-turn conversation (and `query_rewriter`'s disambiguation) works across calls:

```python
from langgraph.checkpoint.memory import MemorySaver
from src.agents.graph import build_graph

graph = build_graph(checkpointer=MemorySaver())
config = {"configurable": {"thread_id": "demo"}}

result = graph.invoke({"user_input": "What is the leave policy?"}, config=config)
print(result["evaluation"])

result = graph.invoke({"user_input": "can you get it for Germany?"}, config=config)
print(result["evaluation"])
```

## Data note

The handbook is a real public document, but this project isn't meant to represent the real company. `src/backfill/synthesizer.py` replaces every case-insensitive occurrence of "gitlab" — in page paths, frontmatter metadata, headings, and body text alike — with **Wall-E Waste Solutions** before anything is indexed. So the agent's answers describe "Wall-E Waste Solutions" policies, not GitLab's. This also means links/URLs/file-name-like strings that originally contained "gitlab" become nonsensical after the substitution — a known, accepted side effect of an org-wide-and-total replacement.

## Key files

| File | Role |
| --- | --- |
| `src/agents/graph.py` | Builds/compiles the StateGraph (`query_rewriter` → `retrieval_agent` ↔ `tools` → `finalize_answer`); also exposes `run(AgentInput) -> AgentOutput` for single-turn callers (e.g. the backend API) |
| `src/agents/nodes.py` | The three node functions |
| `src/agents/tools.py` | `search_handbook`, wrapping the retriever as a single-arg tool |
| `src/models/retrieval_state.py` | `RetrievalState` (graph state) |
| `src/prompts/retrieval_prompts.py` | System/rewriter prompt strings |
| `src/retriever/retrieve_docs.py` | Hybrid-search retrieval function used by the tool |
| `src/store/weaviate.py` | `WeaviateStore` — thin wrapper over the Weaviate client |
| `src/backfill/backfill_gitlab.py` | Downloads, parses, filters, and backfills the handbook |
| `src/backfill/synthesizer.py` | Replaces the real org name with the fictional one |
