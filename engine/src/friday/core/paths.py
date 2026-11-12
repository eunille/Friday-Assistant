"""Where Friday keeps its files.

Everything that touches the disk (config, logs, downloaded models) resolves
through here, so there is one place to change when the app is packaged.

Set FRIDAY_HOME to move the whole lot somewhere else.
"""
import os
from pathlib import Path

# engine/src/friday/core/paths.py -> engine/
_ENGINE_DIR = Path(__file__).resolve().parents[3]

HOME = Path(os.environ.get("FRIDAY_HOME") or _ENGINE_DIR)
CONFIG_FILE = Path(os.environ.get("FRIDAY_CONFIG") or HOME / "config.yaml")
MODELS_DIR = HOME / "models"
LOGS_DIR = HOME / "logs"


def resolve(path):
    """Return an absolute path; relative ones are taken from HOME."""
    p = Path(path)
    return p if p.is_absolute() else HOME / p
