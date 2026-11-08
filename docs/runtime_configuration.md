# 运行与配置

在独立环境安装项目，确认所选解释器及各服务依赖。服务启动器只接受绝对路径的 `KDB_PYTHON`，保留调用者工作目录与业务参数；`--check` 必须放在服务参数之前，只检查本地依赖、配置和资源，不启动业务、不验证真实凭据或后端连通性。

```bash
export KDB_PYTHON=/absolute/path/to/venv/bin/python
scripts/services/retrieval.sh --check config/config_for_search_index.json
```

预检通过后，使用同一条命令去掉 `--check` 启动。解释器未配置时退出 64，资源检查失败时退出 78。检索要求 Elasticsearch Python SDK 8.17.x；不能根据环境目录名称推断实际 Python 或 SDK 版本。

| 服务 | 本地预检参数（接在对应启动器后） | 默认监听及运行资源 |
|---|---|---|
| `retrieval.sh` | `--check config/config_for_search_index.json` | `0.0.0.0:8003`；检索、embedding、可选相似度/类目配置。`SEARCH_SERVICE_WORKERS` 默认 4；初始化可能创建索引或验证 mapping |
| `off_task.sh` | `--check --script-dir "$PWD" --host 127.0.0.1 --port 6000` | 默认 `0.0.0.0:6000`；SQL 配置及可选任务资源配置，启动 SQL pool、队列 worker 和监控线程 |
| `crawler.sh` | `--check` | `0.0.0.0:6001`，原 debug 行为保留；调用接口才开始抓取与清洗 |
| `files.sh` | `--check --config config/minio_config.json --host 127.0.0.1 --port 8001` | 默认 `0.0.0.0:8000`；MinIO 配置。示例显式使用 8001，避免与代理端口冲突 |
| `multilingual.sh` | `--check --model_path resources/models/lid.176.ftz --host 127.0.0.1 --port 8007` | 默认 `0.0.0.0:8007`；需要真实 fastText 包与可加载模型 |
| `fastgpt_proxy.sh` | `--check` | `0.0.0.0:8000`，保留 reload 行为；配置 FastGPT 上游与认证 |

也可在已安装包的环境使用模块入口；六个核心服务使用下列模块命名方式：

```bash
python -m kdb.entrypoints.http.retrieval.app config/config_for_search_index.json
python -m kdb.entrypoints.http.tasks.app --script-dir "$PWD" --host 127.0.0.1 --port 6000
python -m kdb.entrypoints.http.files.app --config config/minio_config.json --host 127.0.0.1 --port 8001
```

直接模块启动会执行真实初始化，应先用对应启动器检查资源。HTTP 监听、SQL/ES 初始化、任务子进程和对象存储写入属于真实运行行为。

## 配置与静态资源

`config/*.example` 是格式示例，复制后填写当前环境的真实路径和凭据。相对配置路径按调用者工作目录解析；示例中的绝对路径需要替换。私有有效配置位于受忽略的 `private/runtime_config/`，包含保留下来的 `hardcoded_defaults.json`；缺文件或字段必须显式报错，不用空值或假凭据填充。新克隆需要单独配置这些资源。

按实际启用的服务选择模板，复制时去掉 `.example` 后缀，再填写真实值：

| 模板 | 目标与填写内容 |
|---|---|
| `config_for_search_index.json.example` | `config/config_for_search_index.json`；引擎、embedding、相似度配置路径及类目/多模态设置 |
| `config_es_engine.json.example` | `config/config_es_engine.json`；ES8.17 endpoint、凭据、索引、provider 路由与实际向量维度 |
| `config_ali_embedding.json.example` | `config/config_ali_embedding.json`；`DASHSCOPE_API_KEY`、模型与维度，`DASHSCOPE_ENCODING_FORMAT` 为 `float` |
| `config_dify_simility.json.example` | `config/config_dify_simility.json`；实际相似度工作流配置 |
| `mysql_conn_config.json.example` | `config/mysql_conn_config.json`；真实 SQL host/database/user/password |
| `minio_config.json.example` | `config/minio_config.json`；对象存储 endpoint、访问密钥、region 与寻址方式 |
| `llm_config.json.example` | `config/llm_config.json`；启用的模型 provider、endpoint、key、模型与回退设置 |
| `hardcoded_defaults.json.example` | **`private/runtime_config/hardcoded_defaults.json`**；按当前环境填入实际所需默认值，保留键与调用关系 |
| `prompt_file_map.txt.example`、`chatkonwledge_report_platform_map.txt.example` | `config/` 下同名无 `.example` 文件；按当前客户和已有 Prompt/报告目标填写，示例记录为合成数据 |

例如，仅准备检索模板时：

```bash
cp config/config_for_search_index.json.example config/config_for_search_index.json
cp config/config_es_engine.json.example config/config_es_engine.json
cp config/config_ali_embedding.json.example config/config_ali_embedding.json
mkdir -p private/runtime_config
cp config/hardcoded_defaults.json.example private/runtime_config/hardcoded_defaults.json
```

复制只建立文件格式，`SET_CURRENT_*`、`.invalid` 地址和示例索引均须按实际环境替换；模板文件存在或预检能解析 JSON，不计作真实依赖/凭据/模型已经补齐。只配置实际启用能力所需的值，不能猜测私有默认键的含义或用占位值启动真实业务。

检索主配置通过 `search_engine_config_path`、`embedding_config_path` 及可选 `simility_config_path` 指向实际配置。embedding 配置使用 `DASHSCOPE_API_KEY`；ES 引擎必须声明 `es_version: "8.17"`、目标索引与向量字段。

文件服务配置优先级为显式 `--config`、`MINIO_CONFIG_PATH`、项目内候选配置。连接字段为 `endpoint_url`、`access_key`、`secret_key`；遗漏字段可能使用保留的私有默认值，预检会提示，不能把存在检查当认证成功。FastGPT 缺 `config/config.json` 时同样可能沿用保留的上游和私有默认值，预检只提示，不请求上游。

Prompt 位于 `resources/prompts/`，共享路径工具为 `kdb.shared.config.paths`。模型、运行数据、输出、日志及缓存不随 Git 提交。任务配置中的客户、数据集和外部资源路径需要逐项核对。

当前未补齐语言服务的真实 fastText 依赖/模型。默认离线测试使用明确的模型/认证测试夹具，不能作为真实资源验收。

可选本地 LLM 增强通过显式 `KDB_LLM_CLIENT_PATH` 加载兼容插件；插件需提供 `configure_providers` 及支持 `image_urls`、返回三元组的 `request_llm`。配置使用 `KDB_LLM_CONFIG`（兼容显式 `AGENTS_LLM_CONFIG`）。未配置时沿既有降级流程，不默认引用其他工作区的客户端或模型配置。

缺口分析工具 `python -m kdb.mining.chat.query_analysis.align_gaps` 与 `python -m kdb.mining.chat.query_analysis.material_coverage` 必须显式提供 `--gap-csv`，或设置 `KDB_GAP_CSV`；不从其他工作区寻找默认输入。

## 独立辅助项目与成对发布

满意度、身份映射、独立运营统计与工作流评测位于 assistant-data-tools。版本配对为 assistant-data-tools 0.1.0 / kdb 0.2.0；辅助项目仅导入 kdb.shared，核心不导入辅助项目。

辅助项目使用自己的 config、data、output，CSAT 启动与认证模板见该项目 README。消费者依赖的 config/zhiqu_assistant_id_map.json 和 config/zhiqu_sid_to_robots_{client}.json 必须与生产脚本迁到同一配置根。核心任务报表和挖掘调度仍留在本项目。

部署时固定两个项目的版本或提交，分别准备真实配置；更新 CSAT 入口及映射 cron 的工作目录、解释器和输出路径后再切换调用，避免两套映射写入任务同时运行。回退时停止新调度，恢复旧入口及其原配置/产物目录。本次代码迁移不修改系统 cron、不部署、不启动真实服务。

当前运行根与资源从源码项目目录解析。发布采用配对源码检出及可编辑安装，不宣称单独 wheel 已包含完整运行资源。

远程聊天素材默认目录 `/root/dify/dify-on-wechat` 属于远端输入数据位置，保留在 chat/media 与 chat/sources/remote_messages；它不是本地代码依赖。可通过原 CHAT_IMAGE_REMOTE_ROOT 或 remote_path_root_dir 参数指定远端路径，不将远程数据目录重绑为本项目。
