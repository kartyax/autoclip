import logging
import json
import sys
from pathlib import Path

from .progress import ProgressEmitter


class StructuredLogger:
    """Structured logger that emits JSON logs"""

    def __init__(self, level: str = "INFO"):
        self.logger = logging.getLogger("autoclip")
        self.logger.setLevel(getattr(logging, level.upper()))

        # Remove default handlers
        self.logger.handlers.clear()

        # Add our custom handler
        handler = JSONLogHandler()
        handler.setLevel(self.logger.level)
        self.logger.addHandler(handler)

    def get_logger(self):
        return self.logger


class JSONLogHandler(logging.Handler):
    """Custom handler that emits JSON logs"""

    def emit(self, record):
        try:
            # Format the message
            message = self.format(record)

            # Emit via progress emitter
            ProgressEmitter.emit_log(
                level=record.levelname,
                message=message,
                logger=record.name,
                function=record.funcName,
                line=record.lineno
            )
        except Exception:
            self.handleError(record)