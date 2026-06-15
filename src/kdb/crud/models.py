"""schema 常量：与旧索引 schema 对齐的顶层字段集合。

权威 ES mapping 定义在旧 `knowledge_interface_tools/es_search_interface.py:_ensure_index`。
重构约束（已与用户确认）：**不能删字段、不能改字段含义；新增字段（不影响旧数据）允许。**

`SCHEMA_FIELDS` 与旧 `SearchDataInterface.doc_schema_field` 严格一致，用于 `_prepare_document`
把"非 schema 字段"归集进 `ext_info` —— 保持与旧实现完全相同的归集行为，这是与旧实现对齐的前提。
"""

# 与旧 doc_schema_field 完全一致（顺序无关，集合语义）
SCHEMA_FIELDS = {
    "title",
    "synonyms_title",
    "content",
    "data_type",
    "platform",
    "audit_result",
    "quality_level",
    "keywords",
    "indexes",
    "insert_time",
    "update_time",
    "from_type",
    "ext_info",
    "_id",
    "title_embedding",
    "content_embedding",
    "image_indexes",
    "del_flag",
    "from_type_norm",
    "category_infos",
    "client",
    "primary_category",
    "dataset",
    "task_id",
    "multimodal_contents",
    "index_name",
}

# 向量字段维度（与 config_es_engine.json 的 vector_fields 一致）
VECTOR_DIM = 1024

# data_type 取值
DATA_TYPE_QA = "qa"
DATA_TYPE_DOC = "doc"
DATA_TYPE_SEGMENT = "segment"

# 软删除标记字段
DEL_FLAG_FIELD = "del_flag"
