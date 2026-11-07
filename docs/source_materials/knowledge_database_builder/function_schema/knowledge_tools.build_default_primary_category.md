# knowledge_tools.build_default_primary_category

## 概述
返回「默认分组」的 `primary_category` 结构，供插入链路（`process_one_data`）和存量回填脚本
（`supply_missing_field.py`）共用，避免两边各写一份字面量后漂移。

## Inputs
无参数。

## Outputs
| 类型 | 说明 |
|------|------|
| dict | `{"category_path": "默认分组", "category_ids": ["1"], "cate1_name": "默认分组", "cate1_id": "1"}` |

每次调用返回新 dict，可直接写入 data 不用再 copy。

## SQL/ES Schema
### 读取
无。类目 ID/名称是常量 `DEFAULT_CATEGORY_ID="1"` / `DEFAULT_CATEGORY_NAME="默认分组"`。

来源依据：`GET https://admin.marsmind.cc/api/rufit-ai/intranet/knowledge/qaCategory/tree?client=<client>`
返回的一级类目里，`categoryId=1 / categoryName=默认分组` 对每个 client 都存在
（joint_login 实测只有这一个一级类目；mercado 有 5 个，默认分组是其中之一）。

### 写入字段
- ES 文档的 `primary_category` 对象（`payoneer_olive`/`joint_login` 里子字段是 keyword；
  `mercado` 是动态映射的 text+keyword，聚合要用 `.keyword`）。

## 关键逻辑
- 「默认分组」是前端可见、可筛、可管理的真实分组，**不是占位符**；真正看不见的是连
  `primary_category` 字段都没有的文档。
- 只在没有任何类目来源时用；有 `category_infos` 时必须按 parent chain 构造真实类目。
