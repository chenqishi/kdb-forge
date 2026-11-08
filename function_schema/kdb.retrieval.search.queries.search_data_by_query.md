# kdb.retrieval.search.queries.search_data_by_query

## Signature

`search_data_by_query(self, query: str, index_names: str=None, condition_dicts: List[Dict[str, Any]]=None, size: int=10, search_type: str='qa', data_type: str='text', use_synonyms=False)`

## Description

`/search` 接口的核心编排：算 query 向量 → ES 召回 → 本地重排。

## Inputs

- `query` (str)
- `index_names` (str, 逗号分隔)
- `condition_dicts` (List[dict]) — 属性条件组，组间 OR。为空时默认
  `[{'quality_level':['high'],'data_type':['qa']}, {'audit_result':[1,2],'data_type':['qa']}]`；
  每组若没写 `audit_result` 会补上 `[1, 2, -1]`
- `size` (int) — 即 `/search` 的 `top_k`
- `search_type` (str) — `'qa'` / 其他，决定本地重排公式
- `data_type` (str) — 含 `'image'` 时把图片相似度并入
- `use_synonyms` (bool)

旧版 query、index_names、condition_dicts、size、search_type、data_type、use_synonyms。

## Outputs

`Tuple[List[Dict], int]` — 每条带 `similarity` 字段

返回 `(candidate_docs, total_num)`，保留候选预算、similarity 计算和多模态 URL 渲染。

## 两级打分（关键，容易记错）

| 级 | 在哪 | 用什么 |
|---|---|---|
| 召回/初排 | ES | `multi_match` + `synonyms_title match`（BM25 词频）+ nested 向量，**相加** |
| 终排 | 本地 `_cal_similarity` | **纯向量**：title / content / indexes同义分支 / image_indexes 四类 embedding |

**ES 的融合分在 `/search` 路径上被完全丢弃**：`:747` 把 `doc['similarity']` 覆写成纯向量分，
`/search` handler 取的是 `similarity`，`doc['score']` 一次都没用。
（`/web_search` 相反：走 `search_multi_by_page`，`:948` 用 `min(score/5.0, 1.0)` 归一化 ES 分，不做本地重排。）

## 候选预算 `size * 2`

传给 `search_multi` 的是 `size * 2`，是**候选总预算**：
- `recall_mode='legacy'`：每索引取 `size*2` 条
- `recall_mode='dual'`：每索引每路各取 `size`，两路合并后总量不变

## 一个已知的排序量纲问题（未改）

`_cal_similarity` 在 `search_type='qa'` 下：
```
有 title:  similarity = title_sim + 0.2 * content_sim     # 上限 1.2
无 title:  similarity = content_sim                       # 上限 1.0
```
两类数据被塞进同一个 list 一起 sort，**segment 系统性吃亏 20%**。
content_sim=0.6096，排第 8；top1「巴西FULL尾程物流费用是多少？」title_sim 只有 0.5657，
靠 `+0.2×0.5633` 的加成反超到 0.6784。

代码注释写着「有title和无title的数据不放在一块排序」，但实际就是放在一块排的。
改法是 qa 分支除以 1.2 归一化，但会动到所有现有排序，需要先跑前后对比。

## SQL

无。

无；读 Elasticsearch。

## dual 召回模式对本函数的影响

**无。** `search_multi` 在 dual 模式下会把 `doc['indexes']` 变薄（只有分数最高的几项带 `embedding`），
但数组形状与字段名不变，`_cal_similarity` / `_cal_title_similarity` 的代码一行未改。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.search_data_by_query`

## Source

`src/kdb/retrieval/search/queries.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
