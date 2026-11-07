# Restart candidate memory

- 2026-11-05 全工程重启实施：只从已发布f6a78084+四个核验dirty重新组装，本候选为detached、未提交未部署。恢复上下文先读/root/kdb-forge/artifacts/whole_project_refactor_restart_20261105/START.md及STATE.json。历史ES分片/DFS不是当前任务。
- SearchDataInterface含客户类目推断整体位于retrieval/application；旧core只保留这一套，forge仅薄协议适配。新发现原forge工厂/严格计数协议已按原契约承接，不能沿用上一轮报告当验收。
- 本机/root/kdb-forge/.venv-es817实际Python3.12，legacy验证使用/root/miniconda3/envs/py38/bin/python（Python3.9）和本候选SDK依赖；不从目录名推断环境。
- 六服务冷导入通过，语言fasttext缺失、爬虫selenium缺失、历史HTML夹具4失败及msearch请求计数2失败独立记录；测试非真实外部写入验收。
- 2026-11-06复核：ES同PIT视图30样本/60对完全一致，见/root/kdb-forge/artifacts/snapshot_pair_validation_20261106。私有材料、launcher预检、默认安全测试和最新清单见/root/kdb-forge/artifacts/refactor_review_remediation_20261106/REPORT.md；旧清单仅代表旧时刻。默认运行run_offline_tests.sh，服务必须显式KDB_PYTHON；先读docs/runbooks/offline_testing.md和restart_runtime.md。混合import/旧路径/目录未完成项见refactor_residuals_20261106.md，不能宣称全项目完全ready。
