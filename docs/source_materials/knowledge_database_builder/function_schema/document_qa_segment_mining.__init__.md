# document_qa_segment_mining.__init__

## 描述
初始化文档 QA/segment 任务控制器。业务上下文缓存默认改为项目级共享目录 `data/business_context_cache`，也可通过 `task_info.business_context_cache_dir` 覆盖。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| script_dir | str | 是 | 项目根目录 |
| task_id | str | 是 | 离线任务 ID |
| task_info | dict | 是 | 任务配置 |

## Outputs
无显式返回；初始化任务文件路径、上下文增强字段和工具实例。

## SQL
本函数不直接读写 SQL。启用 query 上下文时，后续阶段间接读取 `data_chat_history`。
