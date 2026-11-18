"""HTTP shapes for complete ontology resources; row controls stay outside data_json."""
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from kdb.retrieval.ontology.schema import DEFAULT_REVIEW_STATUS, DEFAULT_STATUS

ScopeCode = Annotated[str, Field(max_length=64, pattern=r"^([a-z0-9][a-z0-9_.-]{0,63})?$")]
Revision = Annotated[int, Field(strict=True, ge=1)]
OntologyID = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$", description="本体标识，32位小写十六进制 UUID")]
OntologyStatus = Literal["active", "inactive"]
ReviewStatus = Literal["pending", "approved", "rejected"]
ReviewFilter = Literal["pending", "approved", "rejected", "all"]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class InsertOntologyRequest(_Request):
    data_json: Any
    status: OntologyStatus = Field(default=DEFAULT_STATUS, description="生效状态：active启用，inactive停用")
    review_status: ReviewStatus = Field(default=DEFAULT_REVIEW_STATUS, description="审核状态：pending待审，approved通过，rejected驳回")


class GetOntologyRequest(_Request):
    ontology_id: OntologyID


class UpdateOntologyRequest(InsertOntologyRequest):
    ontology_id: OntologyID
    revision: Revision
    status: Optional[OntologyStatus] = Field(default=None, description="缺省保留当前生效状态")
    review_status: Optional[ReviewStatus] = Field(default=None, description="正文替换时缺省重置pending；可显式指定审核结果")


class UpdateOntologyStatusRequest(GetOntologyRequest):
    status: Optional[OntologyStatus] = Field(default=None, description="可与review_status分别更新，至少提供一个；未传则保留")
    review_status: Optional[ReviewStatus] = Field(default=None, description="审核状态，可独立更新；未传则保留")
    revision: Revision


class DeleteOntologyRequest(GetOntologyRequest):
    revision: Optional[Revision] = None


class SelectOntologyRequest(_Request):
    client: ScopeCode = ""
    product: ScopeCode = ""
    name: Optional[str] = Field(default=None, max_length=255)
    include_document: bool = True


class OntologyErrorBody(BaseModel):
    success: bool = False
    code: str
    message: str
    details: List[Dict[str, Any]] = Field(default_factory=list)


class OntologySelectionBase(BaseModel):
    ontology_id: str
    client: str
    product: str
    name: str
    status: OntologyStatus = Field(description="生效状态：active启用，inactive停用")
    review_status: ReviewStatus = Field(description="审核状态：pending待审，approved通过，rejected驳回")
    revision: int
    update_time: str


class OntologySummary(OntologySelectionBase):
    create_time: str


class OntologyMeta(OntologySummary):
    document_bytes: int = Field(description="完整文档的紧凑 UTF-8 字节数")
    del_flag: Optional[int] = None


class OntologyFull(OntologyMeta):
    alias_name: List[str]
    description: str
    del_flag: int
    data_json: Dict[str, Any] = Field(description="完整本体文档，结构定义见 ontology.schema.json")


class OntologyListItem(OntologySummary):
    alias_name: List[str]
    description: str


class ObjectTypeOutline(BaseModel):
    name: str
    description: str
    attribute_count: int
    attribute_names: List[str]


class OntologyCounts(BaseModel):
    object_types: int
    relations: int
    value_sets: int
    rules: int
    terms: int
    attributes: int


class OntologyOutlineContent(BaseModel):
    object_types: List[ObjectTypeOutline]
    counts: OntologyCounts


class OntologyOutline(OntologySelectionBase):
    outline: OntologyOutlineContent


class SelectedOntologyDocument(OntologySelectionBase):
    data_json: Dict[str, Any] = Field(description="选中行的完整本体文档，不与其他作用域合并")


class OntologyScope(BaseModel):
    client: str
    product: str


class _Success(BaseModel):
    success: bool = True
    message: str = ""


class InsertOntologyResponse(_Success):
    ontology: OntologyMeta


class DetailResponse(_Success):
    ontology: Union[OntologyFull, OntologyOutline]


class DocumentResponse(_Success):
    ontology_id: str
    status: OntologyStatus
    review_status: ReviewStatus
    revision: int
    document: Dict[str, Any]


class MutationResponse(_Success):
    ontology: OntologyMeta
    deleted: Optional[bool] = None


class ListResponse(_Success):
    total: int
    page: int
    page_size: int
    items: List[OntologyListItem]


class SelectResponse(_Success):
    scope: Literal["client_product", "client", "industry", "global", "none"]
    fallback: bool
    request: OntologyScope
    ontology: Optional[Union[SelectedOntologyDocument, OntologyOutline]]


class MetaResponse(_Success):
    schema_version: str
    status_values: List[str]
    review_status_values: List[str]
    scope_values: List[str]
    data_types: List[str]
    item_types: List[str]
    cardinalities: List[str]
    severities: List[str]
    reserved_fields: List[str]
    limits: Dict[str, int]
