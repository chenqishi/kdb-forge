#!/bin/bash
# Wayfair 未答 query 知识库复检 - 定时入口
#
# crontab 示例（每周一 03:00 跑上一周）：
#   0 3 * * 1 /root/knowledge_database_builder/control_script/run_wayfair_unanswered_review.sh >> /root/knowledge_database_builder/logs/wayfair_unanswered_review.log 2>&1
#
# 注意：必须用 py38 环境（elasticsearch==7.10），默认 python3 的 ES 客户端不兼容。

set -euo pipefail

PROJECT_ROOT="/root/knowledge_database_builder"
PY="${WAYFAIR_REVIEW_PYTHON:-/root/miniconda3/envs/py38/bin/python}"
RECENT_DAYS="${WAYFAIR_REVIEW_RECENT_DAYS:-7}"

cd "$PROJECT_ROOT"
mkdir -p logs output/wayfair_unanswered

STAMP="$(date +%Y%m%d_%H%M%S)"
echo "[$(date '+%F %T')] wayfair 未答 query 复检开始 recent_days=${RECENT_DAYS} stamp=${STAMP}"

WORKERS="${WAYFAIR_REVIEW_WORKERS:-4}"

"$PY" query_understanding_analysis/wayfair_unanswered_review.py \
    --mode all \
    --recent-days "$RECENT_DAYS" \
    --workers "$WORKERS" \
    --stamp "$STAMP" \
    --log-level WARNING \
    --raw-path "output/wayfair_unanswered/unanswered_raw_${STAMP}.jsonl"

echo "[$(date '+%F %T')] 完成，产出见 output/wayfair_unanswered/report_${STAMP}.md"
