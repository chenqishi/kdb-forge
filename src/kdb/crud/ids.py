"""文档 _id 生成。

为保证与旧实现"字节级一致"，优先复用旧 `gen_data_id`；旧 import 链不可用时，
退回到内置复刻实现——两者算法完全相同：`md5(f"{title}_{content}_{data_type}")`。
对齐测试会断言"内置 == 旧"（当旧实现可用时）。
"""

import hashlib
from typing import Any, Dict

from kdb.legacy_bridge import HAS_LEGACY_GEN_DATA_ID, legacy_gen_data_id


def _builtin_gen_data_id(data: Dict[str, Any]) -> str:
    """内置复刻：与旧 gen_data_id 算法字节级一致。"""
    title = data.get("title", "")
    content = data.get("content", "")
    data_type = data.get("data_type", "")
    id_str = f"{title}_{content}_{data_type}"
    return hashlib.md5(id_str.encode("utf-8")).hexdigest()


def gen_data_id(data: Dict[str, Any]) -> str:
    """生成文档唯一 _id（title + content + data_type 的 MD5）。

    Args:
        data: 文档 dict。
    Returns:
        32 位十六进制 MD5 字符串。
    """
    if HAS_LEGACY_GEN_DATA_ID and legacy_gen_data_id is not None:
        return legacy_gen_data_id(data)
    return _builtin_gen_data_id(data)
