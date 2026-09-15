# Frontend

Streamlit chat UI + backend API for the Retrieval Agent. The backend's `/chat`
endpoint calls the agent graph directly (`src/agents/graph.py:run`).

Dependencies (`fastapi`, `uvicorn`, `streamlit`, `requests`) are managed by
the root project's `pyproject.toml`/`uv.lock` (the `frontend` dependency
group), not separate virtualenvs — `uv run` from either directory uses the
same project `.venv`. The `requirements.txt` files are kept for anyone
who'd rather `pip install` into their own environment instead.

## Run the backend

```bash
cd frontend/backend
uv run uvicorn main:app --reload --port 8000
```

## Run the Streamlit app

```bash
cd frontend/streamlit_app
uv run streamlit run app.py
```

By default the Streamlit app talks to `http://localhost:8000`. Override
with the `BACKEND_URL` env var if the backend runs elsewhere.
