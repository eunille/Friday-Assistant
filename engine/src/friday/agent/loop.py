"""The agent: the model decides which tools to call, then answers for voice."""
import json
from collections import deque

from friday.core.log import log
from friday.llm.base import LLMError

SYSTEM_PROMPT = """\
You are Friday, a voice assistant running on the user's own computer. Your replies are \
spoken aloud, so answer in one to three short sentences of plain speech: no lists, no \
markdown, no emojis, no URLs read out. Address the user as "boss" now and then.

You have tools. Use them when the user asks for something current, factual or something \
to be done on the computer; do not guess facts you could look up. When a tool gives you \
data, pick out what matters and say what stands out rather than reading it all. If a tool \
fails or the user declines an action, say so plainly and stop. If a search finds nothing, \
try one different wording at most, then say you couldn't find it. Never ask for or repeat \
passwords.
"""

WRAP_UP = ("You are out of steps. Do not call any more tools. Answer now in one or two "
           "sentences using what you have found; if it isn't enough, say what you did find.")
STEP_LIMIT_REPLY ="That took more steps than I allow myself, boss. I stopped before finishing."
NO_MODEL_REPLY = "I can't reach a model right now, boss."


class Agent:
    def __init__(self, model, registry, approvals=None, system_prompt=SYSTEM_PROMPT,
                 max_steps=6, memory_turns=6, max_tokens=700, on_event=None):
        self._model = model
        self._registry = registry
        self._approvals = approvals
        self._system = system_prompt
        self._max_steps = max_steps
        self._max_tokens = max_tokens
        self._history = deque(maxlen=memory_turns * 2)  # user/assistant pairs only
        self._emit = on_event or (lambda event: None)

    def clear(self):
        self._history.clear()

    def run(self, user_text) -> str:
        """One spoken turn: returns what Friday should say."""
        messages = [{"role": "system", "content": self._system},
                    *self._history,
                    {"role": "user", "content": user_text}]
        tools = self._registry.schemas()

        reply = STEP_LIMIT_REPLY
        for step in range(self._max_steps):
            last_step = step == self._max_steps - 1
            if last_step and step > 0:
                # Out of steps: no more tools, answer from what was gathered.
                messages.append({"role": "user", "content": WRAP_UP})
            try:
                result = self._model.chat(messages, tools=None if last_step and step > 0 else tools,
                                          max_tokens=self._max_tokens)
            except LLMError as e:
                log.error(f"Agent model error: {e}")
                return NO_MODEL_REPLY

            if not result.tool_calls:
                reply = result.content or ("Done, boss." if not last_step else STEP_LIMIT_REPLY)
                break
            if last_step:
                break

            messages.append({
                "role": "assistant", "content": result.content or "",
                "tool_calls": [{"id": c.id, "type": "function",
                                "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                               for c in result.tool_calls],
            })
            for call in result.tool_calls:
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": self._run_tool(call)})

        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": reply})
        return reply

    def _run_tool(self, call) -> str:
        tool = self._registry.get(call.name)
        if tool is not None and tool.risk != "read":
            question = f"{tool.description.rstrip('.')}: {json.dumps(call.arguments)}. Go ahead?"
            self._emit({"type": "approval", "tool": call.name, "arguments": call.arguments})
            if self._approvals is None or not self._approvals.ask(question, key=call.name):
                self._emit({"type": "tool_declined", "tool": call.name})
                return "The user declined this action. Do not try it again."

        self._emit({"type": "tool_start", "tool": call.name, "arguments": call.arguments})
        output = self._registry.call(call.name, call.arguments)
        self._emit({"type": "tool_end", "tool": call.name, "ok": not output.startswith("Error:")})
        return output
