# kdb.shared.clients.embedding.build_embedding_client

## Signature

`build_embedding_client(config_path)`

## Description

根据 embedding 配置构造默认 `EmbeddingClient`（复用旧 `kdb.shared.clients.embedding_tools.AliEmbedding`，阿里 DashScope text-embedding-v3，1024 维）。`EmbeddingClient` 为 Protocol：`text2embedding(text: str|List[str]) -> np.ndarray`。

## Inputs

- `config_path` (str): config_ali_embedding.json 路径（含 DASHSCOPE_API_KEY / URL / MODEL / DIMENSION）。

## Outputs

- 实现 `EmbeddingClient` 协议的实例（单文本返回 shape (1024,)，列表返回 (n,1024)）。

## 关键依赖

- `kdb.shared.clients.embedding_tools.AliEmbedding`（经 legacy_bridge 接入）

## SQL

无。

## Source

`src/kdb/shared/clients/embedding.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
