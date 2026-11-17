"""HTTP shapes for complete ontology resources; row controls stay outside data_json."""
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ScopeCode = Annotated[str, Field(max_length=64, pattern=r"^([a-z0-9][a-z0-9_.-]{0,63})?$")]
Revision = Annotated[int, Field(strict=True, ge=1)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class CreateRequest(_Request):
    data_json: Any
    status: Optional[Literal["draft", "active"]] = None


class ReplaceRequest(CreateRequest):
    revision: Revision


class PatchStatusRequest(_Request):
    status: Literal["draft", "active"]
    revision: Revision


class ResolveRequest(_Request):
    client: ScopeCode = ""
    product: ScopeCode = ""
    name: Optional[str] = Field(default=None, max_length=255)
    include_document: bool = True


class OntologyErrorBody(BaseModel):
    success: bool = False
    code: str
    message: str
    details: List[Dict[str, Any]] = Field(default_factory=list)


class OntologyMeta(BaseModel):
    ontology_id: str
    client: str
    product: str
    name: str
    status: str
    revision: int
    create_time: str
    update_time: str
    document_bytes: int
    del_flag: Optional[int] = None


class OntologyFull(OntologyMeta):
    alias_name: List[str]
    description: str
    del_flag: int
    data_json: Dict[str, Any]


class _Success(BaseModel):
    success: bool = True
    message: str = ""


class CreateResponse(_Success):
    ontology: OntologyFull


class DetailResponse(_Success):
    ontology: Dict[str, Any]


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
    items: List[Dict[str, Any]]


class ResolveResponse(_Success):
    scope: str
    fallback: bool
    request: Dict[str, str]
    ontology: Optional[Dict[str, Any]]


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
