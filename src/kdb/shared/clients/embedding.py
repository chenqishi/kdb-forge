from kdb.shared.clients.embedding_tools import AliEmbedding
from typing import Protocol


class EmbeddingClient(Protocol):
    def text2embedding(self, text): ...


def build_embedding_client(config_path):
    return AliEmbedding(config_path)
