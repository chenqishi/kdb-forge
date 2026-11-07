# kdb.mining.pipelines.html_qa_segment.HtmlKgGenTaskController.run_all_stages

## Signature

`HtmlKgGenTaskController.run_all_stages(self)`

## Description

运行 HTML 知识生成全流程。新增业务上下文阶段和通用质量阶段，并支持 `review_only=true` 跳过 ES 插入。

## Inputs

无显式参数，读取控制器初始化后的任务字段。

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 全流程是否成功 |

## 阶段顺序

URL 爬取 → 内容处理 → 多模态处理 → 文本翻译 → 构建业务上下文 → QA生成 → QA质量处理 → 通用质量后处理 → QA Schema → QA插入 → 段落生成 → 段落 Schema → 段落插入。

`review_only=true` 时跳过 QA 插入和段落插入。

## SQL

通过 `TaskStatusUpdater` 更新任务状态、阶段、结果和费用；字段沿用原任务表结构。上下文构建可能间接读取 `data_chat_history`。

## Source

`src/kdb/mining/pipelines/html_qa_segment.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
