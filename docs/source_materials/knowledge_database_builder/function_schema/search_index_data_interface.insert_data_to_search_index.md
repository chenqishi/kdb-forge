# search_index_data_interface.insert_data_to_search_index

批量把 search_data 格式的 jsonl 文件插入检索库（ES/OpenSearch）。`fire` 命令行入口。

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
| `allowed_quality_levels` | str/list/set | None | 可选质量闸门；字符串按逗号拆分。聊天控制器传 `high` |
| `required_review_decision` | str | None | 可选审核决策闸门；聊天控制器传 `accept`。检查字段，不自行审核 |
| `result_file` | str | None | 可选统计 JSON 文件；临时文件写完后原子替换 |

`is_only_title` / `check_duplicate` 支持传字符串（`fire` 命令行），内部按 `'true'` 比较转 bool。

### 什么时候该传 `check_duplicate=False`

只在「已在外部确认过不重复、且默认查重会误杀」时使用，并在关闭前把真重复的记录剔掉。

已知误杀场景（2026-09-02 实测）：**无 title 的 segment**。
`commons/simility_tools.py:is_simility_knowledge` 里两边都没有 `title_embedding` 时
`title_sim_score = -1`，于是 `min_sim_score` 恒为 -1，`min_sim_score > title_basic_threshold`
这条数值规则永远不成立，判重结果 100% 落到 `is_need_llm` 的主题级 LLM 上；
而查重召回用的向量是 `indexes[0].embedding`（segment 的 `indexes[0]` 是 keywords 拼接串），
top5 候选清一色同主题段落 —— 结果是同一篇文档的不同页互相判重。
wayfair 任务 74256b78 因此丢了 163 条段落。

关闭查重时会打一条 WARNING 到日志。

## Outputs

返回统计字典：`input_num`、`gate_skip_num`、`quality_gate_skip_num`、
`review_gate_skip_num`、`tagged_duplicate_skip_num`、`insert_attempt_num`、
`insert_success_num`、`duplicate_skip_num`、`insert_failure_num`。
指定 `result_file` 时，在结束或入库异常时同步写出统计。逐条 `logging`：
- 成功 `成功插入数据: {_id}`
- 失败 `插入数据失败: {_id}, message: {message}`（`message` 为 `数据重复` / `数据处理失败`）
- 异常直接 `raise`，会打断整批

**已知任务成功判定缺口（2026-10-08检查，未修实现）**：单条处理失败/引擎返回False只增加
`insert_failure_num`，函数仍正常返回统计，Fire CLI因此可正常退出。控制器只读子进程退出码，
可能把“失败1、成功0”误报阶段成功。异常向上传播的分支会导致非零退出，不能混淆。
反例、真实入口离线复现和strict xfail见 `tests/test_off_task_es817_20261008.py` 与
`docs/reviews/off_task_es817_20261008.md`。

## 行为要点

- `ext_info.quality_info` 里含「重复」的记录直接跳过，不进入插入流程
- `platform` 缺失时用 `client` 兜底
- `_id` 由 `process_one_data` 内部按 `md5(title_content_data_type)` 生成，入参文件里可以是 None
- 每次CLI初始化一次真实 `SearchDataInterface`，读取业务配置中的 `search_engine_config_path`。
  后续新CLI会重新读取配置，正在运行的批次不因改文件自动更换已有client。
- 当前初始化固定 `index_name='mix'`，实际文档仍按 `index_name_assign/platform` 写入。
  开启自动建库时会先确保mix；升级前同样在初始化时确保它，不是新版引入的错库问题。
  2026-10-08纠正原“只应创建目标索引”的非旧契约期望，替换测试验证初始化沿用旧行为、
  文档仅写实际目标/provider，已通过；没有为此修改入口。mock create不代表真实建索引。

## SQL

不涉及 SQL。数据落 ES/OpenSearch 索引（`config_es_engine.json` 指定连接与索引）。
