"""Node functions for the retrieval agent (company handbook Q&A) graph.

Nodes:
    query_rewriter   -- disambiguates the latest message into a standalone
                        question, using conversation history, and adds it to
                        `state.messages` as a HumanMessage
    retrieval_agent  -- decides when to call the `search_handbook` tool and
                        answers using what it returns
    finalize_answer  -- extracts the agent's final answer once it stops
                        calling tools

The graph itself (StateGraph assembly, compilation) lives in `graph.py`
alongside this module. The `search_handbook` tool lives in `tools.py`.
"""

import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, filter_messages

from src.agents.tools import search_handbook
from src.dto.agent_io import AgentOutput
from src.models.retrieval_state import RetrievalState
from src.prompts.retrieval_prompts import QUERY_REWRITER_PROMPT, RETRIEVAL_AGENT_SYSTEM_PROMPT
from src.repository.llm_repository import LLMRepository

llm_repository = LLMRepository()

retrieval_agent_llm = llm_repository.get_model().bind_tools([search_handbook])

# Matches the "(Source: <path>)" citations RETRIEVAL_AGENT_SYSTEM_PROMPT asks
# the model to inline in its answer, echoing a <document path="..."> tag's
# path attribute (`search_handbook` in tools.py), itself taken straight from
# the record's `path` property.
_INLINE_CITATION = re.compile(r"Source:\s*([^)\n]+)\)?")


def _conversation_history(messages: list, limit: int = 6) -> list:
    """Clean Human/AI turns from prior state.messages, as real message objects.

    Tool-call AIMessages and ToolMessages are dropped rather than passed
    through as-is: an AIMessage with tool_calls that isn't immediately
    followed by its matching ToolMessage is invalid input to Anthropic's API,
    and this helper's output gets appended to, not interleaved with, other
    history. Content is normalized to plain text and rebuilt as fresh
    messages of the same role.
    """
    history = []
    for message in filter_messages(messages, include_types=[HumanMessage, AIMessage])[-limit:]:
        text = llm_repository.as_text(message.content).strip()
        if text:
            history.append(type(message)(content=text))
    return history


def query_rewriter(state: RetrievalState) -> dict:
    history = _conversation_history(state.messages)
    if not history:
        return {"messages": [HumanMessage(content=state.user_input)]}
    messages = [
        SystemMessage(content=QUERY_REWRITER_PROMPT),
        *history,
        HumanMessage(content=f"Latest message: {state.user_input}"),
    ]
    rewritten = llm_repository.invoke(messages).strip()
    return {"messages": [HumanMessage(content=rewritten)]}


def retrieval_agent(state: RetrievalState) -> dict:
    response = retrieval_agent_llm.invoke([SystemMessage(content=RETRIEVAL_AGENT_SYSTEM_PROMPT)] + state.messages)
    return {"messages": [response]}


def finalize_answer(state: RetrievalState) -> AgentOutput:
    answer = llm_repository.as_text(state.messages[-1].content).strip()
    citations = list(dict.fromkeys(path.strip() for path in _INLINE_CITATION.findall(answer)))
    return AgentOutput(evaluation=answer, citations=citations)
