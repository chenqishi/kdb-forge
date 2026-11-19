# kdb.shared.similarity.knowledge.SimLLMModel.__init__

## Signature

`SimLLMModel.__init__(self, api_base=None, api_key=None, model_name=None)`

## Inputs

显式直接LLM配置；省略时使用既有本地LLM adapter。

## Outputs

创建惰性调用器，不访问Dify。

## SQL / ES

无数据库访问；模型访问仅按显式配置执行。

## Source

`src/kdb/shared/similarity/knowledge.py`
