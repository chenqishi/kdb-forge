from typing import Any

_MAPPING_IGNORED_KEYS = {"index", "similarity"}


def _mapping_config_equal(expected: Any, existing: Any) -> bool:
    """
    判断代码期望的 mapping 配置与 ES 返回的实际配置是否等价。
    只检查 expected 里出现的键（子集语义），并忽略 ES 会静默丢弃的参数和可省略的默认值。
    Args:
        expected: 代码里定义的配置片段
        existing: indices.get_mapping 返回的对应片段，字段不存在时为 None
    Returns:
        bool: 等价为 True
    """
    if isinstance(expected, dict) and isinstance(existing, dict):
        for key, value in expected.items():
            if key in _MAPPING_IGNORED_KEYS:
                continue
            # object 是 ES 的默认类型，返回的 mapping 里不会回显 type
            if key == "type" and value == "object" and "type" not in existing:
                continue
            if not _mapping_config_equal(value, existing.get(key)):
                return False
        return True
    return expected == existing
