# kdb.shared.similarity.knowledge.SimilityTools.is_simility_knowledge

## Signature

`SimilityTools.is_simility_knowledge(self, doc_1, doc_2, is_need_llm=False, is_only_title=False, basic_threshold=0.7, title_basic_threshold=0.95)`

## Inputs

两条知识及原阈值参数；类型须相同，不按platform过滤。

## Outputs

归一化标题及正文完全相同直接命中；保留向量规则与可选直接LLM判重。

## SQL / ES

无数据库访问；模型访问仅按显式配置执行。

## Source

`src/kdb/shared/similarity/knowledge.py`
