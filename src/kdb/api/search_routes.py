"""Public ES8 retrieval routes preserving the legacy /search contracts.

The routes deliberately expose retrieval only.  Write and delete routes remain in
``knowledge_routes`` and are not mounted here without their existing controls.
"""

from __future__ import annotations

import copy
import logging
import os
import secrets
import threading
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(tags=["retrieval"])
_basic = HTTPBasic(auto_error=False)
_service = None  # type: ignore
_service_lock = threading.Lock()


class SearchRequest(BaseModel):
    text: str
    top_k: int = Field(100, ge=1, le=1000)
    score_threshold: float = -1
    index_names: Optional[Union[str, List[str]]] = None
    condition_dicts: Optional[List[Dict[str, Any]]] = None
    search_type: str = "qa"
    data_type: str = "text"
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
    model_config = {"extra": "allow"}


class SearchResponse(BaseModel):
    results: List[SearchResult]


class WebSearchRequest(BaseModel):
    text: str = ""
    page_size: int = Field(10000, ge=1, le=10000)
    page_num: int = Field(1, ge=1)
    index_names: Optional[Union[str, List[str]]] = None
    client: Optional[str] = None
    need_from_history: bool = False
    condition_dicts: List[Dict[str, Any]] = Field(default_factory=list)
    score_threshold: float = 5.3


class WebSearchResponse(BaseModel):
    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    current_count: int = 0


def _get_service():
    """Lazily build the ES8 KnowledgeService from the process runtime config."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                from kdb.crud.service import KnowledgeService

                config_path = os.environ.get(
                    "KDB_FORGE_CONFIG", "config/config_search_runtime.local.json"
                )
                _service = KnowledgeService.from_config(config_path)
                logger.info("retrieval service initialized from %s", config_path)
    return _service


def _require_search_auth(
    credentials: Optional[HTTPBasicCredentials] = Security(_basic),
) -> HTTPBasicCredentials:
    """Require credentials configured outside the repository and process argv."""
    expected_user = os.environ.get("KDB_SEARCH_BASIC_USER")
    expected_password = os.environ.get("KDB_SEARCH_BASIC_PASSWORD")
    if not expected_user or not expected_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="retrieval authentication is not configured",
        )
    if credentials is None or not (
        secrets.compare_digest(credentials.username, expected_user)
        and secrets.compare_digest(credentials.password, expected_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid retrieval credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials


def _shape_search_result(item: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the legacy /search result shaping after ES8 retrieval."""
    data_id = str(item.get("_id") or item.get("id") or "")
    dataset = item.get("dataset") or item.get("_index")
    score = float(item.get("similarity", 0.0) or 0.0)
    title = item.get("title", "") or ""
    content = item.get("content", "") or ""
    ext_info = item.get("ext_info") or {}
    primary_category = item.get("primary_category")
    synonyms = item.get("synonyms_title")
    if synonyms:
        if isinstance(synonyms, (list, tuple)):
            synonyms_text = "|".join(str(value) for value in synonyms)
        else:
            synonyms_text = str(synonyms)
        synonyms_title = f"{title}|同义question:{synonyms_text.replace(chr(10), '|')}"
    else:
        synonyms_title = title
    if item.get("data_type") == "qa" or item.get("title"):
        question = title
        answer = content
        combined = f"{synonyms_title}\n{content}"
    else:
        question = ""
        answer = None
        combined = content
    return {
        "id": data_id,
        "dataset": dataset,
        "insert_time": item.get("insert_time"),
        "update_time": item.get("update_time"),
        "q": question,
        "a": answer,
        "content": combined,
        "ext_info": ext_info,
        "score": score,
        "synonyms_title": synonyms_title,
        "metadata": ext_info,
        "primary_category": primary_category,
    }


def _without_embeddings(item: Dict[str, Any], need_from_history: bool) -> Dict[str, Any]:
    """Remove vector payloads and preserve the old web result shape."""
    result = {
        key: copy.deepcopy(value)
        for key, value in item.items()
        if "embedding" not in key.lower()
    }
    indexes = item.get("indexes") or []
    result["indexes"] = [
        entry.get("text")
        for entry in indexes
        if isinstance(entry, dict) and "text" in entry
    ]
    ext_info = result.get("ext_info")
    if isinstance(ext_info, dict) and not need_from_history:
        ext_info.pop("from_chat_history", None)
    return result


@router.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    _credentials: HTTPBasicCredentials = Depends(_require_search_auth),
) -> SearchResponse:
    """Run ES8 BM25/native-KNN retrieval with the legacy response contract."""
    if not request.text:
        raise HTTPException(status_code=400, detail="文本参数不能为空")
    try:
        docs, _total = _get_service().search_text(
            request.text,
            index_name=request.index_names,
            condition_dicts=copy.deepcopy(request.condition_dicts),
            size=request.top_k,
            search_type=request.search_type,
            data_type=request.data_type,
            use_synonyms=request.use_synonyms,
        )
        results = [_shape_search_result(item) for item in docs]
        if request.score_threshold > -1:
            results = [item for item in results if item["score"] > request.score_threshold]
        results.sort(key=lambda item: item["score"], reverse=True)
        return SearchResponse(results=results[: request.top_k])
    except HTTPException:
        raise
    except Exception as exc:  # avoid returning provider credentials in errors
        logger.exception("ES8 retrieval /search failed")
        raise HTTPException(status_code=503, detail="检索服务暂不可用") from exc


@router.post("/web_search", response_model=WebSearchResponse)
def web_search(
    request: WebSearchRequest,
    _credentials: HTTPBasicCredentials = Depends(_require_search_auth),
) -> WebSearchResponse:
    """Run ES8 BM25 pagination with the legacy web-search response contract."""
    try:
        docs, total = _get_service().web_search(
            request.text,
            client=request.client,
            index_name=request.index_names,
            condition_dicts=copy.deepcopy(request.condition_dicts),
            page_size=request.page_size,
            page_num=request.page_num,
            score_threshold=request.score_threshold,
        )
        results = [_without_embeddings(item, request.need_from_history) for item in docs]
        results.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        return WebSearchResponse(
            results=results,
            total_count=total,
            current_count=len(results),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("ES8 retrieval /web_search failed")
        raise HTTPException(status_code=503, detail="检索服务暂不可用") from exc


__all__ = ["router", "SearchRequest", "SearchResponse", "WebSearchRequest", "WebSearchResponse"]
