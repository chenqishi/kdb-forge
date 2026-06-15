"""接线层：把旧项目（knowledge_database_builder）接入 Python path，并统一 re-export 复用对象。

设计决策（已与用户确认）：
- **复用旧适配层**：CRUD 直接复用旧 `EsSearchInterface`（ES/OpenSearch 双引擎驱动）和 `AliEmbedding`，不重写底层。
- **零侵入接线**：通过 sys.path 注入旧项目根目录，不修改旧代码、不要求打包安装。
  旧项目根路径可用环境变量 `KDB_LEGACY_ROOT` 覆盖。

注意：`gen_data_id` 所在模块 `search_index_data_interface` 顶层 import 链较重（dify/keywords/simility，
可能触达 `config_tools/config.py` 的 import 期 json.load）。这里对它单独 try，失败则置空，
由 `kdb.crud.ids` 用字节级一致的内置实现兜底。
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

# 旧项目根目录（含 commons/、knowledge_interface_tools/ 等包）
LEGACY_ROOT = os.environ.get(
    "KDB_LEGACY_ROOT",
    "/Users/chenqishi/stone_fish/knowledge_database_builder",
)


def ensure_legacy_on_path(root: str = None) -> str:
    """把旧项目根目录插入 sys.path（幂等）。

    Args:
        root: 旧项目根目录；默认取 `LEGACY_ROOT`（可被环境变量覆盖）。
    Returns:
        实际生效的根目录路径。
    """
    root = root or LEGACY_ROOT
    if root and os.path.isdir(root) and root not in sys.path:
        sys.path.insert(0, root)
    return root


# import 旧模块前先确保 path 就绪
ensure_legacy_on_path()

# 硬依赖：底层 ES 适配层 + embedding（缺失则无法工作，直接抛错）
from knowledge_interface_tools.es_search_interface import EsSearchInterface  # noqa: E402

# 软依赖：相似度实现。优先复用旧实现以保证浮点口径一致；导入失败时本文件提供等价兜底。
try:
    from commons.simility_tools import cosine_similarity as _legacy_cosine_similarity  # noqa: E402
except Exception as exc:  # pragma: no cover - 仅在旧依赖缺失时触发
    logger.warning("无法导入旧 cosine_similarity，使用内置等价实现: %s", exc)
    _legacy_cosine_similarity = None

# 软依赖：旧 _id 生成。失败则由 kdb.crud.ids 兜底。
try:
    from knowledge_interface_tools.search_index_data_interface import (  # noqa: E402
        gen_data_id as legacy_gen_data_id,
    )
    HAS_LEGACY_GEN_DATA_ID = True
except Exception as exc:  # pragma: no cover
    logger.warning("无法导入旧 gen_data_id，将使用内置复刻实现: %s", exc)
    legacy_gen_data_id = None
    HAS_LEGACY_GEN_DATA_ID = False

# 软依赖：业务默认补齐用。两者都是本地纯 Python 实现（jieba/规则），不打外部 LLM/HTTP。
# - gen_keyword_by_title_content: 基于 jieba.analyse.textrank，结果在同输入下确定性。
# - get_from_norm_type: 基于 from_type 的规则映射（无外部依赖）。
try:
    from commons.keywords_tools import (  # noqa: E402
        gen_keyword_by_title_content as legacy_gen_keyword_by_title_content,
    )
except Exception as exc:  # pragma: no cover
    logger.warning("无法导入旧 gen_keyword_by_title_content，关键词将跳过: %s", exc)
    legacy_gen_keyword_by_title_content = None

try:
    from knowledge_interface_tools.knowledge_tools import (  # noqa: E402
        get_from_norm_type as legacy_get_from_norm_type,
    )
except Exception as exc:  # pragma: no cover
    logger.warning("无法导入旧 get_from_norm_type，from_type_norm 将留空: %s", exc)
    legacy_get_from_norm_type = None


def cosine_similarity(vec1, vec2):
    """余弦相似度。复用旧实现；不可用时退回等价实现（公式相同，浮点结果一致）。"""
    if _legacy_cosine_similarity is not None:
        return _legacy_cosine_similarity(vec1, vec2)
    import numpy as np

    v1 = np.asarray(vec1, dtype=float)
    v2 = np.asarray(vec2, dtype=float)
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0
    return float(np.dot(v1, v2) / (n1 * n2))


def load_legacy_search_interface(config_path: str, index_name: str = None):
    """构造旧 `SearchDataInterface`（仅供对齐测试使用）。

    单独按需 import，避免在生产/回环路径触发其重 import 链。
    Args:
        config_path: 旧 config_for_search_index.json 路径。
        index_name: 覆盖索引名（如 'test_case'）。
    Returns:
        旧 SearchDataInterface 实例。
    """
    from knowledge_interface_tools.search_index_data_interface import SearchDataInterface

    kwargs = {}
    if index_name:
        kwargs["index_name"] = index_name
    return SearchDataInterface(config_path=config_path, **kwargs)


def build_legacy_engine(config_path: str = None, index_name: str = None, **kwargs):
    """构造旧 `EsSearchInterface`（底层 ES/OpenSearch 驱动）。

    Args:
        config_path: config_es_engine.json 路径。
        index_name: 覆盖索引名（显式参数优先于 config 中的 index_name）。
    Returns:
        EsSearchInterface 实例。
    """
    return EsSearchInterface(config_path=config_path, index_name=index_name, **kwargs)


__all__ = [
    "LEGACY_ROOT",
    "ensure_legacy_on_path",
    "EsSearchInterface",
    "cosine_similarity",
    "legacy_gen_data_id",
    "HAS_LEGACY_GEN_DATA_ID",
    "legacy_gen_keyword_by_title_content",
    "legacy_get_from_norm_type",
    "load_legacy_search_interface",
    "build_legacy_engine",
]
