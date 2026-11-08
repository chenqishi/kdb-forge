from __future__ import annotations
from kdb.retrieval.maintenance._logging import logger
from kdb.retrieval.maintenance.auto_audit import AutoAuditProcessor
from kdb.retrieval.maintenance.auto_audit import resolve_time_threshold
from pathlib import Path
import argparse
import json
import logging

def main(argv=None) -> int:
    """Keep legacy CLI options and return a nonzero status on incomplete work."""
    parser = argparse.ArgumentParser(description="通过统一引擎接口执行定时自动审核")
    config = parser.add_mutually_exclusive_group(required=True)
    config.add_argument("--config", help="原引擎配置路径（兼容旧调用）")
    config.add_argument("--search-config", help="线上业务配置，读取 search_engine_config_path")
    targets = parser.add_mutually_exclusive_group(required=True)
    targets.add_argument("--index", help="明确索引名或 all（仅配置provider内按路由归属枚举）")
    targets.add_argument("--indexes", help="明确索引列表，逗号分隔")
    parser.add_argument("--from-type-norm", required=True)
    parser.add_argument("--hours", type=int, default=None)
    parser.add_argument("--minutes", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=100, help="保留兼容；实际批次由 --scroll-size 控制")
    parser.add_argument("--scroll-size", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--exclude-system", action="store_true", default=True)
    parser.add_argument("--report-json", help="可选审核结果JSON路径，不保存凭据/正文/向量")
    args = parser.parse_args(argv)
    try:
        hours, minutes = resolve_time_threshold(args.hours, args.minutes)
        if args.scroll_size <= 0 or args.batch_size <= 0:
            raise ValueError("批次大小必须大于0")
        sources = [item.strip() for item in args.from_type_norm.split(",")]
        if not all(sources):
            raise ValueError("from-type-norm 不能为空")
    except ValueError as exc:
        parser.error(str(exc))
    processor = None
    try:
        processor = AutoAuditProcessor(args.config, search_config_path=args.search_config)
        names = processor.get_all_indexes(args.exclude_system) if args.index == "all" else (
            [args.index] if args.index else [name.strip() for name in args.indexes.split(",")])
        if not names:
            raise RuntimeError("未发现可处理索引")
        result = processor.auto_audit_for_indexes(names, sources, hours, minutes, args.batch_size, args.scroll_size, args.dry_run)
        serialized = json.dumps(result, ensure_ascii=False, indent=2)
        print(serialized)
        if args.report_json:
            Path(args.report_json).write_text(serialized + "\n", encoding="utf-8")
        return int(result["summary"]["failed_count"] > 0)
    except Exception as exc:
        logger.error("审核未完成，错误类型=%s；未执行自动回退", type(exc).__name__)
        return 1
    finally:
        if processor is not None:
            processor.close()


if __name__ == "__main__":
    raise SystemExit(main())
