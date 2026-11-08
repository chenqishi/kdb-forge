from __future__ import annotations
from datetime import datetime
from datetime import timedelta
from kdb.retrieval.maintenance._logging import logger
from kdb.retrieval.engines.es_maintenance import MaintenanceUpdateError
from kdb.retrieval.engines.es_maintenance import exact_index
from kdb.retrieval.engines.factory import EsSearchInterface
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
import hashlib
import json
import logging

def format_time_window(hours: int = 0, minutes: int = 0) -> str:
    """Describe the unchanged hour/minute eligibility delay."""
    if hours and minutes:
        return f"{hours}小时{minutes}分钟"
    if hours:
        return f"{hours}小时"
    if minutes:
        return f"{minutes}分钟"
    return "0（不设延迟，审核全部待审文档）"


def resolve_time_threshold(hours=None, minutes=None):
    """Only use the 24h default when neither option was supplied."""
    if hours is None and minutes is None:
        return 24, 0
    hours, minutes = hours or 0, minutes or 0
    if hours < 0 or minutes < 0:
        raise ValueError("--hours / --minutes 不能为负数")
    return hours, minutes


def load_engine_config_path(config_path: Optional[str], search_config_path: Optional[str]) -> Path:
    """Resolve exactly one existing config; follow the same service pointer."""
    if bool(config_path) == bool(search_config_path):
        raise ValueError("必须且只能指定 --config 或 --search-config")
    if config_path:
        path = Path(config_path).resolve()
    else:
        search_path = Path(search_config_path).resolve()
        if search_path.stat().st_size > 1024 * 1024:
            raise ValueError("业务配置文件过大")
        config = json.loads(search_path.read_text(encoding="utf-8"))
        pointer = config.get("search_engine_config_path")
        if not isinstance(pointer, str) or not pointer.strip():
            raise ValueError("业务配置缺少 search_engine_config_path")
        path = Path(pointer)
        if not path.is_absolute():
            # Service configs historically resolve relative paths from cwd.
            # Never silently choose a different sibling file on a miss.
            path = Path.cwd() / path
        path = path.resolve()
    if not path.is_file():
        raise ValueError("引擎配置文件不存在")
    return path


class AutoAuditProcessor:
    """Audit rules only; all reads and writes use the shared engine factory."""

    def __init__(self, config_path: Optional[str] = None, *, search_config_path: Optional[str] = None,
                 engine: Any = None, now: Optional[datetime] = None):
        self.config_path = str(load_engine_config_path(config_path, search_config_path))
        self.search_config_path = search_config_path
        path = Path(self.config_path)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("引擎配置文件过大")
        raw = path.read_bytes()
        self.config = json.loads(raw)
        self.config_sha256 = hashlib.sha256(raw).hexdigest()
        self.started_at = now or datetime.now()
        self.engine = engine if engine is not None else EsSearchInterface(
            config_path=self.config_path, maintenance_mode=True,
        )
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.config_sha256:
            self.engine.close()
            raise RuntimeError("初始化期间引擎配置发生变化，停止审核")
        self.es_version = self.engine.es_version
        logger.info("审核配置=%s sha256=%s engine=%s", self.config_path, self.config_sha256, self.es_version)

    def get_all_indexes(self, exclude_system: bool = True) -> List[str]:
        """Use the unified inventory, including every authoritative provider."""
        return self.engine.get_all_indexes(exclude_system=exclude_system)

    def _queries(self, from_type_norm: List[str], hours: int, minutes: int) -> Dict[str, Any]:
        """Build the original three rules using one fixed run eligibility time."""
        if not from_type_norm or any(not item for item in from_type_norm):
            raise ValueError("from_type_norm 不能为空")
        resolve_time_threshold(hours, minutes)
        threshold = (self.started_at - timedelta(hours=hours, minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
        source = ({"term": {"from_type_norm": from_type_norm[0]}} if len(from_type_norm) == 1
                  else {"terms": {"from_type_norm": list(from_type_norm)}})
        must = [source, {"term": {"audit_result": -1}}, {"range": {"insert_time": {"lte": threshold}}}]
        return {
            "threshold": threshold,
            "base": {"bool": {"must": must}},
            "high": {"bool": {"must": must + [{"term": {"quality_level": "high"}}]}},
            "other": {"bool": {"must": must, "must_not": [
                {"term": {"quality_level": "high"}}, {"term": {"data_type": "segment"}},
            ]}},
        }

    def check_pending_audit_docs(self, index_name: str, from_type_norm: List[str],
                                 hours: int = 24, minutes: int = 0) -> Dict[str, Any]:
        """Count exact eligible records without applying retrieval defaults."""
        exact_index(index_name)
        queries = self._queries(from_type_norm, hours, minutes)
        total = self.engine.count_by_query(index_name, queries["base"], require_complete=True)
        quality = self.engine.field_value_counts(index_name, "quality_level", queries["base"]) if total else {}
        high = self.engine.count_by_query(index_name, queries["high"], require_complete=True) if total else 0
        other = self.engine.count_by_query(index_name, queries["other"], require_complete=True) if total else 0
        deleted_query = {"bool": {"must": [queries["base"], {"term": {"del_flag": 1}}]}}
        deleted = self.engine.count_by_query(index_name, deleted_query, require_complete=True) if total else 0
        return {
            "index_name": index_name, "provider": self.engine.get_index_provider(index_name),
            "from_type_norm": list(from_type_norm), "total_count": total,
            "quality_distribution": quality, "high_count": high, "other_count": other,
            "unchanged_count": max(0, total - high - other), "soft_deleted_count": deleted,
            "threshold_hours": hours, "threshold_minutes": minutes,
            "threshold_desc": format_time_window(hours, minutes), "threshold_time": queries["threshold"],
        }

    def _run_update_by_query(self, index_name: str, query: Dict[str, Any], update_fields: Dict[str, Any],
                             scroll_size: int, request_timeout_seconds: int = 3600) -> Dict[str, Any]:
        """Pass assignments to the same engine used by other data operations."""
        self.engine.configure_maintenance_updates(scroll_size, request_timeout_seconds)
        return self.engine.update_by_query(index_name, query, update_fields)

    def auto_audit_documents(self, index_name: str, from_type_norm: List[str], hours: int = 24,
                             minutes: int = 0, batch_size: int = 100, scroll_size: int = 30,
                             dry_run: bool = False) -> Dict[str, Any]:
        """Apply only the original two assignments and verify the remaining set."""
        before = self.check_pending_audit_docs(index_name, from_type_norm, hours, minutes)
        if dry_run:
            return {"mode": "dry_run", "stats": before}
        queries = self._queries(from_type_norm, hours, minutes)
        empty = {"updated": 0, "total": 0, "version_conflicts": 0, "failures": []}
        high, other = dict(empty), dict(empty)
        error = None
        stage = "high"
        remaining = None
        try:
            if before["high_count"]:
                high = self._run_update_by_query(index_name, queries["high"], {"audit_result": 2}, scroll_size)
            stage = "other"
            if before["other_count"]:
                other = self._run_update_by_query(index_name, queries["other"], {"audit_result": 0}, scroll_size)
            stage = "verification"
            remaining = sum(self.engine.count_by_query(index_name, queries[key], require_complete=True) for key in ("high", "other"))
        except Exception as exc:
            if isinstance(exc, MaintenanceUpdateError) and exc.confirmed is not None:
                if stage == "high": high = exc.confirmed
                if stage == "other": other = exc.confirmed
            error = {"stage": stage, "error_type": type(exc).__name__,
                     "cause_kind": exc.kind if isinstance(exc, MaintenanceUpdateError) else None,
                     "message": "未完整完成；存在未知写入数量时需按固定阈值重新核对"}
        conflicts = high.get("version_conflicts", 0) + other.get("version_conflicts", 0)
        failures = len(high.get("failures", [])) + len(other.get("failures", []))
        return {
            "index_name": index_name, "provider": before["provider"], "from_type_norm": list(from_type_norm),
            "threshold_hours": hours, "threshold_minutes": minutes, "threshold_time": queries["threshold"],
            "threshold_desc": format_time_window(hours, minutes), "stats_before": before,
            "high_quality": high, "other_quality": other,
            "total_updated": high["updated"] + other["updated"], "total_failures": failures,
            "version_conflicts": conflicts, "remaining_eligible": remaining,
            "complete": error is None and remaining == 0 and conflicts == 0 and failures == 0,
            "accounting_complete": error is None, "error": error,
        }

    def auto_audit_for_indexes(self, index_names: List[str], from_type_norm: List[str], hours: int = 24,
                               minutes: int = 0, batch_size: int = 50, scroll_size: int = 30,
                               dry_run: bool = False) -> Dict[str, Any]:
        """Report every failure/partial update instead of claiming overall success."""
        names = list(dict.fromkeys(index_names))
        summary = {"total_indexes": len(names), "success_count": 0, "failed_count": 0,
                   "skipped_count": 0, "dry_run_count": 0, "total_docs_updated": 0,
                   "total_high_quality": 0, "total_other_quality": 0}
        results = {}
        for index_name in names:
            try:
                exact_index(index_name)
                if not self.engine.index_exists(index_name):
                    raise RuntimeError("目标索引不存在；不会创建或回退到其他集群")
                result = self.auto_audit_documents(index_name, from_type_norm, hours, minutes, batch_size, scroll_size, dry_run)
                if dry_run:
                    status = "dry_run"
                    summary["dry_run_count"] += 1
                elif not result["complete"]:
                    status = "partial"
                    summary["failed_count"] += 1
                elif result["stats_before"]["high_count"] + result["stats_before"]["other_count"] == 0:
                    status = "skipped"
                    summary["skipped_count"] += 1
                else:
                    status = "success"
                    summary["success_count"] += 1
                if not dry_run:
                    summary["total_docs_updated"] += result["total_updated"]
                    summary["total_high_quality"] += result["high_quality"]["updated"]
                    summary["total_other_quality"] += result["other_quality"]["updated"]
                results[index_name] = {"status": status, "result": result}
                logger.info("审核结果 index=%s provider=%s status=%s", index_name, self.engine.get_index_provider(index_name), status)
            except Exception as exc:
                # Don't expose authenticated connection options or document source.
                logger.error("审核失败 index=%s type=%s；需核对剩余集", index_name, type(exc).__name__)
                results[index_name] = {"status": "failed", "error_type": type(exc).__name__,
                                       "error": "审核未完整完成，需核对日志与剩余待审；已成功部分不会回滚"}
                summary["failed_count"] += 1
        return {"summary": summary, "details": results, "config_path": self.config_path,
                "config_sha256": self.config_sha256, "es_version": self.es_version,
                "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S")}

    def close(self) -> None:
        """Release connections without changing any service lifecycle."""
        self.engine.close()


"""Apply the existing delayed audit policy through the shared engine interface."""


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
