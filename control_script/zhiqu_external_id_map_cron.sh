#!/bin/bash
# 致趣 external_id → 本系统 cid 映射 cron（每天凌晨 2 点一次）
#
# 部署 crontab 示例：
#   0 2 * * * /path/to/knowledge_database_builder/control_script/zhiqu_external_id_map_cron.sh
#
# 前置条件：
#   - config/zhiqu_credentials.json    存在（凭据）
#   - config/zhiqu_assistant_id_map.json 存在（人工触发 build_zhiqu_assistant_id_map.py 生成）
#   - config/mysql_conn_config.json    存在（rufitai DB）

set -eu

# 切到仓库根目录（control_script 上一级）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

CLIENT="${1:-mercado}"
TS="$(date '+%Y%m%d_%H%M%S')"
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/zhiqu_external_id_map_${CLIENT}_${TS}.log"

echo "[$(date '+%F %T')] start zhiqu external_id map cron client=$CLIENT" >> "$LOG"
python3 data_control_tools/build_zhiqu_external_id_map.py --client "$CLIENT" >> "$LOG" 2>&1
echo "[$(date '+%F %T')] done" >> "$LOG"
