# kdb.multilingual.detection.detect_language

## Signature

`detect_language(text)`

## Inputs

HTTP 层完成原有非空检查和换行/空白处理后的文本；使用唯一 runtime.model。

## Outputs

原先 predict_language 中的规则优先、fastText k=1 回退、float 置信度转换和标签转换，返回原 lang/confidence/label 字典。异常继续由 HTTP 层原 try/except 处理，不新增降级或模型初始化。

## SQL

无。

## Source

`src/kdb/multilingual/detection.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
