# kdb.integrations.data_control.augment_segment_topics.augment_task_segments

## Signature

`augment_task_segments(task_id, index_name='wayfair', execute=False, count=10, only_file=None, only_files=None, output_dir='output/augment_segment_topics', es_config='config/config_es_engine.json', embedding_config='config/config_ali_embedding.json', model_name=None, provider=None)`

## Purpose

给某个任务新生成的段落知识批量补相似语义问法，写回 ES `indexes[]`（文本 + 向量）。
默认 dry-kdb.mining.generation.run。

## Inputs

- `task_id` (str): 圈定要处理的段落。
- `index_name` (str): ES 索引，默认 `wayfair`。
- `execute` (bool): 默认 False 只产出对照，不写库。
- `count` (int): 每条段落补几条问法，默认 10。
- `only_file` (str|None): 只处理某个 `ext_info.from_file_name`，用于小范围试跑。
- `es_config` / `embedding_config` (str): 配置路径。
- `model_name` / `provider` (str|None): LLM 选择。

## Outputs

- `str`: 报告 JSON 路径，含每条段落的新增问法、跳过原因、失败原因。

副作用（execute=True）：
- 对每条段落做 ES `_update`，只追加 `indexes[]`，**不动** `content` / `content_embedding` /
  `keywords` / `tags` / `multimodal_contents`
- 写回滚文件 `output/augment_segment_topics/rollback_*.jsonl`，记录 doc id 与本次追加的文本，
  回滚时按文本从 `indexes[]` 中剔除（向量可确定性复现，无需备份）

## SQL

No SQL access.

## ES 字段

- 读：`content`, `indexes`, `data_type`, `ext_info.from_file_name`, `task_id`, `del_flag`
- 写：`indexes`（追加 `{text, embedding}`，embedding 为 1024 维 text-embedding-v3）

## 分片（2026-09-02 补）

新增 `only_files`：指向一个"每行一个 `from_file_name`"的清单，用于把大批量切成多片并行跑。
772 条段落每条要补约 25 条问法、每条问法一次 embedding，合计近 1.9 万次调用，单进程太慢。

并行时报告与回滚文件名会带上清单文件名前缀（`report_<清单名>_execute_*.json`），避免互相覆盖。
`only_file`（单个文件名）与 `only_files` 可同时给，取并集。

## Source

`src/kdb/integrations/data_control/augment_segment_topics.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
