# kdb.shared.similarity.knowledge.SimLLMModel.is_simility_knowledge

## Signature

`SimLLMModel.is_simility_knowledge(self, doc_1, doc_2)`

## Inputs

同一index内两条同类型知识。

## Outputs

仅完整语义等价且双侧原文证据可验证时返回1，其余0；模型错误向上传播。

## SQL / ES

无数据库访问；模型访问仅按显式配置执行。

## Source

`src/kdb/shared/similarity/knowledge.py`
