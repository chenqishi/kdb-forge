"""Retained forge wire schema constants; no processing or indexing algorithm."""
SCHEMA_FIELDS = {
    "title", "synonyms_title", "content", "data_type", "platform", "audit_result",
    "quality_level", "keywords", "indexes", "insert_time", "update_time", "from_type",
    "ext_info", "_id", "title_embedding", "content_embedding", "image_indexes",
    "del_flag", "from_type_norm", "category_infos", "client", "primary_category",
    "dataset", "task_id", "multimodal_contents", "index_name",
}
VECTOR_DIM = 1024
DATA_TYPE_QA = "qa"
DATA_TYPE_DOC = "doc"
DATA_TYPE_SEGMENT = "segment"
DEL_FLAG_FIELD = "del_flag"
