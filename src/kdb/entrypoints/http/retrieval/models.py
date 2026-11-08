from datetime import datetime
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Union
import copy
import re

class SearchRequest(BaseModel):
    text: str
    # 默认 100（原为 1000）。1000 正好落在阿里云 serverless ES 容易取消分片的区间：
    # 实测同一条 query 连打 8 次，返回条数在 628~1000 之间乱跳、探针缺失 4/8；
    # 而 top_k<=100 时条数恒定、12 次零缺失。没显式传 top_k 的调用方原本一直在打大查询，
    # 这里把默认值收到安全区。要更多结果显式传即可。
    top_k: int = 100
    score_threshold: float = -1
    index_names: str = None
    condition_dicts: List[Dict[str, Any]] = None
    search_type: str = 'qa'
    data_type: str = 'text'
    use_synonyms: bool = False


class SearchResult(BaseModel):
    id: Optional[str] = None
    dataset: Optional[str] = None
    insert_time: Optional[str] = None
    update_time: Optional[str] = None
    q: str
    a: Optional[str] = None
    ext_info: Optional[Dict[str, Any]] = None
    score: float

    class Config:
        extra = "allow"  # 允许额外字段


class SearchResponse(BaseModel):
    results: List[SearchResult]


class WebSearchRequest(BaseModel):
    text: str = ''
    page_size: int = 10000
    page_num: int = 1
    index_names: str = None
    client: str = None
    need_from_history: bool = False
    condition_dicts: List[Dict[str, Any]] = []
    score_threshold: float = 5.3


class WebSearchResponse(BaseModel):
    results: List[Dict[str, Any]] = []   # 直接返回原始数据字典列表
    total_count : int = 0  # 总记录数
    current_count: int = 0  # 当前请求返回的数据数量


class InsertRequest(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    title: str = None
    content: str = None
    multimodal_contents: Optional[List[Dict[str, Any]]] = None
    data_type: str = None
    from_type: str = None
    index_names: str
    platform: str = None
    audit_result: int = None
    client: str = None
    del_flag: int = None
    tags: Optional[List[str]] = None
    from_type_norm: str = None
    dataset: str = None
    task_id: str = None
    categoryId: str = None
    categoryName: str = None
    category_infos: Optional[List[Dict[str, Any]]] = None
    ext_info: Optional[Dict[str, Any]] = None
    refresh_imm: bool = False
    is_need_llm: bool = False
    is_update_data: bool = True

    class Config:
        allow_population_by_field_name = True
        extra = "allow"  # 允许额外字段

    @property
    def _id(self) -> Optional[str]:
        """为了兼容性，允许使用 _id 访问 id 字段"""
        return self.id

    def get_ext_info_with_extra_fields(self, defined_fields: List[str] = None) -> Dict[str, Any]:
        """
        合并显式ext_info和业务扩展字段，不混入请求控制参数或修改请求对象。
        """
        declared_fields = type(self).model_fields
        excluded_fields = set(defined_fields or ()) | set(declared_fields)
        excluded_fields.update(field.alias for field in declared_fields.values() if field.alias)
        final_ext_info = copy.deepcopy(self.ext_info or {})
        for field_name, field_value in self.model_dump(exclude_none=True).items():
            if field_name not in excluded_fields:
                final_ext_info[field_name] = copy.deepcopy(field_value)
        return final_ext_info


class InsertResponse(BaseModel):
    success: bool
    message: str = ""


class DeleteRequest(BaseModel):
    id: str = Field(..., description="数据ID")
    index_names: str = Field(..., description="索引名称")
    refresh_imm: bool = Field(False, description="是否立即刷新使删除立即生效")


class DeleteResponse(BaseModel):
    success: bool
    message: str = ""


class ValueCollectionRequest(BaseModel):
    index_name: str = Field(..., description="索引名称")
    field_name: str = Field(..., description="字段名称")
    size: int = Field(10000, description="返回值的数量限制")
    include_doc_count: bool = Field(False, description="是否包含文档数量")
    extra_query: Optional[Dict[str, Any]] = Field(None, description="额外的查询条件")


class ValueCollectionResponse(BaseModel):
    success: bool
    values: Union[List[str], List[Dict[str, Any]]] = []
    total_count: int = 0
    message: str = ""


class FromTypeCountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index_name: Optional[str] = Field("", strict=True, description="单个原物理索引名；空名返回0")
    from_type: str = Field("chat_auto", strict=True, min_length=1, description="精确来源类型，默认chat_auto")
    start: Optional[datetime] = None
    end: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_index_name(cls, values):
        if isinstance(values, dict) and "indexName" in values:
            values = dict(values)
            alias = values.pop("indexName")
            if "index_name" in values and values["index_name"] != alias:
                raise ValueError("index_name与indexName不能冲突")
            values["index_name"] = alias
        return values

    @field_validator("index_name")
    @classmethod
    def validate_index_name(cls, value):
        if value and (value in {"_all", ".", ".."} or value.startswith(("-", "+", "_"))
                      or any(char.isspace() or char in '\\/*?"<>|,#:[]' for char in value)
                      or len(value.encode("utf-8")) > 255):
            raise ValueError("index_name必须是单个原物理索引名")
        return value

    @field_validator("start", "end", mode="before")
    @classmethod
    def validate_local_time(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value):
                raise ValueError("时间格式必须为yyyy-MM-dd HH:mm:ss")
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        if isinstance(value, datetime) and value.tzinfo is None and not value.microsecond:
            return value
        raise ValueError("时间必须为不带时区的本地时间，精确到秒")


class FromTypeCountResponse(BaseModel):
    success: bool
    count: int = 0
    message: str = ""


class ListFileNamesRequest(BaseModel):
    index_name: str = Field(..., description="索引名称，必填")
    keyword: Optional[str] = Field(None, description="文件名关键词筛选，为空则列全部")
    size: int = Field(200, ge=1, le=1000, description="最多返回多少个文件名")
    from_type_norm: Optional[str] = Field(None, description="来源类型精确筛选；不传、null、空串或仅空白时不限制来源")


class ListFileNamesResponse(BaseModel):
    success: bool
    values: List[Dict[str, Any]] = []
    total_count: int = 0
    message: str = ""


class PreviewDeleteByFileRequest(BaseModel):
    index_name: str = Field(..., description="索引名称，必填")
    file_names: List[str] = Field(..., description="要删除的来源文件名，可多个")
    match_mode: str = Field("exact", description="exact(默认)|fuzzy，严格二选一，无兜底")
    data_types: Optional[List[str]] = Field(None, description="限定 data_type，默认 qa+segment 全删")
    audit_results: Optional[List[int]] = Field(None, description="限定审核状态，默认不限")
    sample_size: int = Field(10, ge=0, le=50, description="返回几条样例供人工确认")


class PreviewDeleteByFileResponse(BaseModel):
    success: bool
    total_count: int = 0
    by_file: List[Dict[str, Any]] = []
    type_count: Dict[str, int] = {}
    samples: List[Dict[str, Any]] = []
    warnings: List[str] = []
    message: str = ""


class DeleteByFileRequest(BaseModel):
    """入参与 PreviewDeleteByFileRequest 一致（除样例条数），区别只是这个真删。"""
    index_name: str = Field(..., description="索引名称，必填")
    file_names: List[str] = Field(..., description="要删除的来源文件名，可多个")
    match_mode: str = Field("exact", description="exact(默认)|fuzzy，严格二选一，无兜底")
    data_types: Optional[List[str]] = Field(None, description="限定 data_type，默认 qa+segment 全删")
    audit_results: Optional[List[int]] = Field(None, description="限定审核状态，默认不限")


class DeleteByFileResponse(BaseModel):
    success: bool
    deleted_count: int = 0
    snapshot_path: Optional[str] = None
    message: str = ""


class UpdateByConditionRequest(BaseModel):
    index_name: str = Field(..., description="索引名称")
    update_fields: Dict[str, Any] = Field(..., description="要更新的字段和值的映射，格式为 {field_name: new_value}")
    conditions: List[Dict[str, Any]] = Field(..., description="查询条件列表，每个条件为 {field_name: value} 格式")


class UpdateByConditionResponse(BaseModel):
    success: bool
    updated_count: int = 0
    message: str = ""


class ModifyKnowledgeRequest(BaseModel):
    es_index: str = Field(..., description="ES索引名称")
    new_query_info: Dict[str, Any] = Field(..., description="新查询信息，包含title和content")
    old_query_info: Dict[str, Any] = Field(default={}, description="旧查询信息，包含title和content；modify_knowledge接口必填，modify_knowledge_direct_update接口可选")
    search_querys: Optional[List[str]] = Field(None, description="搜索查询列表")
    write_db_id: Optional[str] = Field(None, description="写入数据库ID（仅modify_knowledge使用）")
    allow_insert: bool = Field(False, description="是否允许插入新QA到ES，仅当为True且没有要修改的旧QA时才插入")


class ModifyKnowledgeResponse(BaseModel):
    success: bool
    has_correction: bool = False
    message: str = ""
    modify_qa_infos: Optional[List[Dict[str, Any]]] = None
