from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, filter_messages

from src.agents.tools import search_handbook
from src.dto.agent_io import AgentOutput
from src.models.retrieval_state import RetrievalState
from src.models.submit_answer import SubmitAnswer
from src.prompts.retrieval_prompts import QUERY_REWRITER_PROMPT, RETRIEVAL_AGENT_SYSTEM_PROMPT
from src.repository.llm_repository import LLMRepository

llm_repository = LLMRepository()


def _clean_conversation_history(messages: list, limit: int = 6) -> list:
    """Clean Human/AI turns from prior state.messages, as real message objects.
    """
    history = []
    for message in filter_messages(messages, include_types=[HumanMessage, AIMessage])[-limit:]:
        text = llm_repository.as_text(message.content).strip()
        if text:
            history.append(type(message)(content=text))
    return history


def query_rewriter(state: RetrievalState) -> dict:
    history = _clean_conversation_history(state.messages)
    if not history:
        return {"messages": [HumanMessage(content=state.user_input)]}
    messages = [
        SystemMessage(content=QUERY_REWRITER_PROMPT),
        *history,
        HumanMessage(content=f"Latest message: {state.user_input}"),
    ]
    rewritten = llm_repository.invoke(messages).strip()
    return {"messages": [HumanMessage(content=rewritten)]}


def build_retrieval_agent():
    retrieval_agent_llm = llm_repository.get_model().bind_tools([search_handbook, SubmitAnswer])

    def retrieval_agent(state: RetrievalState) -> dict:
        response = retrieval_agent_llm.invoke([SystemMessage(content=RETRIEVAL_AGENT_SYSTEM_PROMPT)] + state.messages)
        return {"messages": [response]}

    return retrieval_agent


def _last_message(state: RetrievalState) -> BaseMessage:
    return next(reversed(state.messages))


def route_after_retrieval_agent(state: RetrievalState) -> str:
    tool_calls = getattr(_last_message(state), "tool_calls", None) or []
    if any(call["name"] == "search_handbook" for call in tool_calls):
        return "tools"
    return "finalize_answer"


def finalize_answer(state: RetrievalState) -> AgentOutput:
    last_message = _last_message(state)
    tool_calls = getattr(last_message, "tool_calls", None) or []
    submission = next((call["args"] for call in tool_calls if call["name"] == "SubmitAnswer"), None)
    if submission is not None:
        return AgentOutput(evaluation=submission["answer"], citations=submission.get("citations", []))
    return AgentOutput(evaluation=llm_repository.as_text(last_message.content).strip())
