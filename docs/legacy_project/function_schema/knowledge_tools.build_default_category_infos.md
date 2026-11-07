# knowledge_tools.build_default_category_infos

## 概述
返回「默认分组」的 `category_infos` 列表，形状与前端手工选「默认分组」插入的数据一致。

## Inputs
无参数。

## Outputs
| 类型 | 说明 |
|------|------|
| list | `[{"category_id": "1", "category_name": "默认分组", "score": 1.0, "source": "default"}]` |

## SQL/ES Schema
### 写入字段
- ES 文档的 `category_infos`（nested-ish object 数组：`category_id` / `category_name` 为
  text+keyword）。`score` / `source` 不在 mapping 里声明，按动态映射写入。

## 关键逻辑
- `category_infos` 是「类目候选来源 + 打分」，`primary_category` 才是归组/过滤用的落地字段；
  两者都补是为了让兜底数据和人工选类目插入的数据结构一致，后续重算 `primary_category` 时不丢来源。
- `source='default'` 用来区分兜底和人工选择（`manual`），后续做平台类目回填时可据此圈定。
