# kdb.mining.chat.query_analysis.ecommerce.mine_queries

## Signature

`mine_queries(mysql_config_path: str, customers: Sequence[str], start_time: Optional[str], end_time: Optional[str], users: Optional[Sequence[str]]=None, app_ids: Optional[Sequence[str]]=None, raw_limit: int=20000, max_candidates: int=1000, max_queries: int=500, batch_size: int=50, sample_per_query: int=2, model_name: Optional[str]=None, provider: Optional[str]=None, output_dir: str='output/ecommerce_query_mining', require_reply: bool=True, skip_llm: bool=False, per_theme_limit: int=0) -> dict`

## Description

端到端执行电商平台知识覆盖率测评 query 挖掘：SQL 聚合候选、小批样本、规则过滤、LLM 泛化、去重排序、输出文件。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| mysql_config_path | str | 是 | MySQL 配置路径 |
| customers | list[str] | 是 | customer 白名单 |
| start_time | str\|None | 否 | 起始时间 |
| end_time | str\|None | 否 | 结束时间 |
| users | list[str]\|None | 否 | user 白名单 |
| app_ids | list[str]\|None | 否 | app_id 白名单 |
| raw_limit | int | 否 | SQL 聚合候选上限 |
| max_candidates | int | 否 | 进入 LLM 的候选上限 |
| max_queries | int | 否 | 最终输出 query 上限 |
| batch_size | int | 否 | LLM 批大小 |
| sample_per_query | int | 否 | 每个候选样本数 |
| model_name | str\|None | 否 | 低成本 LLM 模型 |
| provider | str\|None | 否 | LLM 渠道 |
| output_dir | str | 是 | 输出目录 |
| require_reply | bool | 否 | 是否要求已有回复 |
| skip_llm | bool | 否 | 是否跳过 LLM，仅规则化 |

## Outputs

| 类型 | 说明 |
|------|------|
| dict | 运行结果摘要和输出文件路径 |

## SQL

- 只读 `data_chat_history`。
- 读取字段：`id`、`customer`、`send_type`、`send_content`、`reply_content`、`msg_id`、`content_category`、`norm_content`、`regular_content`、`create_time`、`channel_type`、`user`、`app_id`。
- 写操作：无。
- 表结构来源：2026-07-19 只读 `SHOW COLUMNS FROM data_chat_history`。

## Source

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
