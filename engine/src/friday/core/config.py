"""Load config.yaml and provide access to its settings."""
import os
import yaml

from friday.core.paths import CONFIG_FILE

_CONFIG = None
_CONFIG_PATH = str(CONFIG_FILE)

_DEFAULTS = {
    "assistant": {
        "name": "Friday",
        "wake_word": "hey_jarvis",
        "personality": "iron_man",
    },
    "stt": {
        "model": "base",
        "language": "en",
        "vad_filter": True,
        "beam_size": 1,
        "silence_timeout": 2.0,
    },
    "tts": {
        "voice": "en_US-ryan-medium.onnx",
        "speed": 1.0,
    },
    "wake_word": {
        "engine": "openwakeword",
        "sensitivity": 0.5,
    },
    "llm": {
        "engine": "ollama",
        "model": "phi3:mini",
    },
    "system": {
        "log_level": "INFO",
        "log_file": "logs/friday.log",
        "audio_device": None,
    },
}


def _deep_merge(defaults, overrides):
    """Merge overrides into defaults (non-mutating)."""
    result = dict(defaults)
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path=None):
    """Load config.yaml and merge with defaults. Cached after first call."""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    config_path = path or _CONFIG_PATH
    user_config = {}

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            user_config = yaml.safe_load(f) or {}

    _CONFIG = _deep_merge(_DEFAULTS, user_config)
    return _CONFIG


def get(section, key=None):
    """Get a config value. Examples: get('stt', 'model'), get('tts')."""
    config = load_config()
    section_data = config.get(section, {})
    if key is None:
        return section_data
    return section_data.get(key)
