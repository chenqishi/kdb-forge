from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
import os
from pathlib import Path
from typing import Optional

BASE_DIR = _PROJECT_ROOT

DEFAULT_CACHE_CONTROL = "public, max-age=31536000, immutable"

CONFIG_PATH: Optional[Path] = None

DEFAULT_CONFIG_CANDIDATES = [
    lambda: CONFIG_PATH,
    lambda: os.environ.get("MINIO_CONFIG_PATH"),
    lambda: BASE_DIR / "config" / "minio_config.json",
    lambda: BASE_DIR / "config" / "minio_config_default.json",
    lambda: BASE_DIR / "config" / "minio_config_default_aws_test.json",
]

CHUNK_SIZE = 1024 * 1024  # 1MB

DEFAULT_DOWNLOAD_TIMEOUT = int(os.environ.get("FILE_SERVICE_DOWNLOAD_TIMEOUT", "180"))

CONNECT_TIMEOUT = int(os.environ.get("FILE_SERVICE_CONNECT_TIMEOUT", "10"))
