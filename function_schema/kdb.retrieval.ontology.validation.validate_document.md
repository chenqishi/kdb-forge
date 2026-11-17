# kdb.retrieval.ontology.validation.validate_document

## Signature

`validate_document(raw: Any) -> ValidatedDocument`

## Inputs

raw 是完整文档对象或只解析一次的 JSON 字符串。schema_version 必须为 1.0。

## Outputs

返回冻结的 ValidatedDocument：规范化文档、client/product/name/alias_name/description 五个投影及紧凑 UTF-8 document_bytes，不修改原对象。

固定顺序：入参形态→紧凑字节数≤1MB→版本→保留键（extensions 子树跳过）→严格 Pydantic 结构/自由字典大小→NFKC+casefold 唯一性→类型字段组合→引用→投影/最终大小。所有字符串值 strip，不 lower 客户/行业，不重写引用拼写，填充模型默认值。

第3–7步最多返回50条有序 path/reason/message；结构失败停止后续依赖结构的检查；出现保留键时顶层 code 优先 ONTOLOGY_RESERVED_FIELD。其他错误为 ONTOLOGY_VALIDATION_FAILED；不支持版本为 ONTOLOGY_SCHEMA_VERSION_UNSUPPORTED；超1MB为413 ONTOLOGY_PAYLOAD_TOO_LARGE。自由字典根64KB、节点16KB；最终文档超过200KB只记warning，不拒绝。错误 reason 见 docs/api.md 与设计v8 §5.3，不透传 Pydantic 原始错误类型或 input。

## SQL

无 SQL/HTTP/ES/embedding；只依赖 models、schema、errors 及标准库。投影与最终文档在同一个返回值中交仓储写入。

## Source

`src/kdb/retrieval/ontology/validation.py`。依据业务本体设计 v8 §3–5；字段结构真值为 models.py，产物 ontology.schema.json。
