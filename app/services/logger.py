"""logger.py — Structured logger for Finance Coach."""
import logging
import json
from datetime import datetime


class StructuredLogger:
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)

    def _log(self, level: str, event: str, **kwargs):
        entry = {"ts": datetime.utcnow().isoformat(), "level": level, "event": event, **kwargs}
        getattr(self._logger, level)(json.dumps(entry))

    def info(self, event: str, **kwargs): self._log("info", event, **kwargs)
    def warning(self, event: str, **kwargs): self._log("warning", event, **kwargs)
    def error(self, event: str, **kwargs): self._log("error", event, **kwargs)


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)
