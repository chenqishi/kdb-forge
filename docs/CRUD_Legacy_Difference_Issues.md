# CRUD 重构与旧实现差异记录

本文件记录对比旧项目 `/Users/chenqishi/stone_fish/knowledge_database_builder`
与当前重构版 CRUD 模块后发现的行为差异；每项标注**当前状态**（已闭合 / 已遗留 / 不再实现）。

> 闭合原则：旧 `SearchDataInterface` 的公开方法和服务副作用必须由兼容层暴露；外部 HTTP/LLM
> 仍通过旧配置和兼容依赖接入，底层 ES 请求全部改走 ES8.17 named API。
> 范围例外：Payoneer Olive 自动类目推断属于挖掘侧，用户明确排除，不作为 CRUD/检索遗漏项。

## 范围澄清：Payoneer Olive 类目推断

2026-09-28 用户确认此功能属于挖掘，不纳入 CRUD/检索重构。重构版已移除专属推断及
按模型来源丢弃类目候选的分支；不改旧项目的聊天 QA/挖掘实现。
保留显式 `category_infos` 归一化、类目树解析、已有 `primary_category`、默认分组，
以及 `web_search` 的类目过滤。没有显式类目时不会从 marketplace/model_platform、tags 或 title 猜类目。
对应离线回归见 `tests/test_legacy_service_compat.py`；这不是完整服务等价或真实 ES 验证结论。

## 1. 旧 `process_one_data` 的业务默认字段未补齐

### 状态：**已闭合**（不依赖外部 HTTP/LLM 的部分已全部补齐）

`KnowledgeService._prepare_document` 现在按旧 `process_one_data` 顺序补齐了下列业务默认（实现见
`src/kdb/crud/service.py` 第 2–14 步）：

| 项目 | 实现细节 |
|---|---|
| `is_audit` → `audit_result` | 直接迁移字段名 |
| `audit_result` 缺省 `-1` | 仅新建（`_id` not in data） |
| 非法 `audit_result` 重置 `-1` | 校验集合 `{-1, 0, 1, 2}` |
| `quality_level` 缺省 `"mid"` | 仅新建 |
| 非法 `quality_level` 重置 `"mid"` | 校验集合 `{"high", "mid", "low"}` |
| `from_type` 缺省 `"unknown"` | 仅新建 |
| 非字符串 `from_type` 转 str | `data["from_type"] = str(...)` |
| `from_type_norm` | 委托 `legacy_get_from_norm_type`（旧 `knowledge_tools.get_from_norm_type`，纯规则映射） |
| `tags` 缺省 = `keywords` | 仅新建，对齐旧 `tags = data.get('keywords', [])` |
| `keywords` 缺省 | 委托 `legacy_gen_keyword_by_title_content`（旧 `keywords_tools`，**jieba.analyse.textrank**，无外部 LLM） |
| `category_infos[].category_id` 转 str | `for ci in category_infos: ci['category_id'] = str(...)` |
| `dataset` 缺省 = `index_name` | 通过 `insert_text(index_name=...)` 传入 |
| `multimodal_contents` → `content` 拼接 | `_join_multimodal_contents`，与旧 `join_multimodal_contents` 等价；占位符仍为字面 `[multimodal_prefix]`，由 search_text 阶段替换 |

### 兼容层已补齐

| 项目 | 原因 |
|---|---|
| `primary_category` 构造 | `LegacySearchDataInterfaceMixin._apply_category_defaults` 调用兼容类目接口 |
| dedup / `is_update_data` | `find_duplicates` 和 `insert_data` 保留旧 SimilityTools/软删除入口 |

旧服务的 `SearchDataInterface` 方法名通过 `KnowledgeService` 直接暴露；同时提供
`kdb.crud.SearchDataInterface` 和 `kdb.knowledge_interface_tools.search_index_data_interface.SearchDataInterface`
兼容构造入口。`web_search_data`、`search_data_by_multi_query`、`batch_insert_data`、按文件名操作
均已纳入兼容层。

### 验证

- `tests/test_service_roundtrip.py::test_service_full_text_crud_roundtrip` 默认输入未提供
  `from_type_norm/tags/keywords` 也能写入成功，证明默认补齐链路工作。
- 对齐测试 `tests/test_alignment_with_legacy.py` 在共享同一 embedding/jieba 实现的前提下，
  新旧 `_id`/向量/indexes/ext_info 仍一致。

## 2. 搜索返回未替换 `[multimodal_prefix]`

### 状态：**已闭合**

`KnowledgeService` 构造时接受 `multimodal_prefix: str` 参数；`from_config` 自动从 cfg 引用的旧
`config_for_search_index.json` 读取（键 `multimodal_prefix`，当前值 `https://file.marsmind.cc/`）。
`search_text` 在返回前对每条 doc 的 `content` 做：

```python
content.replace("[multimodal_prefix]", self._multimodal_prefix)
```

与旧 `SearchDataInterface.search_data_by_query`（旧 `search_index_data_interface.py:711`）行为
完全一致；构造时传空串则不替换（向后兼容）。

测试 fixture `tests/conftest.py::multimodal_prefix` 也按相同方式读取，确保 service fixture 与
旧实例使用同一前缀值。

## 验证建议

修复后建议增加集成测试（待补）：

- 插入 `multimodal_contents=[{"type":"image","path":"foo.png"},...]`，验证 `content` 被旧/新都拼接为 `[multimodal_prefix]foo.png` 形式，并通过 `search_text` 返回后被替换成实际 URL。
- 不带 `keywords/tags/from_type/from_type_norm` 的最小输入插入，验证 jieba 关键词与 from_type_norm 由 CRUD 自动补齐。
- 使用 `test_case` 索引运行完整集成测试 `./run_tests.sh`，确认对齐测试仍通过。
