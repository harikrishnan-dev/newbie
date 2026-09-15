"""Builds and compiles the retrieval agent (company handbook Q&A) graph.

Node logic lives in `nodes.py`; this module wires those functions into a
StateGraph via a `build_graph` factory and exposes the module-level `graph`
that `langgraph.json` points at.
"""

from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from src.agents.nodes import build_retrieval_agent, finalize_answer, query_rewriter, route_after_retrieval_agent
from src.agents.tools import search_handbook
from src.dto.agent_io import AgentInput, AgentOutput
from src.models.retrieval_state import RetrievalState


def build_graph(checkpointer: Optional[BaseCheckpointSaver] = None) -> CompiledStateGraph:
    builder = StateGraph[RetrievalState, None, AgentInput, AgentOutput](
        RetrievalState, input_schema=AgentInput, output_schema=AgentOutput
    )
    builder.add_node("query_rewriter", query_rewriter)
    builder.add_node("retrieval_agent", build_retrieval_agent())
    builder.add_node("tools", ToolNode([search_handbook]))
    builder.add_node("finalize_answer", finalize_answer)

    builder.add_edge(START, "query_rewriter")
    builder.add_edge("query_rewriter", "retrieval_agent")
    builder.add_conditional_edges(
        "retrieval_agent", route_after_retrieval_agent, {"tools": "tools", "finalize_answer": "finalize_answer"}
    )
    builder.add_edge("tools", "retrieval_agent")
    builder.add_edge("finalize_answer", END)

    return builder.compile(checkpointer=checkpointer)


# `graph` is what langgraph.json points at. The LangGraph API/Studio platform
# manages checkpointing itself, so this instance must NOT have a custom
# checkpointer attached (the platform ignores/warns about it otherwise).
graph = build_graph()


def run(request: AgentInput) -> AgentOutput:
    """Invoke the graph with a single request and return its answer.

    No checkpointer is attached, so each call is a standalone turn with no
    memory of prior questions (`query_rewriter`'s disambiguation needs prior
    turns in `state.messages` to do anything useful across calls) — callers
    that need multi-turn conversations should build their own graph via
    `build_graph(checkpointer=...)` and invoke with a `thread_id` instead.
    """
    result = graph.invoke(request.model_dump())
    return AgentOutput(**result)
