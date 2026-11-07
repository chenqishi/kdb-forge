# 隔离候选：服务启动检查与交接

候选 `/root/kdb-forge-refactor-dev-20261105-restart`；源码基线f6a78084加四个挖掘修复。本文件给出具体可审阅命令，**不表示本次已获部署/重启/真实worker运行授权**。本次只执行了`--check`和禁网络/进程/外部写边界下的原`__main__`启动smoke；没有运行真正监听的服务或真实SQL/ES初始化。

## 显式解释器及本地preflight

七个`scripts/services/*.sh`不再默认选择PATH的裸python。必须设置`KDB_PYTHON`为绝对可执行路径；缺失/无效退出64。shell保留调用者cwd/PATH/argv，在原PYTHONPATH前加入候选src/root，exec preflight；preflight成功后exec同一解释器的原wrapper，信号和最终退出码沿exec传递，不增加后台任务或改成in-process业务调用。首参数`--check`只检查并打印安全JSON，永不启动；未满足条件退出78。原wrapper直接调用的业务默认/CLI行为没有重写。

现场独立探测（2026-11-06，仅代表检查时刻）：

| 解释器 | 实际Python / SDK | 用途与缺口 |
|---|---|---|
| PATH python=`/root/miniconda3/bin/python` | 3.12.4 / Elasticsearch9.4.1 | 不符合检索要求；Flask/fire/boto3等也不齐，不能沿用目录名或历史结果推断可用 |
| `/root/kdb-forge/.venv-es817/bin/python` | 3.12.4 / Elasticsearch8.17.2 | 检索`--check`通过；有独立venv site-packages，虽然二进制symlink可指同一基础Python。缺Flask/fire/boto3/fasttext，不用于宣称全部服务ready |
| `/root/miniconda3/envs/py38/bin/python` | **3.9.0** / Elasticsearch7.10.0 | 非检索辅助服务的现有依赖较齐；不直接用于检索。不能由`py38`名推断Python3.8 |
| `/root/knowledge_database_builder/.venv-es817/bin/python` | **不存在** | 历史runbook引用已失效，不应继续复制 |

preflight报告`sys.executable/sys.prefix/sys.base_prefix/interpreter_realpath`、SDK实际加载文件及版本；不能只看realpath把venv当系统环境。检索要求实际SDK8.17.x及配置es_version8.17，检查分服务进行，不要求每个辅助服务都安装ES SDK。本次不安装/更改任何共享环境；`private/test_dependencies`仅测试runner显式使用，不是runtime默认依赖。

下面的`cd`是调用者按旧入口相对路径契约主动选择工作目录，launcher不强行chdir。先执行检查：

```bash
cd /root/kdb-forge-refactor-dev-20261105-restart
KDB_PYTHON=/root/kdb-forge/.venv-es817/bin/python scripts/services/retrieval.sh --check config/config_for_search_index.json
KDB_PYTHON=/root/miniconda3/envs/py38/bin/python scripts/services/off_task.sh --check --script-dir /root/kdb-forge-refactor-dev-20261105-restart --host 127.0.0.1 --port 6000
KDB_PYTHON=/root/miniconda3/envs/py38/bin/python scripts/services/crawler.sh --check
KDB_PYTHON=/root/miniconda3/envs/py38/bin/python scripts/services/files.sh --check --config config/minio_config.json --host 127.0.0.1 --port 8001
KDB_PYTHON=/root/miniconda3/envs/py38/bin/python scripts/services/multilingual.sh --check --model_path model/lid.176.ftz --host 127.0.0.1 --port 8007
KDB_PYTHON=/root/miniconda3/envs/py38/bin/python scripts/services/csat.sh --check --mysql-config config/mysql_conn_config.json --auth-config config/csat_auth.json --port 7000
KDB_PYTHON=/root/kdb-forge/.venv-es817/bin/python scripts/services/fastgpt_proxy.sh --check
```

本轮retrieval/off_task/crawler/files/FastGPT五个本地资源检查通过；语言服务缺fasttext和真实模型、CSAT缺实际认证文件，二者明确失败。FastGPT缺cwd下config/config.json但沿用原内置上游和保真私有key fallback，预检明确warning，不新增必填配置禁用原功能。没有创建占位认证/模型/配置让检查变绿。preflight只证明本地依赖存在/选定SDK版本/JSON必需字段，不证明凭据有效、真实网络可达、模型可加载或服务能正式上线。

## 各服务实际入口与资源

| 服务 | 获准真实启动后用的命令（先对应`--check`通过，再去掉`--check`） | 必需资源与启动副作用 |
|---|---|---|
| retrieval | `KDB_PYTHON=/root/kdb-forge/.venv-es817/bin/python SEARCH_SERVICE_WORKERS=4 scripts/services/retrieval.sh config/config_for_search_index.json` | 旧脚本位置knowledge_database_search_service/src/knowledge_database_search_es.py；配置首位置参数必须提供。原固定0.0.0.0:8003；主进程先构造SDI/ModifyKnowledge，每真实worker再独立lifespan初始化。ES构造可ensure/create/mapping，必须在具体运行授权中处理，不因check通过自动放行。embedding/similarity配置、私有defaults及可选类目服务均按原读取顺序 |
| off_task | `KDB_PYTHON=/root/miniconda3/envs/py38/bin/python scripts/services/off_task.sh --script-dir /root/kdb-forge-refactor-dev-20261105-restart --host 127.0.0.1 --port 6000` | config/mysql_conn_config.json、可选task_resource_config.json；真实启动建立SQL pool、任务worker、monitor，可读写状态/启动挖掘子进程。队列/任务/产物交接未做时不可实启。--max-concurrency仍受原resource-config加载覆盖规则影响，未顺手修改 |
| crawler | `KDB_PYTHON=/root/miniconda3/envs/py38/bin/python scripts/services/crawler.sh` | 原0.0.0.0:6001/debug=True不变，CLI没有host/port覆盖参数。import构造ProcessLogitic；调用才抓取/清洗/写dataset。受控测试未运行这些外部业务 |
| files | `KDB_PYTHON=/root/miniconda3/envs/py38/bin/python scripts/services/files.sh --config config/minio_config.json --host 127.0.0.1 --port 8001` | 旧file_service/file_access_service.py；MinIO配置JSON按原MinioTools读取endpoint_url/access_key/secret_key；省略字段仍保留原私有默认值fallback并在preflight告知，原默认8000，本示例显式8001避开FastGPT原8000。配置路径按原优先级：显式--config > MINIO_CONFIG_PATH > 候选config列表。真实GET读对象、upload写对象；本轮不做真实对象写 |
| multilingual | 资源齐后：`KDB_PYTHON=/root/miniconda3/envs/py38/bin/python scripts/services/multilingual.sh --model_path model/lid.176.ftz --host 127.0.0.1 --port 8007` | 真实fasttext包及有效lid.176.ftz均缺，未安装/伪造。原__main__先检查文件并load_model，失败退出1；本轮仅模型依赖替身与缺失失败路径smoke |
| csat | 真实认证齐后：`KDB_PYTHON=/root/miniconda3/envs/py38/bin/python scripts/services/csat.sh --mysql-config config/mysql_conn_config.json --auth-config config/csat_auth.json --port 7000` | 原SQL pool与认证JSONclient→secret映射。实际auth文件缺失，不提供假secret。原绑定0.0.0.0，HTTP签名/300秒时窗不改。本轮synthetic auth仅临时测试夹具，未放候选config |
| fastgpt_proxy | `KDB_PYTHON=/root/kdb-forge/.venv-es817/bin/python scripts/services/fastgpt_proxy.sh` | 原8000代理，实际调用chat/completions，不是另一个ES检索；原reload=True行为不改。原wrapper缺cwd config/config.json时保留内置上游/private-default key fallback，preflight明确warning；若文件存在则按原字段knowledge_base_url检查。上游认证有效性未实测，--check不会调用chat/completions |

检索、FastGPT、crawler的原监听/重载机制保留，因此不能凭launcher的环境变量声称它们都只绑定loopback。要改监听行为属于另行明确的运行变更。此表不是一键启动所有服务的脚本。

## 私有路径与凭据

仅在候选private/runtime_config内，对确以`/root/dify/knowledge_database_builder/config/`开头且候选config已有同basename文件的指针，保真重绑到候选绝对路径；本轮2份私有JSON共4处。值、优先级和文件内容保留，旧快照/原工作区未改。元数据在`artifacts/refactor_review_remediation_20261106/launcher_private_path_rebindings.json`，不包含凭据值。未对未知路径、任务业务字段或缺失资源做大范围替换。

preflight不会连接SQL/ES/LLM/MinIO，也不会打印JSON字段值/URL/密钥；失败给角色/字段名/路径和类型。共享环境、现有服务、认证和真实数据未修改。

## 启动smoke实际范围

`tests/entry_smoke/test_launcher_startup.py`在强制socket/exec/subprocess/外部写审计下执行原wrapper的`__main__`：实际SDI配置解析与构造、ModifyKnowledge构造、SQL配置/pool接线、文件显式配置、语言模型加载/缺失退出、crawler processor构造和原server参数均经过。仅替换ES/SQL/Dify的外部构造边界、fasttext模型依赖、uvicorn.run/Flask.run和Thread.start；不启动真实监听、不执行worker/monitor target。

retrieval主进程初始化1次、uvicorn.run捕获1次；额外模拟一个worker import+lifespan初始化1次，重复进入同worker lifespan不重复初始化。它验证worker接线，不启动真实多进程。七服务原host/port/reload/workers参数保持。测试中所有auth/model/config为临时synthetic夹具，不是已补齐真实资源。

用独立offline runner明确测试私有SDK后执行本文件；测试证据与真实`--check`矩阵分开记录，不能把模型/SQL替身成功当正式环境ready。原__main__在同测试进程被runpy再次执行可能发出“已import模块”警告，已有原始输出保留，不会通过关闭安全guard掩盖失败。

## 定时与挖掘子进程（本次未改）

scripts/scheduled的两份shell仍exec原control_script下脚本，保持dirname/cwd、flock、退出75、日志及水位。AUTO_AUDIT_PYTHON、活动配置、cron仍须单独核验；本次不替它们安装venv或修改cron。scripts/mining/run_local_mining.sh及五controller的argv/shell、解释器/PATH/PYTHONPATH、超时/进程组机制均未改，仍会执行真实业务，不能裸跑当smoke。

## 发布与回退

候选未提交/未部署。后续需审阅具体版本、remote/main、私有配置、现有cwd/进程/环境和任务状态交接；不把代码快照等同SQL/ES/MinIO状态备份。真实部署由对应机器工作目录Git pull完成，不能复制覆盖/全量reset/clean/stash用户dirty。回退代码不自动撤销已发生数据/审核/水位副作用。启动命令只在具体服务和后端作用范围获准后使用。
