# KDB Forge — 整项目结构重构候选

本候选从已发布f6a78084与四个有效dirty修复重新组装；正式模块位于src/kdb/services、jobs、mining、retrieval、shared、integrations、reporting。旧脚本/import路径保留薄wrapper，旧forge重复核心归档。

候选尚未部署；不直接启动离线任务或维护工具。运行命令、解释器和缺失资源见[启动说明](docs/runbooks/restart_runtime.md)，默认安全测试见[离线测试说明](docs/runbooks/offline_testing.md)，forge独立协议见[兼容协议](docs/runbooks/forge_compat_restart_protocol.md)，当前结构见[架构图](docs/Architecture_Overview_Diagram.md)。

ES检索已完成同一PIT视图的新旧对比：30个重点样本、两轮共60对，响应与原SDK请求计划均完全一致；不能将此结论扩展成1000条全量快照复验或七服务全部可上线。语言模型和CSAT认证仍缺真实资源。默认`./run_offline_tests.sh -q`或`./run_tests.sh -q`只运行受禁网络/进程边界保护的入口与离线测试；历史测试须显式选择。

来源及初次组装证据保留在`/root/kdb-forge/artifacts/whole_project_refactor_restart_20261105/`。2026-11-06复核整改、最新候选清单与完整性复查见`/root/kdb-forge/artifacts/refactor_review_remediation_20261106/REPORT.md`，旧清单不能代表当前现场。遗留import、绝对路径与目标目录的未完成项见[结构处置清单](docs/runbooks/refactor_residuals_20261106.md)。

原工作区、旧候选、内容快照与活动数据保留，私有配置不入Git。
