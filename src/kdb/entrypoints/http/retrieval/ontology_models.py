"""HTTP shapes for complete ontology resources; row controls stay outside data_json."""
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

ScopeCode = Annotated[str, Field(max_length=64, pattern=r"^([a-z0-9][a-z0-9_.-]{0,63})?$")]
Revision = Annotated[int, Field(strict=True, ge=1)]
OntologyID = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{32}$", description="本体标识，32位小写十六进制 UUID")]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class InsertOntologyRequest(_Request):
    data_json: Any
    status: Optional[Literal["draft", "active"]] = None


class GetOntologyRequest(_Request):
    ontology_id: OntologyID


class UpdateOntologyRequest(InsertOntologyRequest):
    ontology_id: OntologyID
    revision: Revision


class UpdateOntologyStatusRequest(GetOntologyRequest):
    status: Literal["draft", "active"]
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
    status: Literal["draft", "active"]
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
    scope_values: List[str]
    data_types: List[str]
    item_types: List[str]
    cardinalities: List[str]
    severities: List[str]
    reserved_fields: List[str]
    limits: Dict[str, int]
