import logging
import os
import sys
from pathlib import Path

_LOGGING_CONFIGURED = False


def configure_logging():
    """
    Console logging works everywhere (local, Docker, Azure Log Stream).
    Optional file logging only when LOG_TO_FILE=1.
    """
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_to_file = os.getenv("LOG_TO_FILE", "0") == "1"
    log_dir = os.getenv("LOG_DIR", "")

    handlers: list[logging.Handler] = []

    # 1) Console handler (always)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    handlers.append(console)

    # 2) Optional file handler (local dev)
    if log_to_file:
        if not log_dir:
            # default to ./logs relative to project root
            log_dir = str(Path(__file__).resolve().parents[1] / "logs")

        Path(log_dir).mkdir(parents=True, exist_ok=True)
        file_path = Path(log_dir) / "app.log"

        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(log_level)
        handlers.append(file_handler)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    for h in handlers:
        h.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(log_level)

    # Avoid duplicate handlers if Django/Gunicorn configures logging too
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)

    _LOGGING_CONFIGURED = True