"""embedding 层：EmbeddingClient 协议 + 旧 AliEmbedding 适配。"""

from kdb.embedding.client import EmbeddingClient, build_embedding_client

__all__ = ["EmbeddingClient", "build_embedding_client"]
