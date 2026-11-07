# 项目操作指针

- 从 `README.md` 与 `docs/Architecture_Overview_Diagram.md` 了解当前结构；业务代码仅在 `src/kdb`，命令使用 `python -m kdb.…` 或 `scripts/`。
- 修改函数前先读 `function_schema/current_index.md` 中对应模块契约，更新 Inputs、Outputs；涉及 SQL 时记录实际表/字段及结构来源，不能猜测缺失数据格式。
- 对外只使用原业务接口，路由、参数、返回和认证保持原协议；服务配置与资源见 `docs/runtime_configuration.md`；默认验证见 `docs/testing.md`。模型、认证和后端连接的真实验收与离线验证分别记录。
- 五条管道、任务队列和自动入库约束见 `docs/pipelines.md`；ES8.17 与索引路由约束见 `docs/es8_retrieval.md`。
- 当前仓库只保留有效源码、资源及操作文档；历史材料和执行证据保存在仓库外，不复制进项目归档目录。
