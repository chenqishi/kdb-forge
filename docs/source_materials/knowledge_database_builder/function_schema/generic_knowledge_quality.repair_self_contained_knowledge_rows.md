# generic_knowledge_quality.repair_self_contained_knowledge_rows

## 描述
通用知识质量后处理（不硬编码任何客户）。修复两类问题：
1. 悬空指代：第N期/本次/此次/该活动/该服务/该合作/该平台/该计划/该课程开头。
2. 栏目式泛标题：活动概述与目标/适合对象/推广内容/服务内容/详情/核心优势等。
用 from_file_name（或业务上下文实体词）推导稳定业务主体补全；无法补全则标记 needs_review。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| rows | list[dict] | 是 | 知识行 |
| business_context | dict\|None | 否 | 提供 entity_markers/client/query_intents 提升判断精度 |
| source_title_field | str | 否 | 主体兜底来源字段，默认 from_file_name |
| title_field | str | 否 | 标题字段名，默认 title（QA 流程传 'q'） |
| content_field | str | 否 | 内容字段名，默认 content（QA 流程传 'a'） |

## Outputs

| 类型 | 说明 |
|------|------|
| (list[dict], dict) | (repaired_rows, report)。report: {total, repaired_count, needs_review_count, changes, needs_review} |

## 逻辑
1. 栏目式泛标题 → `主体：栏目名`。
2. 标题悬空前缀 → 主体替换前缀。
3. 内容悬空前缀（活动采用/该服务/本次活动…）→ 主体 + 泛词。
4. 修复后仍悬空/泛标题 → row['needs_review']=True。
5. changes 记录前后 title/content，不静默修改。

## 备注
- 主体优先用业务上下文实体词；允许 from_file_name 作为兜底主体。
