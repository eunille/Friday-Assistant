"""Tools the agent can call.

A tool is a plain function that returns data (text). It never speaks; the
agent decides what to say. `risk` decides whether the user is asked first:
  read   - never asks
  write  - asks (sending, signing in, changing something)
"""
import json
from dataclasses import dataclass
from typing import Callable

from friday.core.log import log

MAX_RESULT_CHARS = 4000


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema for the arguments
    fn: Callable[..., object]
    risk: str = "read"

    def schema(self) -> dict:
        return {"type": "function",
                "function": {"name": self.name, "description": self.description,
                             "parameters": self.parameters}}


class Registry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def tool(self, name, description, parameters=None, risk="read"):
        """Decorator form of register()."""
        def wrap(fn):
            self.register(Tool(name, description,
                               parameters or {"type": "object", "properties": {}}, fn, risk))
            return fn
        return wrap

    def get(self, name) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    def call(self, name, arguments) -> str:
        """Run a tool and return its result as text. Never raises."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: there is no tool called {name}."
        try:
            result = tool.fn(**(arguments or {}))
        except TypeError as e:
            return f"Error: wrong arguments for {name}: {e}"
        except Exception as e:
            log.error(f"Tool {name} failed: {e}", exc_info=True)
            return f"Error: {name} failed: {e}"
        if result is None:
            return "Done."
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        return text[:MAX_RESULT_CHARS]
