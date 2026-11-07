"""Load an explicitly selected JSON runtime configuration."""

import json
from typing import Any, Dict


def load_config(config_path: str) -> Dict[str, Any]:
    """读取 JSON 配置文件并返回 dict。

    Args:
        config_path: 配置文件绝对路径。
    Returns:
        配置 dict。
    Raises:
        FileNotFoundError / json.JSONDecodeError: 文件缺失或格式错误时。
    """
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)
