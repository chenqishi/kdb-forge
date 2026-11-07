# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._get_index_name

## Signature

`EsSearchInterfaceES8._get_index_name(self, index_names: IndexNames=None) -> str`

## Description

把调用方传的索引参数规整成 ES 接受的索引串（小写、逗号分隔），
顺带保证其中每个索引都已经过 `_ensure_index` 检查。

## Inputs

- `index_names` (str | List[str] | None)
  - `None`/空 → 用 `self.index_name`
  - `List[str]` → 逗号拼接
  - `str` → 可能本身就是逗号分隔的多索引串

单索引、逗号分隔索引或索引列表；为空使用默认索引。

## Outputs

`str` — 小写、逗号分隔的索引串

小写逗号分隔索引串，并确保每个索引通过 ES8 native mapping 检查。

## 两个已修正的坑

1. **缓存 key 大小写不一致**：`_ensure_index` 内部 `index_name.lower()` 后写 `has_build_index`，
   而这里用**原样** key 查 → 只要调用方传了带大写的索引名，缓存永远命中不了，每次请求都重跑。
   现在查询侧统一 `.lower()`。
2. **str 分支不拆逗号**：`index_names="a,b"` 时原来直接 `_ensure_index("a,b")`，
   而 `indices.exists("a,b")` 对「两个都存在」返回 True，接着
   `get_mapping("a,b")[...]["a,b"]` 必然 KeyError → 整个 mapping 同步静默失败。
   现在 str 分支也按逗号拆开逐个检查。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
