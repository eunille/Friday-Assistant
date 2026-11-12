"""Centralized logging for Friday."""
import logging
import logging.handlers
import os
from friday.core.config import get as cfg
from friday.core.paths import resolve


def setup_logger(name="friday"):
    """Create and configure the Friday logger."""
    log_level = cfg("system", "log_level") or "INFO"
    log_file = str(resolve(cfg("system", "log_file") or "logs/friday.log"))

    # Ensure log directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Avoid duplicate handlers on reload
    if logger.handlers:
        return logger

    # File handler — detailed
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(file_handler)

    # Console handler — minimal (won't conflict with TUI when TUI is active)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console_handler)

    return logger


# Module-level convenience
log = setup_logger()
