# kdb.mining.pipelines.html_qa_segment.HtmlKgGenTaskController.stage_4_5_build_business_context

## Signature

`HtmlKgGenTaskController.stage_4_5_build_business_context(self)`

## Description

HTML 任务阶段 4.5：复用 `business_context_builder.build_business_context` 构建业务上下文。`enable_context_enrichment=false` 时 no-op。

## Inputs

无显式参数，读取 `self.task_info` 和初始化字段：

| 字段 | 说明 |
|------|------|
| client / knowledge_objective / business_context_text | 缓存 key 与上下文文本来源 |
| enable_context_enrichment / enable_chat_query_context / enable_web_context | 控制上下文来源 |
| business_context_cache_dir / context_cache_ttl_days | 共享缓存位置与 TTL |

现有参数签名：`self`。控制器继续从 task_info、script_dir、任务文件读取原有字段；不改变默认值或参数位置。

## Outputs

| 产物 | 说明 |
|------|------|
| self.business_context_path | 写入 `business_context.json`，后续 QA/segment/quality 使用 |
| bool | 总是尽量返回 True；增强失败时降级跳过 |

阶段4.5：构建业务上下文（仅 enable_context_enrichment=true 时执行）。

## SQL

本函数不直接读写 SQL；当启用 `enable_chat_query_context` 时，间接通过 `chat_query_context.load_client_queries` 读取 `data_chat_history`。

## 路径和子进程契约

本阶段通过当前 `kdb.mining.generation.processing` 包导入上下文和质量实现；`script_dir` 仅用于运行配置、数据、日志与工作目录。Python 模块定位由标准包入口和当前 `src` 提供，阶段执行保持已有模块搜索路径。

正式入口使用当前解释器 `sys.executable -m kdb.*`；仅替换旧脚本定位，不修改子命令、业务 argv、重定向、阶段顺序、工作目录、成功/失败返回及异常处理。环境经 `kdb.shared.config.paths.subprocess_env` 继承，仅前置当前 src 到 PYTHONPATH。聊天控制器继续加载可选 LLM env、独立进程组、任务总超时与 TERM/KILL 规则。日志预览仅有界读取头500字符/尾1000字符。

## SQL / ES

本次仅迁移代码入口，无新增 SQL 或 ES 字段。任务状态更新仍经 TaskStatusUpdater，原任务表 dops_task_kggen_info 及 task_id/task_stage/run_status/task_result 等字段不变；索引写入仍由现有 insert_data_to_search_index 接收相同 argv。上下文构建在原开关启用时经现有实现读取 data_chat_history，SQL 与字段遵循被调用函数原 schema。

## Source

`src/kdb/mining/pipelines/html_qa_segment.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
