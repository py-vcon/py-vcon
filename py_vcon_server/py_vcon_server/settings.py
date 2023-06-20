import os
from pathlib import Path

VCON_STORAGE_TYPE = os.getenv("VCON_STORAGE_TYPE", "redis")
VCON_STORAGE_URL = os.getenv("STORAGE_URL", "redis://localhost")
HOSTNAME = os.getenv("HOSTNAME", "http://localhost:8000")
ENV = os.getenv("ENV", "dev")
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
LOGGING_CONFIG_FILE = os.getenv("LOGGING_CONFIG_FILE", Path(__file__).parent / 'logging.conf')

