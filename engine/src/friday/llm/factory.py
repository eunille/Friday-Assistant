"""Pick the model source from settings: a local model, or OpenRouter's free ones."""
from friday.core.config import get as cfg
from friday.core.log import log
from friday.core.secrets import secret
from friday.llm.base import LLMError, NoModelAvailable
from friday.llm.ollama_provider import OllamaLocal
from friday.llm.openrouter import OpenRouterFree

_providers = None


def _build():
    llm = cfg("llm") or {}
    router_cfg = llm.get("openrouter") or {}
    local = OllamaLocal(model=llm.get("agent_model") or llm.get("model") or "qwen3:4b",
                        num_ctx=int(llm.get("agent_num_ctx") or 4096))
    remote = OpenRouterFree(api_key=secret("OPENROUTER"),
                            preference=router_cfg.get("prefer"),
                            cooldown_seconds=float(router_cfg.get("cooldown_seconds") or 60))
    return {"local": local, "openrouter": remote}


def providers():
    global _providers
    if _providers is None:
        _providers = _build()
    return _providers


class ModelSource:
    """The configured source first; the other one as a fallback when allowed."""

    name = "auto"

    def __init__(self, primary, fallback=None):
        self.primary = primary
        self.fallback = fallback
        self.last_model = ""

    def available(self):
        return self.primary.available() or bool(self.fallback and self.fallback.available())

    def chat(self, messages, tools=None, max_tokens=None):
        order = [p for p in (self.primary, self.fallback) if p is not None and p.available()]
        if not order:
            raise NoModelAvailable("No model source is set up.")
        last_error = None
        for provider in order:
            try:
                result = provider.chat(messages, tools=tools, max_tokens=max_tokens)
                self.last_model = result.model
                return result
            except LLMError as e:
                last_error = e
                log.warning(f"{provider.name} model source failed: {e}")
        raise last_error


def get_model_source():
    """llm.source: 'openrouter' (free models, local as backup) or 'local' (never leaves the PC)."""
    source = (cfg("llm", "source") or "local").lower()
    p = providers()
    if source == "openrouter":
        return ModelSource(p["openrouter"], fallback=p["local"])
    return ModelSource(p["local"])
