# html_kg_gen_task_control.stage_6_5_generic_quality

## 描述
HTML 任务阶段 6.5：复用通用质量后处理，修复悬空指代/泛标题，并过滤 boilerplate、单薄知识。

## Inputs
无显式参数，读取 `self.reclear_qa_file_path`、`self.business_context_path`、`self.quality_profile`。

## Outputs

| 产物 | 说明 |
|------|------|
| self.reclear_qa_file_path 指向的 QA JSON | 原地更新 high/mid/low 列表 |
| self.quality_report_path | 修复与拒绝报告 |
| bool | 增强阶段失败时降级返回 True |

## SQL
不读写 SQL。
