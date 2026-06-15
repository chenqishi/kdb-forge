#!/usr/bin/env bash
# 一键运行 rebuild 集成测试（真实 ES + DashScope）。
# 用法：
#   ./run_tests.sh                 # 跑全部 integration 测试
#   ./run_tests.sh -k roundtrip    # 透传 pytest 参数
#   PYTHON=/path/to/python ./run_tests.sh   # 指定 python 解释器（需含 elasticsearch 等旧项目依赖）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 旧项目根（被 import 复用）；可用环境变量覆盖
export KDB_LEGACY_ROOT="${KDB_LEGACY_ROOT:-/Users/chenqishi/stone_fish/knowledge_database_builder}"
# 让 `import kdb` 与旧模块都能解析（无需安装）
export PYTHONPATH="${HERE}/src:${KDB_LEGACY_ROOT}:${PYTHONPATH:-}"

# 选择 python：$PYTHON 优先；否则探测含 elasticsearch 的可用解释器；都没有就用 python
choose_python() {
    if [[ -n "${PYTHON:-}" ]] && command -v "${PYTHON}" >/dev/null 2>&1; then
        echo "${PYTHON}"; return
    fi
    for cand in /opt/anaconda3/envs/py39/bin/python /opt/anaconda3/envs/py310/bin/python python3 python; do
        if command -v "${cand}" >/dev/null 2>&1 && \
           "${cand}" -c "import elasticsearch" >/dev/null 2>&1; then
            echo "${cand}"; return
        fi
    done
    echo "python"
}
PYBIN="$(choose_python)"

echo "[run_tests] KDB_LEGACY_ROOT=${KDB_LEGACY_ROOT}"
echo "[run_tests] PYTHONPATH=${PYTHONPATH}"
echo "[run_tests] python=${PYBIN}"

cd "${HERE}"
"${PYBIN}" -m pytest -v -m integration tests "$@"
