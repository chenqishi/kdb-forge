"""EmbeddingClient 协议 + 旧 AliEmbedding 适配。

CRUD 层通过注入 `EmbeddingClient` 使用向量能力，而非硬编码 DashScope —— 这是
"两层架构、低耦合"的体现：Repository 只进出向量，Service 持有一个可替换的 embedding 客户端。

旧 `commons.embedding_tools.AliEmbedding` 已满足 `EmbeddingClient` 协议
（有 `text2embedding(text) -> np.ndarray`），故这里直接复用，不重复造轮子。
"""

from typing import List, Protocol, Union, runtime_checkable

import numpy as np

from kdb.legacy_bridge import ensure_legacy_on_path

ensure_legacy_on_path()
from commons.embedding_tools import AliEmbedding  # noqa: E402


@runtime_checkable
class EmbeddingClient(Protocol):
    """向量生成客户端协议。"""

    def text2embedding(self, text: Union[str, List[str]]) -> np.ndarray:
        """把文本（或文本列表）转成向量；单文本返回 shape (dim,)，列表返回 (n, dim)。"""
        ...


def build_embedding_client(config_path: str) -> EmbeddingClient:
    """根据 embedding 配置构造默认客户端（复用旧 AliEmbedding）。

    Args:
        config_path: config_ali_embedding.json 路径（含 DASHSCOPE_API_KEY 等）。
    Returns:
        实现了 `EmbeddingClient` 协议的实例。
    """
    return AliEmbedding(config_path)
