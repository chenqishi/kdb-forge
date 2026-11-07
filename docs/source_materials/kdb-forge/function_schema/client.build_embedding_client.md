# build_embedding_client

## 所属文件
`src/kdb/embedding/client.py`

## 功能描述
根据 embedding 配置构造默认 `EmbeddingClient`（复用旧 `commons.embedding_tools.AliEmbedding`，阿里 DashScope text-embedding-v3，1024 维）。`EmbeddingClient` 为 Protocol：`text2embedding(text: str|List[str]) -> np.ndarray`。

## Inputs
- `config_path` (str): config_ali_embedding.json 路径（含 DASHSCOPE_API_KEY / URL / MODEL / DIMENSION）。

## Outputs
- 实现 `EmbeddingClient` 协议的实例（单文本返回 shape (1024,)，列表返回 (n,1024)）。

## 关键依赖
- `commons.embedding_tools.AliEmbedding`（经 legacy_bridge 接入）

## SQL
无。
