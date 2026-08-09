import logging
import json
from datetime import datetime, timezone
import os
from src.core.config import settings

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        })

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())

os.makedirs(settings.LOG_DIR, exist_ok=True)

file_handler = logging.FileHandler(filename=os.path.join(settings.LOG_DIR, f"app-{datetime.now(timezone.utc).date()}.log"))
file_handler.setFormatter(JSONFormatter())

logger = logging.getLogger("app")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.addHandler(file_handler)