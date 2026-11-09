# 测试

默认验证入口在导入业务代码前禁止网络、监听、DNS、子进程和外部写入，测试产物限项目、系统临时目录及显式指定的输出目录。TestClient 的内部 socketpair 允许使用。

```bash
./run_offline_tests.sh -q
./run_tests.sh -q
python -m pytest -q
```

前两个入口等价；测试解释器由 `KDB_TEST_PYTHON` 指定，缺省为 PATH 的 `python3`。它与服务启动所需的 `KDB_PYTHON` 分开。默认收集整个 `tests/`，覆盖服务入口、检索、挖掘、任务管理、业务边界与共享模块的当前离线测试；裸 `python -m pytest` 使用相同范围和守卫。按需选择领域回归：

```bash
./run_offline_tests.sh --group retrieval -q
./run_offline_tests.sh --group mining -q
./run_offline_tests.sh --group audit -q
./run_offline_tests.sh --group all -q
./run_offline_tests.sh --group explicit tests/services/test_file_access_service_timeout.py -q
```

另有 `shared/services` 组；`jobs/integrations` 仅保留分组参数，实际选择已迁到业务目录的测试；`--group smoke` 显式选择 `entry_smoke/offline`。默认与 `--group all` 均选择当前全套，确切选择以 `scripts/testing/offline_runner.py` 为准。两个需要真实子进程的断言（Excel 空格参数及 shell 日志/锁）标记为 `requires_process`，默认明确排除并打印原因；原业务断言保留，不能计作已通过。

在专用测试环境安装 `test` 依赖组，它包含基础依赖、pytest 和当前离线测试导入的 Python 包。`requirements-offline.txt` 保留本机私有测试目录的附加版本记录，不是独立的完整环境锁文件。推荐安装方式：

```bash
python -m pip install -e ".[test]"
KDB_TEST_PYTHON=/absolute/path/to/venv/bin/python ./run_offline_tests.sh -q
```

安装与 runner 应使用同一解释器；不要在共享生产解释器中安装测试依赖。既有环境若需保留本机测试版本，可再用该解释器执行 `python -m pip install --target "$PWD/private/test_dependencies" -r requirements-offline.txt`。目录如存在，runner 会优先加载并检查其中的 SDK；服务启动器不会自动使用此目录。包依赖声明不等于完成空白机器或全部平台的安装验收。

部分抓取代码导入系统 Tcl/Tk，需安装匹配解释器的系统组件；`test` 不安装真实 fastText 模型，不下载浏览器或配置认证。按服务选择生产依赖见[运行配置](runtime_configuration.md)。

需要将 JUnit 等报告写到仓库外时，先指定允许目录：

```bash
KDB_OFFLINE_OUTPUT_DIR=/absolute/path/to/test-output ./run_offline_tests.sh -q --junitxml=/absolute/path/to/test-output/results.xml
```

安全边界不能通过禁用守卫来绕过失败。启动测试替换 ES/SQL/LLM、模型、监听和线程等外部边界，检查真实参数和初始化接线；它们不启动真实 worker、不验证凭据、不证明 LLM 生成质量或真实后端可用。涉及真实外部调用的测试需要单独明确测试资源与数据范围。

修改函数前读取并更新对应 `function_schema/` 契约；SQL 表字段必须写明实际来源。优先验证行为和必要回归，不以方法名称、参数存在或静态导入代替完整业务验收。


默认测试检查业务依赖方向、静态 import 环、任务 CLI 定位及状态唯一持有者。CSAT 启动和认证测试在独立 assistant-data-tools 执行，不再计入核心套件。两个项目均使用离线守卫。

测试项数表示离线断言（含参数化用例），不是生产日志中约 1000 条请求的重放。生产配对回放、真实模型质量、后端可用性必须单独记录。

启动测试仅临时隔离待执行的入口模块，并在 finally 恢复其缓存及父包属性；业务 runtime 模块保持同一身份。该方式消除先 import 再 runpy 的重复模块告警，不屏蔽 warning、不关闭离线守卫，也不改变生产多 worker 启动方式。可用 `-W error::RuntimeWarning` 检查启动回归。
