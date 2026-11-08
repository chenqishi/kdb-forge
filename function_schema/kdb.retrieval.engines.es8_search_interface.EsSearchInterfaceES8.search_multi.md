# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.search_multi

## Signature

`search_multi(self, query: Dict[str, Any], index_names: IndexNames=None, size: int=10, page_num: int=1, recall_mode: Optional[str]=None) -> Tuple[List[Dict[str, Any]], int]`

## Description

混合检索的召回入口。支持两种召回模式，由 `recall_mode` 决定。

## Inputs

- `query` (dict) — `{"query": str|List[str], "vector": {"value":[...]}|List[...], "attribute": [条件组...], "insert_time"/"update_time": [start,end]}`
- `index_names` (str | List[str] | None) — 多索引时一次 `_msearch`
- `size` (int) — **候选总预算**。legacy 模式下每索引取 `size`；dual 模式下每索引每路各取 `size//2`，两路合并后总量不变
- `page_num` (int) — 未使用（保留）
- `recall_mode` (str | None) — `'legacy'` / `'dual'`；`None` 时取实例默认 `self.recall_mode`
  （由 `extra_params.recall_mode` 配置，**默认 `dual`**；回退写 `"recall_mode": "legacy"`）

query、目标索引、size、page_num、可选 recall_mode。

## Outputs

`Tuple[List[Dict], int]` — (结果列表, 总命中数)

每条结果除 `_source` 字段外还带：

| 字段 | 说明 |
|---|---|
| `_index` / `_id` / `score` | 同 legacy |
| `indexes` | **dual 模式下形状不变、内容变薄**：`_source` 排掉了 `indexes.embedding`，所以数组仍是完整的 N 项、每项都有 `text`，但只有 `inner_hits` 带回的前 `_INNER_HITS_SIZE` 项按 `_nested.offset` 补回了 `embedding` |
| `recall_route` | **仅 dual 模式**。`"bm25"` / `"vector"` / `"bm25,vector"`，记录该文档被哪几路召回 |

`(docs, total)`；默认 dual，BM25/native KNN 分路后按 `_index + _id` 合并。

## 两种模式

### legacy（与改造前逐字节一致）
每索引一个 body，`bool.should` = `[multi_match, synonyms_title match, nested script_score]`，分数**相加**。
`_source` 不做过滤，整条文档（含所有 embedding）回传。

### dual（默认，双路召回）
每索引**两个** body，一次 `_msearch` 发出（**仅当文本与向量都有时**；只有其中之一时拆路无意义，退回单路）：

| 路 | should 子句 | size |
|---|---|---|
| bm25 | `multi_match(title^2/content^1.5/indexes.text)` + `match synonyms_title^1.8` | `size//2` |
| vector | `nested script_score cosineSimilarity(indexes.embedding)` | `size//2` |

`_source` 过滤只在**真的挂了 `inner_hits`**（即 `vector_should` 非空）时才加——
否则 `indexes[].embedding` 被排掉又没人补回来，下游 `_cal_title_similarity` 的同义问法分会静默丢失。
无 query、无向量的纯属性检索因此走单路、不做 `_source` 过滤，与 legacy 逐字节一致。

两路都带 `_source.excludes = ["indexes.embedding", "image_indexes.embedding"]`。

**只有向量路挂 nested 子句**（`bd4dae6` 起 BM25 路不再挂 boost=0 的 nested——boost 只清零它对
父文档分的贡献，cosineSimilarity 照样全量执行，等于把最贵的向量打分跑两遍）。故：
- nested 的 `inner_hits: {size: 3, ...}` 与 `score_mode: "max"`（不写时 ES 默认 avg，
  同义问法越多向量分被摊得越低）**只在向量路上**
- BM25 路的命中拿不到 `indexes[].embedding`，靠合并时从向量路那份补齐（见下）

合并按 `(_index, _id)` 去重，`recall_route` 记录来源。`total_num` 取两路中的较大值（相加会重复计数）。

**同一条被两路都命中时：保留先到的那份（分数与排序位置不变），并把另一份的
`indexes[].embedding` 按 `text` 对齐合并进来**（`_merge_index_embeddings`，已有的不覆盖）。

不这么做会有一个静默失效（2026-09-07 wayfair 线上答错事故的直接原因）：
BM25 路自 `bd4dae6` 起不挂 nested 向量子句，其 `_source` 排除了 `indexes[].embedding`
且没有 `inner_hits` 可补（`title_embedding`/`content_embedding` 仍在，只缺 indexes 里的）。
而 `_cal_title_similarity` 的同义问法分支要求
`text in synonyms_title and index_info.get('embedding')` 同时成立，拿不到 embedding 就整段空转、
静默退化成只用 `title_embedding`。子请求按 `(索引 × 路)` 顺序发出、BM25 在前，
先到先得会让 BM25 那份占坑，于是**一条同义问法与 query 逐字相同（cosine=1.0）的知识，
最终只拿到 title 的 0.648 分**，排不进候选池。

也不能改成「按 `_score` 取 max」：BM25 分量级 30~60、cosine 分量级 0~2，不同量纲不可比，
取 max 恒选 BM25，问题原样保留。

## 为什么 bm25 路不能挂 nested（哪怕 boost=0）

最初挂了一份 `boost: 0` 的 nested 来白拿 `inner_hits`——`boost` 确实只清零它对父文档分的贡献

**但 `boost` 不影响执行**：`cosineSimilarity` 照样对该索引所有 nested 文档全量算一遍，

```
                                        并发1        并发4       回传
dual 挂 boost0 nested                0.64/1.56s   1.22/2.87s   13.7MB
dual 不挂（现在）                     0.94/1.08s   1.87/2.07s    9.2MB
                                      ↑47%         ↑53%         ↓33%
只 BM25（2子请求）                    2.31/0.46s   4.82/0.77s    2.5MB
只向量（2子请求）                      1.30/0.74s   2.69/1.47s    6.7MB
```

代价：只被 BM25 路召回的文档拿不到 `indexes[].embedding`，
`_cal_title_similarity` 的同义问法分支归零，退化成只用 `title_embedding`。

```
只被 BM25 路召回的文档       1442 条
其中同义词分支真的掉分的        2 条 (0.1%)
掉分幅度  中位 0.0076  最大 0.0117
top1 重合 100.0% (30/30 完全相同)   top3 95.6%   top5 95.3%   top10 96.0%
```
原因是「某个同义问法跟 query 很像」的文档**必然被向量路召回**，那时 `inner_hits` 就有了；
只被 BM25 路召回的，本来就是同义问法跟 query 不像的，同义分支对它们也贡献不了什么。

## 下游为什么不用改（关键设计）

`_source` 排掉 `indexes.embedding` 后，`doc['indexes']` 仍是完整的 N 项、每项都有 `text`，只是没有向量。
`inner_hits` 的每一项带 `_nested.offset`（它在原 `indexes[]` 数组里的下标），
`_restore_inner_embeddings` 按这个下标把 embedding 填回对应位置。

结果是一个**形状与原来完全一致**的数组，只有分数最高的那几项带 `embedding`。
`_cal_title_similarity` 原本就写着 `if text and text in synonyms_titles and index_info.get('embedding')`
—— 没补到向量的项被这个判断自动跳过，**所以本地重排代码一个字都不用改**。

```
_source 里 9 项都只有 text、没有 embedding
  塞回 offset=1  cos=0.4770  '活动提报（DOD/限时特惠）'
  塞回 offset=7  cos=0.4521  '活动提报（Deal of the Day/L'
  塞回 offset=6  cos=0.4504  '活动提报（今日特惠/LD）'
→ 3 项有 embedding，6 项没有
```

## 输入输出保持一致（硬约束）

dual **不能给返回的文档加或减任何字段**，否则会影响下游。
召回来源（bm25 / vector）只写日志，不进文档；`indexes` 数组的条数、顺序、`text` 与 legacy 完全相同。
`tests/test_dual_route_recall.py` 里有这些断言守着：
- `test_returned_doc_fields_identical_between_modes` — 字段集合一致
- `test_dual_does_not_leak_internal_fields` — 不泄漏 `recall_route`/`indexes_sims`/`inner_hits`
- `test_no_query_no_vector_falls_back_to_single_route` — 纯属性检索两模式逐字节一致
- `test_dual_both_routes_carry_identical_filters` — 两路 `must` 过滤（含自动补的 `del_flag=0`）完全相同
- `test_dual_del_flag_not_overridden_when_explicit` — 显式给了 `del_flag` 就不再补

真实集群验证（`payoneer_olive`）：
- 无 query 的 7 类属性检索（含 `category_path`、两组 OR、显式 `del_flag=1`），
  **整篇文档逐字段比对完全一致**
- 有 query 时 6 类条件下返回文档**违反条件 0 条、删除态 0 条**；
  双索引 4 个子请求的 `must` 只有 1 种，两路过滤完全一致
- 有 query 的 75 条共有文档：字段集合无差异，`indexes` 条数与 `text` 序列 75/75 一致

## 兼容性

- `recall_mode='legacy'` 时不加 `_source` 过滤、不加 `inner_hits`，生成的查询体与改造前**逐字节一致**
  （8 个场景对拍 git HEAD 旧代码，全部相同：单/多索引、多 query 多向量、无向量、无文本、显式 del_flag、时间范围、无 attribute）
- `dual` 模式下 `doc` 的字段结构与 legacy 相同，只是未进 top-N 的 `indexes` 项没有 `embedding`
- 离线脚本直接读 ES 的路径不受影响

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
