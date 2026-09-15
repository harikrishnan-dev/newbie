"""Thin wrapper around the Anthropic chat model API.

This is the only place in the project that talks to `langchain_anthropic`
directly. Anything that needs an LLM call should go through
`src/repository/llm_repository.py` instead of importing this module.
"""

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5"


class AnthropicStore:
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._llm = ChatAnthropic(model=model)

    def invoke(self, messages: list[BaseMessage]) -> str:
        response = self._llm.invoke(messages)
        return self.as_text(response.content)

    def get_model(self) -> BaseChatModel:
        return self._llm

    @staticmethod
    def as_text(content: str | list) -> str:
        """Normalize AIMessage.content: Anthropic can return either a plain
        string or a list of content blocks (e.g. text/thinking/citation
        blocks) depending on the response."""
        if isinstance(content, str):
            return content
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block) for block in content
        )
