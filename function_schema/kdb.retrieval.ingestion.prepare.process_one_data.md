# kdb.retrieval.ingestion.prepare.process_one_data

## Signature

`process_one_data(self, data: Dict[str, Any], index_name: str=None) -> bool`

## 概述

规范化单条待写入检索索引的数据，补齐索引字段、embedding、关键词、类目和时间字段。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| data | Dict[str, Any] | 是 | 待处理的数据，会被原地修改 |
| index_name | str | 否 | 目标索引名，用于默认 `dataset` |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 处理成功返回 True，异常返回 False |

## SQL/ES Schema

### 读取
- 不直接读取 SQL。
- 当存在 `category_infos` 时，会通过类目服务/缓存获取 parent chain 构造 `primary_category`。
- embedding 由配置里的 embedding 工具生成。

### 写入字段
- `ext_info`: 非 schema 字段会并入 `ext_info`。
- `audit_result`: 缺失的新数据默认为 `-1`；合法值为 `-1, 0, 1, 2`。
- `indexes`: 包含 title、image text、`synonyms_title` 派生文本及其 embedding。
- `title_embedding` / `content_embedding`: 根据 title/content 生成。
- `keywords`: 根据 title/content 生成。
- `insert_time` / `update_time`: 新数据（无 `_id`）补当前时间；更新（有 `_id`）不带 `insert_time`
  时**不写**该字段，让 ES 保留原值；带了但不是字符串才纠正。所有数据都刷新 `update_time`。
- `from_type` / `from_type_norm` / `tags` / `del_flag` / `dataset`: 按默认规则补齐。
- `primary_category`: 从最高分 `category_infos` 和 parent chain 构造；**没有任何类目来源时，
  新数据（`_id` 不在 data 里）兜底成「默认分组」**（`build_default_primary_category()`），
  同时补 `category_infos`（`source='default'`）。带 `_id` 的更新不写，避免覆盖已有真实类目。

## 关键逻辑

- `audit_result=2` 是机器自动审核 high 数据的通过状态，必须保留，不能误判成非法值。
- `synonyms_title` 会派生进 `indexes[]` 并生成向量；只 direct update `synonyms_title` 不足以让向量召回生效。
- **类目兜底不能省**：入库不传类目的链路（群聊自动学习 `chatknowledge_process.sh` 走
  `schema_trans.py` 时不传 `--category_id/--category_name`）以前会让文档连 `primary_category`
  字段都不存在。归组/过滤走的是 `primary_category.cate1_id` / `category_path`（不是
  `category_infos`），字段缺失的文档按任何类目都筛不出来，客户在分组里永远看不到它们。
- 「默认分组」= `categoryId=1`，在每个 client 的类目树接口里都真实存在，是可见可筛的分组，
  不是占位符；默认值定义在 `knowledge_tools.build_default_primary_category()`，
  `supply_missing_field.py` 的 `DEFAULT_PRIMARY_CATEGORY` 复用同一份。
- `insert_time` 的三种情况必须分开判断。曾经写成
  `if 'insert_time' not in data and '_id' not in data: ... elif not isinstance(data['insert_time'], str)`，
  「有 `_id` 且没带 `insert_time`」会走进 elif 直接 KeyError，整条数据处理失败返回 False
  （回归用例 `tests/test_default_category.py::test_update_without_insert_time_does_not_crash`）。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.process_one_data`

## Source

`src/kdb/retrieval/ingestion/prepare.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
