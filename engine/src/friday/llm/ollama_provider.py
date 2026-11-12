"""A local model through Ollama, with tool calling."""
import re

from friday.core.log import log
from friday.llm.base import ChatResult, LLMError, ToolCall

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_thinking(text):
    text = _THINK.sub("", text or "")
    if "</think>" in text:
        text = text.split("</think>")[-1]
    return text.strip()


class OllamaLocal:
    name = "local"

    def __init__(self, model, num_ctx=4096, client=None):
        self.model = model
        self._num_ctx = num_ctx
        self._client = client  # anything with .chat() and .list(); defaults to the ollama module

    def _ollama(self):
        if self._client is None:
            import ollama
            self._client = ollama
        return self._client

    def available(self) -> bool:
        try:
            listed = self._ollama().list()
            models = listed.get("models", []) if isinstance(listed, dict) else getattr(listed, "models", [])
            names = [(m.get("name") or m.get("model", "")) if isinstance(m, dict) else getattr(m, "model", "")
                     for m in models]
            # Exact model and tag: qwen3:1.7b being installed does not make qwen3:4b available.
            wanted = self.model if ":" in self.model else f"{self.model}:latest"
            return wanted in names
        except Exception:
            return False

    def chat(self, messages, tools=None, max_tokens=None) -> ChatResult:
        options = {"num_ctx": self._num_ctx}
        if max_tokens:
            options["num_predict"] = max_tokens
        kwargs = {"model": self.model, "messages": _to_ollama(messages), "options": options}
        if tools:
            kwargs["tools"] = tools
        try:
            try:
                # think=False stops qwen3 spending its token budget on reasoning.
                response = self._ollama().chat(think=False, **kwargs)
            except TypeError:
                response = self._ollama().chat(**kwargs)
        except Exception as e:
            log.error(f"Ollama error: {e}")
            raise LLMError(f"The local model failed: {e}") from e

        message = response["message"]
        calls = []
        for i, call in enumerate(message.get("tool_calls") or []):
            fn = call["function"]
            calls.append(ToolCall(id=f"call_{i}", name=fn["name"], arguments=dict(fn.get("arguments") or {})))
        return ChatResult(content=_strip_thinking(message.get("content")), tool_calls=calls, model=self.model)


def _to_ollama(messages):
    """OpenAI-format history -> Ollama's (tool arguments are dicts, not JSON text)."""
    import json
    out = []
    for m in messages:
        m = dict(m)
        if m.get("tool_calls"):
            m["tool_calls"] = [
                {"function": {"name": c["function"]["name"],
                              "arguments": json.loads(c["function"]["arguments"])
                              if isinstance(c["function"]["arguments"], str) else c["function"]["arguments"]}}
                for c in m["tool_calls"]
            ]
        m.pop("tool_call_id", None)
        out.append(m)
    return out
