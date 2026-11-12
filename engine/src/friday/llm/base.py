"""What every model provider looks like to the rest of Friday."""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""


class LLMError(Exception):
    """A model call failed and trying again with the same provider won't help."""


class NoModelAvailable(LLMError):
    """Every candidate model was tried and none answered."""


class Provider(Protocol):
    name: str

    def available(self) -> bool:
        """True if this provider can be used right now."""

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             max_tokens: int | None = None) -> ChatResult:
        """Send OpenAI-format messages (and tool schemas); return the reply."""
