# Newbie

A minimal LangGraph project containing the Retrieval Agent, spun out of `lang-graph-learn` so it has its own project and dependency set.

## Setup

```bash
uv sync
```

## Retrieval Agent (RAG over the company handbook)

A Weaviate-backed, agentic RAG chatbot that answers questions about the (fictionalized) company handbook. See [`docs/retrieval_agent.md`](docs/retrieval_agent.md) for the full setup (Weaviate via `docker-compose.yml`, required env vars, backfill/retrieval CLI commands) and an explanation of how it works.

## CLI

The `newbie` CLI (registered in `pyproject.toml`, entry point `src/cli/main.py`) wraps the backfill and retrieval commands:

```bash
# Download the GitLab handbook and backfill it into Weaviate
uv run newbie backfill-gitlab
uv run newbie backfill-gitlab --collection my_collection

# Run a hybrid (BM25 + vector) search against a backfilled collection
uv run newbie retrieve-docs "what is the leave policy"
uv run newbie retrieve-docs "what is the leave policy" --collection my_collection --limit 5 --alpha 0.5

# See all commands/options
uv run newbie --help
uv run newbie backfill-gitlab --help
uv run newbie retrieve-docs --help
```

`backfill-gitlab` requires Weaviate to be reachable (see `docker-compose.yml` for a local instance, or set `WEAVIATE_URL`/`WEAVIATE_API_KEY` in `.env` for Weaviate Cloud) — see [`docs/retrieval_agent.md`](docs/retrieval_agent.md) for full setup details.

## Frontend (Streamlit chat UI + backend API)

A chat frontend lives in `frontend/` — a Streamlit app (role selection + chat box) talking to a FastAPI backend, which calls the agent graph directly via `src/agents/graph.py:run`. See [`frontend/README.md`](frontend/README.md) for details.

Run the backend API:

```bash
cd frontend/backend
uv run uvicorn main:app --reload --port 8000
```

Run the Streamlit app (in a separate terminal):

```bash
cd frontend/streamlit_app
uv run streamlit run app.py
```

Open http://localhost:8501 in your browser. The Streamlit app talks to `http://localhost:8000` by default; set the `BACKEND_URL` env var to point it elsewhere.

## LangGraph Studio

To inspect and debug the graph visually in [LangGraph Studio](https://langchain-ai.github.io/langgraph/cloud/how-tos/studio/quick_start/):

```bash
uv run langgraph dev
```

This starts a local API server (generating a `.langgraph_api/` cache directory) and opens LangGraph Studio in your browser, connected to it. `langgraph.json` at the repo root registers the graph as `retrieval_agent`.
