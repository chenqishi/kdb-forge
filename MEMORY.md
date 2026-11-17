# 项目操作指针

- 业务本体的实际存储、校验、事务、作用域选取与克隆逻辑见 [实现说明](docs/business_ontology_implementation.md)；协议见 [API](docs/api.md#业务本体)，职责见 [代码库本体](docs/ontology.md)，独立真实 MySQL 验证入口见 [测试说明](docs/testing.md)。

- 先按 [AGENTS.md](AGENTS.md) 的上下文获取规则定位本次需要的资料；README、架构图及本文件均按需检索，不默认整篇加载。业务代码仅在 `src/kdb`，命令使用 `python -m kdb.…` 或 `scripts/`。
- 需求归属、模块协作和修改边界见 [代码库本体](docs/ontology.md)；它描述代码项目，保持模块级粒度，与单条知识数据无关。函数参数和 SQL 细节继续查当前契约。
- 修改函数前按文件名/符号检索 `function_schema`，必要时查 `current_index.md` 的对应模块行，再读目标契约；更新 Inputs、Outputs，涉及 SQL 时记录实际表/字段及结构来源，不能猜测缺失数据格式。
- 对外只使用原业务接口，路由、参数、返回和认证保持原协议；服务配置与资源见 `docs/runtime_configuration.md`；默认验证见 `docs/testing.md`。模型、认证和后端连接的真实验收与离线验证分别记录。
- 五条管道、任务队列和自动入库约束见 `docs/pipelines.md`；ES8.17 与索引路由约束见 `docs/es8_retrieval.md`。
- 当前仓库只保留有效源码、资源及操作文档；历史材料和执行证据保存在仓库外，不复制进项目归档目录。

- 业务依赖方向由 scripts/testing/architecture.py 与默认测试约束；状态归属见 docs/state_ownership.md。CSAT 与身份映射属于独立 assistant-data-tools，版本与回退边界见运行配置。
