# KDB Forge

知识库检索、知识挖掘和配套 HTTP 服务。正式代码集中在 `src/kdb`，检索后端为 Elasticsearch 8.17.x。

```text
src/kdb/
  services/       七个 HTTP 服务与独立协议适配
  retrieval/      应用接口、ES8 引擎和索引路由
  mining/         五条挖掘管道与处理阶段
  jobs/           定时任务
  shared/         配置、客户端、类目、文本和文件
  integrations/   外部系统适配
  reporting/      统计报表
scripts/          服务、任务、测试入口
resources/        Prompt 等静态资源
config/           可提交的配置示例
function_schema/  当前函数和 SQL 契约
tests/            离线测试
docs/             架构、接口和运行说明
```

在独立 Python 环境安装包，然后运行默认离线检查：

```bash
python -m pip install -e .
./run_offline_tests.sh -q
```

辅助服务和完整测试还需要各自依赖；安装及验证边界见[测试说明](docs/testing.md)。配置示例不含有效凭据，真实配置、模型和运行数据不入 Git。

服务启动器要求 `KDB_PYTHON` 为所选解释器的绝对路径，先执行本地预检：

```bash
KDB_PYTHON=/absolute/path/to/venv/bin/python scripts/services/retrieval.sh --check config/config_for_search_index.json
```

资源齐备后，使用相同参数去掉 `--check` 启动；也可在已安装环境中直接执行 `python -m kdb.services.retrieval.app config/config_for_search_index.json`。七服务参数见[运行配置](docs/runtime_configuration.md)。语言服务尚缺真实 fastText 依赖/模型，CSAT 尚缺真实认证配置，不能据离线测试视为可运行。

[架构](docs/Architecture_Overview_Diagram.md) · [HTTP API](docs/api.md) · [挖掘与任务队列](docs/pipelines.md) · [ES8 路由](docs/es8_retrieval.md) · [函数契约索引](function_schema/current_index.md)
