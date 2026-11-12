"""OpenRouter, free models only.

Rules this module enforces:
  * A model is only ever called if OpenRouter lists its prompt and completion
    price as zero. There is no code path that calls a paid model.
  * When a model is rate-limited, out of quota, gone or overloaded, the next
    free model is tried and the failed one rests for a cool-down period.
"""
import json
import time

import httpx

from friday.core.log import log
from friday.llm.base import ChatResult, LLMError, NoModelAvailable, ToolCall

BASE_URL = "https://openrouter.ai/api/v1"

# Tried in this order when present in the live free list; the rest follow.
DEFAULT_PREFERENCE = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-lightning:free",
    "thinkingmachines/inkling-2-small:free",
    "recursive/flint-v1.0:free",
]

# Statuses that mean "this model can't answer right now, another might".
_SKIP_STATUSES = {402, 404, 408, 429, 500, 502, 503, 504, 529}
# Statuses that mean "no model will answer until the user fixes something".
_FATAL_STATUSES = {401, 403}


def is_free(model: dict) -> bool:
    """True only if both prices are present and exactly zero."""
    pricing = model.get("pricing") or {}
    try:
        return float(pricing["prompt"]) == 0.0 and float(pricing["completion"]) == 0.0
    except (KeyError, TypeError, ValueError):
        return False


def supports_tools(model: dict) -> bool:
    return "tools" in (model.get("supported_parameters") or [])


class OpenRouterFree:
    name = "openrouter"

    def __init__(self, api_key, preference=None, cooldown_seconds=60.0,
                 list_ttl_seconds=3600.0, client=None, clock=time.monotonic):
        self._key = api_key
        self._preference = list(preference or DEFAULT_PREFERENCE)
        self._cooldown = cooldown_seconds
        self._list_ttl = list_ttl_seconds
        self._client = client or httpx.Client(timeout=60.0)
        self._clock = clock
        self._free_ids: list[str] = []
        self._listed_at: float | None = None
        self._resting: dict[str, float] = {}  # model id -> time it may be tried again
        self.last_model = ""

    def available(self) -> bool:
        return bool(self._key)

    # -- model list ---------------------------------------------------------

    def free_models(self) -> list[str]:
        """Free, tool-capable model ids in the order they will be tried."""
        now = self._clock()
        if self._listed_at is None or now - self._listed_at > self._list_ttl:
            self._refresh()
        return list(self._free_ids)

    def _refresh(self):
        try:
            response = self._client.get(f"{BASE_URL}/models")
            response.raise_for_status()
            models = response.json()["data"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            if self._free_ids:
                log.warning(f"OpenRouter model list refresh failed, keeping old list: {e}")
                return
            raise LLMError(f"Could not fetch OpenRouter's model list: {e}") from e

        ids = [m["id"] for m in models if is_free(m) and supports_tools(m)]
        preferred = [m for m in self._preference if m in ids]
        self._free_ids = preferred + [m for m in ids if m not in preferred]
        self._listed_at = self._clock()
        log.info(f"OpenRouter free tool-capable models: {len(self._free_ids)}")

    def _candidates(self) -> list[str]:
        now = self._clock()
        free = self.free_models()
        rested = [m for m in free if self._resting.get(m, 0.0) <= now]
        if rested or not free:
            return rested
        # Every free model is resting (a burst of rate limits). Limits are often
        # per-minute, so give the one that has rested longest one more try.
        return [min(free, key=lambda m: self._resting.get(m, 0.0))]

    def _rest(self, model, reason):
        self._resting[model] = self._clock() + self._cooldown
        log.warning(f"OpenRouter: {model} unavailable ({reason}); trying the next free model")

    # -- chat ---------------------------------------------------------------

    def chat(self, messages, tools=None, max_tokens=None) -> ChatResult:
        if not self._key:
            raise LLMError("No OpenRouter key. Put OPENROUTER=... in .env")

        tried = []
        for model in self._candidates():
            # Guard: never send a request for a model outside the free list.
            if model not in self._free_ids:
                continue
            tried.append(model)
            payload = {"model": model, "messages": messages}
            if tools:
                payload["tools"] = tools
            if max_tokens:
                payload["max_tokens"] = max_tokens

            try:
                response = self._client.post(
                    f"{BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {self._key}", "X-Title": "Friday"},
                    json=payload,
                )
            except httpx.HTTPError as e:
                self._rest(model, f"network: {e}")
                continue

            if response.status_code in _FATAL_STATUSES:
                raise LLMError(f"OpenRouter refused the key (HTTP {response.status_code}).")
            if response.status_code in _SKIP_STATUSES:
                self._rest(model, f"HTTP {response.status_code}")
                continue
            if response.status_code >= 400:
                self._rest(model, f"HTTP {response.status_code}: {response.text[:120]}")
                continue

            try:
                body = response.json()
            except ValueError:
                self._rest(model, "unreadable reply")
                continue
            # OpenRouter can report an upstream failure inside a 200 reply.
            if body.get("error") or not body.get("choices"):
                self._rest(model, f"error in reply: {str(body.get('error'))[:120]}")
                continue

            result = _parse(body, model)
            if not result.content and not result.tool_calls:
                # Typically a reasoning model that used its whole budget thinking.
                # Not a limit, so no cool-down: just ask the next model this time.
                log.warning(f"OpenRouter: {model} returned an empty reply; trying the next free model")
                continue
            self.last_model = model
            return result

        if not tried:
            raise NoModelAvailable("OpenRouter lists no free model that can use tools right now.")
        raise NoModelAvailable(f"No free OpenRouter model answered (tried {len(tried)}).")


def _parse(body, model) -> ChatResult:
    message = body["choices"][0].get("message") or {}
    calls = []
    for i, call in enumerate(message.get("tool_calls") or []):
        fn = call.get("function") or {}
        raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (ValueError, TypeError):
            args = {}
        calls.append(ToolCall(id=call.get("id") or f"call_{i}", name=fn.get("name", ""), arguments=args))
    return ChatResult(content=(message.get("content") or "").strip(), tool_calls=calls, model=model)
