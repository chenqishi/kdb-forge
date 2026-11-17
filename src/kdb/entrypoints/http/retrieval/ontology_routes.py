"""Eight ontology operations mounted on the existing retrieval application."""
from typing import Annotated, Literal, Optional, Union
import inspect

from fastapi import Depends, Query
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from kdb.retrieval.ontology import schema
from kdb.retrieval.ontology.errors import OntologyError, ONTOLOGY_BAD_REQUEST
from kdb.retrieval.ontology.repository import OntologyRepository
from kdb.retrieval.ontology.service import OntologyService
from kdb.retrieval.ontology.validation import pydantic_issues

from .ontology_models import (DeleteOntologyRequest, DetailResponse, DocumentResponse, GetOntologyRequest,
                              InsertOntologyRequest, InsertOntologyResponse, ListResponse, MetaResponse,
                              MutationResponse, OntologyErrorBody, SelectOntologyRequest, SelectResponse,
                              UpdateOntologyRequest, UpdateOntologyStatusRequest)

ScopeQuery = Annotated[Optional[str], Query(max_length=64, pattern=r"^([a-z0-9][a-z0-9_.-]{0,63})?$")]


def get_service() -> OntologyService:
    return OntologyService(OntologyRepository())


def insert_ontology(body: InsertOntologyRequest, service: OntologyService = Depends(get_service)):
    return service.insert_ontology(body)


def get_ontology(body: GetOntologyRequest, view: Literal["full", "document", "outline"] = "full",
                 include_deleted: bool = False, service: OntologyService = Depends(get_service)):
    return service.get_ontology(body.ontology_id, view, include_deleted)


def list_ontologies(client: ScopeQuery = None, product: ScopeQuery = None,
                    status: Optional[Literal["draft", "active"]] = None,
                    q: Optional[str] = None, deep: Annotated[int, Query(ge=0, le=1)] = 0,
                    include_deleted: bool = False,
                    page: Annotated[int, Query(description="页码，从1开始，范围由业务服务校验")] = 1,
                    page_size: Annotated[int, Query(description="每页条数，1至100，范围由业务服务校验")] = schema.DEFAULT_PAGE_SIZE,
                    service: OntologyService = Depends(get_service)):
    return service.list_ontologies(client=client, product=product, status=status, q=q.strip() if q else None,
                        deep=bool(deep), include_deleted=include_deleted, page=page, page_size=page_size)


def update_ontology(body: UpdateOntologyRequest, service: OntologyService = Depends(get_service)):
    return service.update_ontology(body.ontology_id, body)


def update_ontology_status(body: UpdateOntologyStatusRequest, service: OntologyService = Depends(get_service)):
    return service.update_ontology_status(body.ontology_id, body)


def delete_ontology(body: DeleteOntologyRequest,
                    service: OntologyService = Depends(get_service)):
    return service.delete_ontology(body.ontology_id, body.revision)


def select_ontology(body: SelectOntologyRequest, service: OntologyService = Depends(get_service)):
    return service.select_ontology(**body.model_dump())


def ontology_meta():
    return {"success": True, "message": "", "schema_version": schema.SCHEMA_VERSION,
            "status_values": schema.STATUS_VALUES, "scope_values": schema.SCOPE_VALUES,
            "data_types": schema.DATA_TYPES, "item_types": schema.ITEM_TYPES,
            "cardinalities": schema.CARDINALITIES, "severities": schema.SEVERITIES,
            "reserved_fields": schema.RESERVED_FIELD_ORDER,
            "limits": {"max_document_bytes": schema.MAX_DOCUMENT_BYTES, "warn_document_bytes": schema.WARN_DOCUMENT_BYTES,
                       "object_types": 200, "attributes_per_object": 200, "relations": 500, "value_sets": 200,
                       "values_per_set": 100, "rules": 200, "terms": 500, "alias_per_node": 20,
                       "name_chars": 128, "description_chars": 2048}}


async def ontology_error_handler(request, exc):
    if "ontology" not in getattr(request.scope.get("route"), "tags", ()):
        handler = getattr(request.app.state, "ontology_previous_error_handler", None)
        if handler is not None:
            result = handler(request, exc)
            return await result if inspect.isawaitable(result) else result
        return JSONResponse(status_code=exc.http_status, content={"detail": exc.message})
    return JSONResponse(status_code=exc.http_status, content=exc.to_body())


async def ontology_request_error_handler(request, exc):
    if "ontology" in getattr(request.scope.get("route"), "tags", ()):
        error = OntologyError(ONTOLOGY_BAD_REQUEST, 400, "请求参数不合法", pydantic_issues(exc.errors()))
        return JSONResponse(status_code=400, content=error.to_body())
    handler = getattr(request.app.state, "ontology_previous_validation_handler", request_validation_exception_handler)
    result = handler(request, exc)
    return await result if inspect.isawaitable(result) else result


def register_ontology_routes(app):
    errors = {status: {"model": OntologyErrorBody} for status in (400, 404, 409, 413, 422, 503, 500)}
    options = {"responses": errors, "tags": ["ontology"]}
    app.get("/ontology_meta", response_model=MetaResponse, **options)(ontology_meta)
    app.post("/select_ontology", response_model=SelectResponse, **options)(select_ontology)
    app.post("/list_ontologies", response_model=ListResponse, **options)(list_ontologies)
    app.post("/insert_ontology", response_model=InsertOntologyResponse, status_code=201,
             response_model_exclude_none=True, **options)(insert_ontology)
    app.post("/get_ontology", response_model=Union[DocumentResponse, DetailResponse], **options)(get_ontology)
    mutation = dict(options, response_model=MutationResponse, response_model_exclude_none=True)
    app.post("/update_ontology", **mutation)(update_ontology)
    app.post("/update_ontology_status", **mutation)(update_ontology_status)
    app.post("/delete_ontology", **mutation)(delete_ontology)
    app.state.ontology_previous_validation_handler = app.exception_handlers.get(
        RequestValidationError, request_validation_exception_handler)
    app.state.ontology_previous_error_handler = app.exception_handlers.get(OntologyError)
    app.add_exception_handler(OntologyError, ontology_error_handler)
    app.add_exception_handler(RequestValidationError, ontology_request_error_handler)
