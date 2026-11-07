# 候选默认离线测试

从候选根目录运行：

```bash
./run_offline_tests.sh -q
./run_tests.sh -q
python -m pytest -q
```

前两个命令等价。解释器由`KDB_TEST_PYTHON`显式选择，未设置时使用PATH的python3；这只用于测试，服务launcher另行强制设置绝对路径的`KDB_PYTHON`。所选环境必须具备测试依赖。runner会打印实际Python、ES SDK版本和加载位置，不依据环境目录名猜版本。

候选`private/test_dependencies`存在时，测试明确将它放入依赖路径并验证Elasticsearch8.17.x；该目录受忽略，不能据此宣称Git克隆已有依赖。可复现安装清单与隔离准备方式见`requirements-offline.txt`，不要修改共享Python包，也不要将该测试依赖路径作为服务默认环境。

默认只收集`tests/entry_smoke`与`tests/offline`，保留`baseline_legacy`、`baseline_forge`供显式选择。直接`pytest tests`是扩大到历史测试，可能出现历史失败/环境错误，不属于默认通过结果。原带macOS路径和真实integration选择的runner完整保存在`archive/forge_pre_refactor/tools/run_tests.integration.original.sh.txt`，不可执行，不再是测试入口。

## 外部操作边界

支持的runner在导入pytest和业务模块前安装进程生命周期审计，禁TCP/UDP连接、监听、DNS及子进程/exec/fork；允许TestClient内部socketpair。文件读取允许，写入限候选、系统临时目录，以及显式的`KDB_OFFLINE_OUTPUT_DIR`。写报告到其它目录须先指定该变量。此边界防止普通Python标准库调用意外连接后端；不是对恶意本机代码/ctypes的隔离承诺。

根`conftest.py`为正常裸pytest安装同一边界；裸pytest使用`--noconftest`会由调用者主动绕开它。支持的runner独立安装边界，即使转发该参数仍生效，并关闭pytest自动插件加载，减少机器插件造成的环境差异。不要把扩大写目录或禁用conftest作为修复测试失败的方法。

启动测试执行原wrapper的`__main__`，替换外部ES/SQL/Dify构造、模型和serve/thread边界；检查实际配置接线、初始化次数、原host/port/worker参数。没有真实监听、任务执行或凭据验证。真实资源状态须以服务`--check`和启动说明为准。

## 显式回归组

```bash
./run_offline_tests.sh --group retrieval -q
KDB_TEST_PYTHON=/root/miniconda3/envs/py38/bin/python ./run_offline_tests.sh --group mining -q
KDB_TEST_PYTHON=/root/miniconda3/envs/py38/bin/python ./run_offline_tests.sh --group audit -q
./run_offline_tests.sh --group history tests/baseline_legacy/test_default_category.py -q
```

组内文件列表以`scripts/testing/offline_runner.py`为准。mining和audit各明确排除一个断言需要真实子进程的原历史测试（Excel带空格argv子进程、shell日志/flock子进程），runner打印完整用例ID和原因；原测试与断言保留，显式history调用仍受守卫阻止，不能算成这两项已通过。首次受阻失败证据保留。

`--group all`只是这些选择组的并集，不代表所有历史测试；历史用例在同一进程混跑还可能受测试替身状态影响。本次报告分别记录实际执行命令、通过和排除数，不把曾有失败的历史套件改称全绿。

外置JUnit示例：

```bash
KDB_OFFLINE_OUTPUT_DIR=/root/kdb-forge/artifacts/refactor_review_remediation_20261106 ./run_offline_tests.sh -q --junitxml=/root/kdb-forge/artifacts/refactor_review_remediation_20261106/example.xml
```

测试的快照/缓存/临时数据不得进入Git；`.gitignore`保留这些现场。未授权的线上写入、知识生成和生产重启都不属于离线测试步骤。

## 本轮依赖安装的准确范围

`requirements-offline.txt`是**增量测试依赖清单**，锁24个公开发行包（其中ES8.17.2/elastic-transport8.19.0原已在测试目录；其余为真实Flask/Werkzeug及启动import链所需boto3、PyMuPDF、psutil等及其传递依赖）。它不是fresh clone的完整环境lock，也不等同生产requirements。没有用fakeFlask、skip或改断言来通过启动测试。

前置：选择已有Python3.12测试环境，具备项目基础依赖和pytest；本轮实测基础包如下。它们不是这次pip target新增的包，其传递依赖由该既有环境提供：

| 基础发行包 | 本轮默认Python3.12环境版本 |
|---|---|
| pytest | 9.1.1 |
| fastapi / pydantic / uvicorn | 0.138.1 / 2.13.4 / 0.49.0 |
| numpy / requests / httpx / jieba | 2.5.0 / 2.32.2 / 0.28.1 / 0.42.1 |
| mysql-connector-python / python-docx | 9.7.0 / 1.2.0 |
| Pillow / lxml | 12.3.0 / 6.1.2 |

此外crawler启动import需要该Python自带的tkinter/Tcl-Tk；pip清单不安装系统GUI库。真正fasttext/模型仍不在测试依赖清单，只有语言启动测试在已标明的模型依赖边界使用替身。服务`--check`不自动加载此测试目录，也不因离线通过变成正式环境ready。

在满足前置的**所选测试解释器**下，从候选根执行增量安装：

```bash
python3 -m pip install --target "$PWD/private/test_dependencies" -r requirements-offline.txt
./run_offline_tests.sh -q
```

如果选的是自己的隔离venv，应把第一行python3和`KDB_TEST_PYTHON`都指向同一个venv解释器。该命令只安装到候选private测试目录，不能去掉`--target`而修改共享环境；不在service launcher中自动添加它。现有同版本ES目录未被覆盖，pip相关warning保留。

本轮用上述target安装后，PATH Python3.12默认runner实测85 passed；另外Python3.9原启动组14项也通过。可复现范围是**已有上述基础测试环境 + 锁定的增量依赖**；未在空白机器全新创建环境，不能把这一结果宣称为fresh clone自足。安装wheel/hash与基础版本分别记录在整改证据`default_offline_fixed_dependencies.json`及`default_offline_base_environment.json`。原79 passed/6 failed的缺Flask证据保留为default_offline_final，不覆盖。
