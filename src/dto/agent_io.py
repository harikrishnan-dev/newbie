"""Public input/output contract for the agent graph.

These are deliberately narrower than the internal `QueryState` (see
`src/models/query_state.py`): they're what a caller of `graph.invoke(...)`
should send and expect back, regardless of how many internal fields the
pipeline uses along the way.
"""

from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    """What the graph accepts: the user's question, nothing else."""

    user_input: str


class AgentOutput(BaseModel):
    """What the graph returns: a human-readable answer plus its sources."""

    evaluation: str
    citations: list[str] = Field(default_factory=list)
