# kdb.entrypoints.cli.index_upload.insert_data_to_search_index

## Signature

`insert_data_to_search_index(data_file: str, config_path: str, use_platform_index: bool=True, index_name_assign: str=None, data_type=None, platform=None, from_type=None, is_update_data: bool=False, is_only_title: bool=False, basic_threshold: float=0.7, title_basic_threshold: float=0.95, check_duplicate: bool=None, is_need_llm: bool=None, allowed_quality_levels=None, required_review_decision: str=None, result_file: str=None)`

## Inputs


| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `data_file` | str | 必填 | jsonl 文件路径，每行一条 search_data |
| `config_path` | str | 必填 | `config/config_for_search_index.json` |
| `use_platform_index` | bool | True | 未指定 `index_name_assign` 时按 `platform` 选索引 |
| `index_name_assign` | str | None | 强制指定索引名（如 `wayfair`） |
| `data_type` / `platform` / `from_type` | str | None | 数据缺该字段时的兜底值 |
| `is_update_data` | bool | False | 查重命中时软删旧数据（`del_reason=cover_by_new`）再插新数据 |
| `is_only_title` | bool | False | 只按标题相似度判重 |
| `basic_threshold` | float | 0.7 | 进入判重的最低相似度 |
| `title_basic_threshold` | float | 0.95 | 判定为重复的相似度阈值 |
| `check_duplicate` | bool | None | 是否做入库查重。**None = 沿用配置文件的 `check_duplicate`**；`False` 关闭查重 |
| `is_need_llm` | bool | None | 向量规则无法确定时是否调用 LLM 精判。**None = 沿用索引配置**；`False` 保留向量查重但跳过 LLM 精判 |

`is_only_title` / `check_duplicate` / `is_need_llm` 支持传字符串（`fire` 命令行），内部按
`'true'` 比较转 bool。

`is_need_llm=False` 与 `check_duplicate=False` 不同：前者仍执行向量召回和数值阈值判重，
仅在阈值无法确定时不调用外部 LLM；后者完全关闭查重。外部精判模型临时 429 时优先使用前者。

### 什么时候该传 `check_duplicate=False`

只在「已在外部确认过不重复、且默认查重会误杀」时使用，并在关闭前把真重复的记录剔掉。

`src/kdb/shared/similarity/knowledge.py:is_simility_knowledge` 里两边都没有 `title_embedding` 时
`title_sim_score = -1`，于是 `min_sim_score` 恒为 -1，`min_sim_score > title_basic_threshold`
这条数值规则永远不成立，判重结果 100% 落到 `is_need_llm` 的主题级 LLM 上；
而查重召回用的向量是 `indexes[0].embedding`（segment 的 `indexes[0]` 是 keywords 拼接串），
top5 候选清一色同主题段落 —— 结果是同一篇文档的不同页互相判重。
wayfair 任务 74256b78 因此丢了 163 条段落。

关闭查重时会打一条 WARNING 到日志。

## Outputs


无返回值。逐条 `logging`：
- 成功 `成功插入数据: {_id}`
- 失败 `插入数据失败: {_id}, message: {message}`（`message` 为 `数据重复` / `数据处理失败`）
- 异常直接 `raise`，会打断整批

## SQL


不涉及 SQL。数据落 ES/OpenSearch 索引（`config_es_engine.json` 指定连接与索引）。

## Description

批量把 search_data 格式的 jsonl 文件插入检索库（ES/OpenSearch）。`fire` 命令行入口。

## 行为要点

- `ext_info.quality_info` 里含「重复」的记录直接跳过，不进入插入流程
- `platform` 缺失时用 `client` 兜底
- `_id` 由 `process_one_data` 内部按 `md5(title_content_data_type)` 生成，入参文件里可以是 None

## Source

`src/kdb/entrypoints/cli/index_upload.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
