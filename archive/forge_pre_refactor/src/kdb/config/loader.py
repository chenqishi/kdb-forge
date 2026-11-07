"""配置加载：把 rebuild 的 config json 读成 dict。

rebuild 不复制任何凭据，config_test.json 只用绝对路径引用旧 config 文件
（config_es_engine.json / config_ali_embedding.json / config_for_search_index.json）。
"""

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
