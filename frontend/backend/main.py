"""Backend API for the Retrieval Agent chat frontend.

Receives chat questions from the Streamlit app and forwards them to the
retrieval agent graph (`src/agents/graph.py`) via its `run` function.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agents.graph import run as run_agent
from src.dto.agent_io import AgentInput

app = FastAPI(title="Retrieval Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_ROLES = {"employee", "ceo", "hr"}


class ChatRequest(BaseModel):
    role: str
    message: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[str] = []


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    role = request.role.lower()
    if role not in VALID_ROLES:
        return ChatResponse(
            answer=f"Unknown role '{request.role}'. Expected one of {sorted(VALID_ROLES)}."
        )

    # TODO: the agent graph doesn't take `role` yet (AgentInput is just
    # `user_input`), so it isn't used to tailor retrieval/answers. Wire it
    # through once the graph/state support it.
    result = run_agent(AgentInput(user_input=request.message))
    return ChatResponse(answer=result.evaluation, citations=result.citations)
