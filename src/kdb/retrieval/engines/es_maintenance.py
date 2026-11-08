"""Shared maintenance operations for the existing engine implementations.

Audit policy belongs to the caller. Connection selection and checked native
updates belong here, alongside the other engine data operations.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Mapping
from typing import Any
from typing import Dict
from typing import List
from kdb.retrieval.engines.es_count_utils import complete_count

logger = logging.getLogger(__name__)


class MaintenanceUpdateError(RuntimeError):
    """Expose safe failure kind and confirmed counters, never document source."""

    def __init__(self, kind: str, payload: Mapping = None):
        self.kind = kind if isinstance(kind, str) and re.fullmatch(r"[a-zA-Z0-9_]+", kind) else "unknown"
        self.confirmed = None
        payload = payload or {}
        counters = {key: payload.get(key, 0 if key == "version_conflicts" else None)
                    for key in ("updated", "total", "version_conflicts")}
        if (all(type(value) is int and value >= 0 for value in counters.values())
                and counters["updated"] <= counters["total"]):
            failures = payload.get("failures", [])
            if isinstance(failures, list):
                self.confirmed = dict(counters, failures=[{"type": "item_failure"} for _ in failures])
        super().__init__("维护更新失败 type=" + self.kind + "；已成功部分不会回滚")


def response_body(response: Any) -> Dict[str, Any]:
    """Unwrap real ES8 responses without accepting an unknown success envelope."""
    body = getattr(response, "body", response)
    if not isinstance(body, Mapping):
        raise RuntimeError("维护操作返回了非对象响应")
    return dict(body)


def exact_index(index_name: str) -> str:
    """Require one explicit index, never an all-index expression for a mutation."""
    if (not isinstance(index_name, str) or not index_name.strip()
            or index_name != index_name.strip() or index_name in {"_all", "."}
            or any(char in index_name for char in "*,?[]/: ")):
        raise ValueError("维护操作必须指定单个明确索引名")
    return index_name


def is_write_size_error(value: Any) -> bool:
    """Recognize only the previously observed server-side write-size rejection."""
    text = (json.dumps(value, ensure_ascii=False) if isinstance(value, Mapping) else str(value)).lower()
    return any(token in text for token in (
        "max_write_size_per_request", "write_size blocked", "write.max_size_per_request",
    ))


def wait_for_update_task(client: Any, task_id: str, poll_interval: float = 5.0,
                         timeout_seconds: float = 3600) -> Dict[str, Any]:
    """Wait for the actual terminal response, preserving task-level errors."""
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("无效的更新task ID")
    deadline = time.monotonic() + timeout_seconds
    while True:
        result = response_body(client.tasks.get(task_id=task_id))
        if result.get("completed") is True:
            return result
        if result.get("error") or not isinstance(result.get("completed"), bool):
            raise RuntimeError("更新task状态无效；不能确认完成")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("等待更新task超时；已成功部分不会回滚")
        time.sleep(min(poll_interval, remaining))


def run_native_update(client: Any, request: Dict[str, Any], *, scroll_size: int = 30,
                      request_timeout_seconds: int = 3600, max_attempts: int = 12,
                      client_api: int = 8) -> Dict[str, Any]:
    """Run a checked, bounded native update; don't replay an uncertain write."""
    if scroll_size < 1 or max_attempts < 1 or request_timeout_seconds <= 0:
        raise ValueError("维护更新批次、超时与重试次数必须为正数")
    current_scroll = scroll_size
    transport = client.options(request_timeout=request_timeout_seconds, max_retries=0, retry_on_timeout=False) if client_api == 8 else client
    for attempt in range(max_attempts):
        options = dict(request, scroll_size=current_scroll)
        if client_api != 8:
            options["request_timeout"] = request_timeout_seconds
        # A transport exception has an unknown write outcome. Never issue a
        # second mutation merely because a timeout message looks retryable.
        result = response_body(transport.update_by_query(**options))
        if isinstance(result.get("task"), str):
            result = wait_for_update_task(transport, result["task"], timeout_seconds=request_timeout_seconds)
        task = result.get("task")
        status = task.get("status", {}) if isinstance(task, Mapping) else {}
        payload = result.get("response", status if result.get("error") else result)
        if not isinstance(payload, Mapping):
            raise RuntimeError("更新响应内容无效；已成功部分不会回滚")
        error = result.get("error") or payload.get("error")
        if error:
            reported_updates = [part["updated"] for part in (payload, status) if "updated" in part]
            confirmed_zero = bool(reported_updates) and all(type(value) is int and value == 0 for value in reported_updates)
            progressed = any(part.get(key, 0) for part in (payload, status) for key in (
                "updated", "deleted", "noops", "version_conflicts",
            ))
            if is_write_size_error(error) and confirmed_zero and not progressed and current_scroll > 1 and attempt + 1 < max_attempts:
                current_scroll = max(1, current_scroll // 2)
                logger.warning("维护更新写入大小被拒，零进展，减小scroll_size=%s后重试", current_scroll)
                continue
            raise MaintenanceUpdateError(error.get("type", "native_error") if isinstance(error, Mapping) else "native_error", payload)
        if (payload.get("timed_out") or (any(key in result for key in ("task", "response", "completed"))
                                        and result.get("completed") is not True)):
            raise RuntimeError("维护更新未完整完成；已成功部分不会回滚")
        output: Dict[str, Any] = {}
        for key in ("updated", "total", "version_conflicts"):
            value = payload.get(key, 0 if key == "version_conflicts" else None)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeError("维护更新缺少有效统计；不能声明成功")
            output[key] = value
        if output["updated"] > output["total"]:
            raise RuntimeError("维护更新成功数超过处理数；统计无效")
        failures = payload.get("failures", [])
        if not isinstance(failures, list):
            raise RuntimeError("维护更新失败列表无效")
        output["failures"] = failures
        if failures:
            raise MaintenanceUpdateError("bulk_failure", payload)
        return output
    raise RuntimeError("维护更新重试次数耗尽")


class EngineMaintenanceMixin:
    """Small shared operations, exposed through the normal engine factory."""

    def _maintenance_client(self, index_name: str) -> Any:
        """Select the same connection as retrieval without ensure/create."""
        exact_index(index_name)
        return self.get_client_by_index(index_name) if hasattr(self, "router") else self.es

    def get_index_provider(self, index_name: str) -> str:
        """Describe route ownership without exposing connection credentials."""
        exact_index(index_name)
        return self.router.resolve_provider(index_name) if hasattr(self, "router") else "legacy"

    def index_exists(self, index_name: str) -> bool:
        """Check existence on the authoritative provider, without creating it."""
        return bool(self._maintenance_client(index_name).indices.exists(index=index_name))

    def get_all_indexes(self, exclude_system: bool = True) -> List[str]:
        """Inventory every provider, retaining only indexes owned by that route."""
        router = getattr(self, "router", None)
        clients = [(name, router.get_client_by_provider(name)) for name in router.providers] if router else [("legacy", self.es)]
        indexes = set()
        for provider, client in clients:
            rows = getattr(response := client.cat.indices(format="json", h="index"), "body", response)
            if not isinstance(rows, list):
                raise RuntimeError("索引清单响应无效，不能继续全量维护")
            for row in rows:
                if not isinstance(row, Mapping) or not isinstance(row.get("index"), str):
                    raise RuntimeError("索引清单条目无效")
                name = row["index"]
                if exclude_system and name.startswith("."):
                    continue
                exact_index(name)
                if router is None or router.resolve_provider(name) == provider:
                    indexes.add(name)
        return sorted(indexes)

    def field_value_counts(self, index_name: str, field: str, query: Dict[str, Any], size: int = 10) -> Dict[str, int]:
        """Return complete bounded terms counts, rejecting shard errors/truncation."""
        client = self._maintenance_client(index_name)
        aggregation = {"values": {"terms": {"field": field, "size": size, "show_term_doc_count_error": True}}}
        if hasattr(self, "router"):
            response = client.search(index=index_name, query=query, size=0, aggregations=aggregation)
        else:
            response = client.search(index=index_name, body={"query": query, "size": 0, "aggs": aggregation})
        result = response_body(response)
        complete_count(dict(result, count=0))
        values = result.get("aggregations", {}).get("values", {})
        if (not isinstance(values.get("buckets"), list) or values.get("sum_other_doc_count", 0)
                or values.get("doc_count_error_upper_bound", 0)):
            raise RuntimeError("维护聚合截断或存在计数误差")
        counts = {}
        for item in values["buckets"]:
            count = item.get("doc_count")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0 or item.get("doc_count_error_upper_bound", 0):
                raise RuntimeError("维护聚合bucket无效")
            counts[str(item["key"])] = count
        return counts

    def configure_maintenance_updates(self, scroll_size: int = 30, request_timeout_seconds: int = 3600) -> None:
        """Apply explicit batching only to a maintenance factory instance."""
        if not getattr(self, "_maintenance_mode", False):
            raise RuntimeError("仅维护模式可以配置维护更新")
        if scroll_size < 1 or request_timeout_seconds <= 0:
            raise ValueError("维护更新批次和超时必须为正数")
        self._maintenance_update_options = {"scroll_size": scroll_size, "request_timeout_seconds": request_timeout_seconds}

    def close(self) -> None:
        """Release the legacy connection pool; ES8 retains its existing close()."""
        self.es.close()
