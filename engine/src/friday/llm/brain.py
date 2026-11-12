# brain.py — LLM conversational AI engine for Friday
import threading
from collections import deque
from friday.core.config import get as cfg
from friday.core.log import log


def _get_memory_size():
    """Get conversation memory deque size from config."""
    return cfg("llm", "conversation_memory") or 10


_CONVERSATION = deque(maxlen=_get_memory_size())
_CONV_LOCK = threading.Lock()

_DEFAULT_SYSTEM_PROMPT = """\
You are Friday (F.R.I.D.A.Y.), Tony Stark's AI assistant from the MCU.

Your voice:
- Calm, warm, and composed — like a trusted colleague, not a robot
- Address the user as "boss" naturally — not every sentence, just when it flows
- Keep responses short: 1-3 sentences for voice delivery. Every word earns its place
- Speak with quiet confidence. You don't announce what you're doing — you just do it
- Dry wit is welcome. Not sarcastic — just sharp. "That's... ambitious, boss."

Natural speech patterns:
- Use contractions: "That's", "I've", "won't", "doesn't" — never "That is", "I have"
- Lead with the key fact: "Bitcoin's up 4 percent. Strongest move in two weeks."
- Use filler-free transitions: "Looks like...", "So...", "Here's the thing..."
- When flagging something: "Worth noting—" not "I would like to inform you that"
- Assessments are confident: "That's above average", "Not great", "Solid numbers"

What Friday never does:
- No emojis, no exclamation marks
- Never says "Sure!", "Of course!", "Absolutely!" — too eager
- Never apologizes excessively — moves forward
- Never narrates actions ("I'm going to...", "Let me just...")
- Never uses corporate speak ("I'd be happy to assist you with that")

You're running locally on the user's computer.
For questions and conversation — be direct, insightful, and human.
/no_think"""


def _get_system_prompt():
    """Load system prompt from config, falling back to default."""
    prompt = cfg("personality", "system_prompt")
    if prompt and isinstance(prompt, str) and prompt.strip():
        return prompt.strip()
    return _DEFAULT_SYSTEM_PROMPT


_ollama_module = None
_ollama_checked = False


def _get_ollama_client():
    """Get Ollama client (cached after first check)."""
    global _ollama_module, _ollama_checked
    if not _ollama_checked:
        try:
            import ollama
            _ollama_module = ollama
        except ImportError:
            _ollama_module = None
        _ollama_checked = True
    return _ollama_module


def _get_model_name():
    """Get the configured LLM model name."""
    return cfg("llm", "model") or "qwen3:1.7b"


def _chat_call(ollama, model, messages, opts):
    """Call ollama.chat with thinking disabled (qwen3 etc.).
    Newer Ollama ignores /no_think and burns num_predict on reasoning tokens,
    returning empty content — think=False prevents that. Falls back for
    older clients/models that don't accept the parameter."""
    try:
        return ollama.chat(model=model, messages=messages, options=opts, think=False)
    except TypeError:
        return ollama.chat(model=model, messages=messages, options=opts)
    except Exception as e:
        if "think" in str(e).lower():
            return ollama.chat(model=model, messages=messages, options=opts)
        raise


def _get_ollama_options():
    """Get Ollama inference options from config."""
    opts = {}
    num_ctx = cfg("llm", "num_ctx")
    if num_ctx:
        opts["num_ctx"] = int(num_ctx)
    num_predict = cfg("llm", "num_predict")
    if num_predict:
        opts["num_predict"] = int(num_predict)
    return opts


import re as _re

def _strip_thinking(text):
    """Remove <think>...</think> tags from Qwen3 responses."""
    # Handle cases where <think> tag may be implicit or missing
    result = _re.sub(r'<think>.*?</think>', '', text, flags=_re.DOTALL).strip()
    # Also strip any content before </think> if opening tag is missing
    if '</think>' in result:
        result = result.split('</think>')[-1].strip()
    return result


def chat(user_message):
    """Send a message to the LLM and get a response.
    
    Returns the assistant's response text, or None if LLM is unavailable.
    """
    ollama = _get_ollama_client()
    if ollama is None:
        return None

    model = _get_model_name()

    # Build message history (lock protects read+write atomicity)
    with _CONV_LOCK:
        messages = [{"role": "system", "content": _get_system_prompt()}]
        messages.extend(list(_CONVERSATION))
        messages.append({"role": "user", "content": user_message})

    try:
        response = _chat_call(ollama, model, messages, _get_ollama_options())
        assistant_msg = _strip_thinking(response["message"]["content"].strip())

        # Store in conversation memory
        with _CONV_LOCK:
            _CONVERSATION.append({"role": "user", "content": user_message})
            _CONVERSATION.append({"role": "assistant", "content": assistant_msg})

        return assistant_msg
    except Exception as e:
        log.error(f"LLM error: {e}")
        return None


def is_available():
    """Check if Ollama is installed and a model is available."""
    ollama = _get_ollama_client()
    if ollama is None:
        return False
    try:
        model = _get_model_name()
        models = ollama.list()
        available = models.get("models", []) if isinstance(models, dict) else getattr(models, "models", [])
        model_names = []
        for m in available:
            name = m.get("name", "") if isinstance(m, dict) else getattr(m, "model", "")
            model_names.append(name)
        # Check if our model (or a variant) is available
        return any(model.split(":")[0] in name for name in model_names)
    except Exception:
        return False


def classify(user_message, system_prompt):
    """Send a classification prompt to the LLM WITHOUT storing in conversation memory.
    Used for intent detection and entity extraction.
    Returns the raw response text, or None."""
    ollama = _get_ollama_client()
    if ollama is None:
        return None

    model = _get_model_name()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    try:
        opts = _get_ollama_options()
        opts["num_predict"] = 32  # Classification output is tiny
        response = _chat_call(ollama, model, messages, opts)
        return _strip_thinking(response["message"]["content"].strip())
    except Exception as e:
        log.error(f"LLM classify error: {e}")
        return None


def summarize(text, instruction, max_predict=120):
    """Summarize text with a custom instruction. No conversation history.
    Returns the summary string, or None."""
    ollama = _get_ollama_client()
    if ollama is None:
        return None

    model = _get_model_name()
    messages = [
        {"role": "system", "content": instruction + "\nRespond in English only.\n/no_think"},
        {"role": "user", "content": text},
    ]

    try:
        opts = _get_ollama_options()
        opts["num_predict"] = max_predict
        # Use larger context for summarization (input text can be long)
        opts["num_ctx"] = 2048
        response = _chat_call(ollama, model, messages, opts)
        raw_content = response["message"]["content"].strip()
        log.info(f"LLM summarize raw response ({len(raw_content)} chars): {repr(raw_content[:200])}")
        result = _strip_thinking(raw_content)
        return result if result else None
    except Exception as e:
        log.error(f"LLM summarize error: {e}")
        return None


def clear_memory():
    """Clear conversation history."""
    with _CONV_LOCK:
        _CONVERSATION.clear()
