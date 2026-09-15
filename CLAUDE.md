# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Newbie is a Weaviate-backed, agentic RAG chatbot (`retrieval_agent`) that answers questions about a (fictionalized) company handbook. Built with LangGraph; exposed via a CLI, a FastAPI backend, and a Streamlit chat UI. See `docs/retrieval_agent.md` for the full walkthrough (setup, env vars, how the agent works, data note about the fictionalized org name).

## Commands

```bash
# Install dependencies
uv sync

# Start Weaviate + the local embedding model (required before backfill/retrieval)
docker compose up -d weaviate t2v-transformers

# Backfill the handbook into Weaviate (full clean reload every run)
uv run newbie backfill-gitlab
uv run newbie backfill-gitlab --collection my_collection

# Run a hybrid (BM25 + vector) search directly against a collection
uv run newbie retrieve-docs "what is the leave policy"
uv run newbie retrieve-docs "what is the leave policy" --collection my_collection --limit 5 --alpha 0.5

# Inspect/debug the graph visually
uv run langgraph dev

# Run the tests
uv run pytest
uv run pytest path/to/test_file.py::test_name   # single test

# Run the frontend (two terminals)
cd frontend/backend && uv run uvicorn main:app --reload --port 8000
cd frontend/streamlit_app && uv run streamlit run app.py
```

There is no dedicated lint/format command configured yet (`pre-commit` is a dependency but `.pre-commit-config.yaml` doesn't exist in the repo).

## Architecture

### Agent graph (`src/agents/`)

The retrieval agent is a LangGraph `StateGraph` over `RetrievalState` (`src/models/retrieval_state.py`), registered in `langgraph.json` as `retrieval_agent` and compiled in `src/agents/graph.py`. Flow: `query_rewriter` → `retrieval_agent` ↔ `tools` → `finalize_answer`.

- **`query_rewriter`** (`nodes.py`) — LLM call that rewrites the latest user message into a standalone question using recent conversation history (via `_clean_conversation_history`), so follow-ups like "can you get it for Germany?" resolve correctly instead of being searched literally.
- **`retrieval_agent`** (`nodes.py`, built by `build_retrieval_agent()`) — an LLM bound to two tools: `search_handbook` (real retrieval) and `SubmitAnswer` (`src/models/submit_answer.py`, a schema-only tool used to force a structured final answer instead of free text). The model loops through the `tools` node on its own, deciding whether/what to search, until it calls `SubmitAnswer`.
- **`route_after_retrieval_agent`** (`nodes.py`) — conditional edge: routes to `"tools"` if the model called `search_handbook`, otherwise to `"finalize_answer"`. The system prompt (`src/prompts/retrieval_prompts.py`) instructs the model never to call both tools in the same turn, since `ToolNode` only knows about `search_handbook` and errors on an unrecognized tool call.
- **`finalize_answer`** (`nodes.py`) — reads `answer`/`citations` out of the `SubmitAnswer` tool call args; falls back to the last message's plain text if the model didn't call it.

`src/dto/agent_io.py` defines `AgentInput`/`AgentOutput`, the graph's public input/output schema (`StateGraph(..., input_schema=AgentInput, output_schema=AgentOutput)`), deliberately narrower than the internal `RetrievalState`. `graph.py` also exposes `run(AgentInput) -> AgentOutput` for single-turn callers (e.g. the backend API); it attaches no checkpointer, so multi-turn conversations (needed for `query_rewriter` to do anything useful) require calling `build_graph(checkpointer=...)` directly with a `thread_id`.

### LLM access (`src/repository/`, `src/store/`)

Callers never talk to a provider SDK directly — they go through `LLMRepository` (`src/repository/llm_repository.py`), which delegates to `AnthropicStore` (`src/store/anthropic_store.py`). This indirection is what lets the underlying provider change without touching graph/node code.

### Retrieval (`src/retriever/`, `src/store/weaviate.py`)

`retrieve_docs()` wraps `WeaviateStore.hybrid_search` (BM25 + vector, blended via `alpha`). `WeaviateStore` auto-connects to Weaviate Cloud if `WEAVIATE_URL` is set, otherwise to a local instance via `WEAVIATE_HOST`/`WEAVIATE_PORT`/`WEAVIATE_GRPC_PORT`. Note the `weaviate-client` version is pinned (see comments in `weaviate.py`) due to a `grpcio` conflict with `langgraph-api` — don't bump it casually.

### Backfill (`src/backfill/`)

`backfill_gitlab_handbook` clones/parses the GitLab handbook, filters noisy sections, then `synthesizer.py` replaces every case-insensitive "gitlab" occurrence with the fictional org name ("Wall-E Waste Solutions") before the content is embedded and bulk-inserted into Weaviate. Every backfill run drops and recreates the collection from scratch — it's not incremental.

### Frontend (`frontend/`)

A FastAPI backend calls `src/agents/graph.py:run` directly (no HTTP hop to a separately-deployed agent service); a Streamlit app is the chat UI on top of that backend. Both share the root project's `.venv`/`pyproject.toml` (the `frontend` dependency group) rather than having their own virtualenvs.

## Code style rules

These are strict and apply to all code in this repository, not just new code you're asked to touch:

- **No magic numbers.** Any numeric or string literal with non-obvious meaning must be a named constant (module-level `UPPER_SNAKE_CASE` or a function parameter with a default), not an inline literal buried in logic.
- **Clean Code naming.** Names must say what they hold or do, be pronounceable, and avoid abbreviations/disinformation — a variable's name should make a comment explaining it unnecessary. Prefer intention-revealing names (`retry_limit`, not `n` or `tmp`).
- **Avoid deep/long if-else chains.** Prefer early returns, guard clauses, dict/lookup-table dispatch, or polymorphism over cascading `if/elif/else`. If you find yourself writing more than 2-3 branches, look for a structural alternative before adding another `elif`.
- **Single Responsibility Principle.** Each function/class should have one reason to change. If a function is doing two things (e.g. fetching data *and* formatting it, or validating *and* persisting), split it. This project's existing pattern of thin node functions and single-purpose repository/store classes is the model to follow.
