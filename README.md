# KDB Forge

知识检索、知识挖掘、多语言与公共能力。业务代码按职责组织，HTTP、CLI 和定时入口负责工程接线。对外沿用原业务协议，检索后端为 Elasticsearch 8.17.x。

```text
src/kdb/
  retrieval/      知识检索：查询、排序、入库、类目、维护、引擎
  mining/
    tasks/        任务队列、状态、资源、进程、提交与任务报表
    document/     文档与 Excel 挖掘
    web/          网页抓取、处理与挖掘
    chat/         对话读取、清洗、身份、生成与质量处理
    common/       共用的 LLM、质量、去重、schema、解析与切分
    bridges/      挖掘调用检索的唯一桥接处
  multilingual/  语言规则、模型加载、识别与标签
  shared/        对象存储、数据库、客户端、配置、类目、文本与文件
  entrypoints/   HTTP / CLI / scheduled 工程入口
  operations/    数据迁移等工程工具
scripts/          启动器、调度脚本、离线检查
resources/        Prompt 等静态资源
config/           可提交的配置示例
function_schema/  当前函数与 SQL 契约
tests/            离线测试
docs/             当前架构、接口和运行说明
```

满意度、外部身份映射和独立运营统计已拆为 **assistant-data-tools** 项目。核心不依赖它；它固定依赖 `kdb==0.2.0` 的公共模块。两个项目的配置、产物与测试分别管理，见[运行配置](docs/runtime_configuration.md)。

在独立 Python 环境安装包和测试依赖后执行离线检查。完整前提见[测试说明](docs/testing.md)；`test` 安装组覆盖 Python 测试依赖，系统组件另行准备：

```bash
python -m pip install -e ".[test]"
./run_offline_tests.sh -q
```

仅安装检索可用 `python -m pip install -e .`；其他服务使用 `.[files]`、`.[tasks]`、`.[web]`、`.[multilingual]` 等安装组，见[运行配置](docs/runtime_configuration.md)。测试依赖不包含真实模型、浏览器及认证。四个核心 HTTP 服务由启动器预检后运行，显式选择解释器：

```bash
KDB_PYTHON=/absolute/path/to/venv/bin/python scripts/services/retrieval.sh --check config/config_for_search_index.json
```

资源齐备后去掉 `--check` 启动。真实配置、凭据、模型与运行数据不入 Git。离线测试不能证明真实资源已就绪。

[业务架构](docs/Architecture_Overview_Diagram.md) · [HTTP API](docs/api.md) · [挖掘与任务队列](docs/pipelines.md) · [状态所有权](docs/state_ownership.md) · [ES8 路由](docs/es8_retrieval.md) · [函数契约](function_schema/current_index.md)
