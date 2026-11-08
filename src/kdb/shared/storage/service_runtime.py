from functools import lru_cache
from kdb.shared.storage.minio import MinioTools
from pathlib import Path
from typing import Dict
import json
import kdb.shared.storage.runtime_state as runtime_state
import logging
logger = logging.getLogger('kdb.entrypoints.http.files.app')

def _load_json_config(path: Path) -> Dict[str, str]:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def _iter_config_candidates():
    for candidate_fn in runtime_state.DEFAULT_CONFIG_CANDIDATES:
        try:
            candidate = candidate_fn()
        except Exception:
            continue

        if not candidate:
            continue

        path = Path(candidate).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if path.exists() and path.is_file():
            yield path


@lru_cache
def get_minio_tools() -> MinioTools:
    """
    通过 MinioTools 初始化 boto3 客户端，复用现有封装。
    """
    config_path = next(_iter_config_candidates(), None)
    if not config_path:
        raise RuntimeError("未找到可用的 MinIO 配置文件")

    config_map = _load_json_config(config_path)
    logger.info("加载 MinIO 配置文件: %s", config_path)
    return MinioTools(config=config_map)


@lru_cache
def get_s3_client():
    tools = get_minio_tools()
    if not tools.s3_client:
        raise RuntimeError("MinioTools 未成功初始化 S3 客户端")
    return tools.s3_client


def set_config_path(config_path: str) -> Path:
    """
    设置自定义配置文件路径，并清理客户端缓存。
    """

    resolved = Path(config_path).expanduser()
    if not resolved.is_absolute():
        resolved = (Path.cwd() / resolved).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"配置文件不存在: {resolved}")
    if not resolved.is_file():
        raise IsADirectoryError(f"配置路径不是文件: {resolved}")

    runtime_state.CONFIG_PATH = resolved
    get_minio_tools.cache_clear()
    get_s3_client.cache_clear()
    logger.info("使用自定义配置文件: %s", runtime_state.CONFIG_PATH)
    return runtime_state.CONFIG_PATH
