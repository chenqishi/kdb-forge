# kdb.shared.similarity.knowledge.SimilityTools.__init__

## Signature

`SimilityTools.__init__(self, config_path: str=None)`

## Inputs

相似度配置；llm对象为直接模型配置；不再使用Dify凭据。

## Outputs

保留向量阈值接口并构建直接LLM判定器。

## SQL / ES

无数据库访问；模型访问仅按显式配置执行。

## Source

`src/kdb/shared/similarity/knowledge.py`
