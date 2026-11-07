#!/usr/bin/env bash
# Payoneer chat mining 测试一键脚本。
#
# 用法：
#   bash tests/run_all_payoneer.sh           # 只跑非 LLM 单测（默认）
#   bash tests/run_all_payoneer.sh --llm     # 同时跑效果类（依赖 OpenRouter）
set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
RUN_LLM=0
if [[ "${1:-}" == "--llm" ]]; then
  RUN_LLM=1
fi

echo "[1/2] 单元测试 (非 LLM)"
$PY -m pytest tests/test_data_loader.py tests/test_conversation_segmenter.py -v

if [[ "$RUN_LLM" == "1" ]]; then
  echo "[2/2] 效果类测试 (LLM, 需联网)"
  $PY -m pytest tests/test_rag_suitability_cases.py tests/test_qa_extractor_cases.py -m llm -v
else
  echo "[2/2] 跳过 LLM 测试 (使用 --llm 启用)"
fi
