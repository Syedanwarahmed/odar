import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            data.update(record.extra_data)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def setup_logging(log_dir: str, level: str = "INFO") -> None:
    os.makedirs(log_dir, exist_ok=True)
    fmt = JsonFormatter()

    app_handler = RotatingFileHandler(
        os.path.join(log_dir, "odar.log"), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    app_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [app_handler, console]

    audit_handler = RotatingFileHandler(
        os.path.join(log_dir, "audit.log"), maxBytes=10 * 1024 * 1024, backupCount=10
    )
    audit_handler.setFormatter(fmt)
    audit = logging.getLogger("odar.audit")
    audit.setLevel("INFO")
    audit.propagate = False
    audit.handlers = [audit_handler]
