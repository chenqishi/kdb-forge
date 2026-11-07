# kdb.mining.query_analysis.ecommerce_query_mining.download_random_sample

## Signature

`download_random_sample(mysql_config_path: str, customers: Sequence[str], sample_size: int, sample_output_path: str, start_time: Optional[str], end_time: Optional[str], users: Optional[Sequence[str]]=None, app_ids: Optional[Sequence[str]]=None, require_reply: bool=True, per_customer_even: bool=True, random_seed: Optional[int]=None) -> dict`

## Description

端到端执行一次数据库随机抽样下载，将 `data_chat_history` 中指定 customer 的文本聊天记录保存为本地 JSONL。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| mysql_config_path | str | 是 | MySQL 配置路径 |
| customers | list[str] | 是 | customer 列表 |
| sample_size | int | 是 | 总抽样条数 |
| sample_output_path | str | 是 | JSONL 输出路径 |
| start_time | str\|None | 否 | 起始时间 |
| end_time | str\|None | 否 | 结束时间 |
| users | list[str]\|None | 否 | user 白名单 |
| app_ids | list[str]\|None | 否 | app_id 白名单 |
| require_reply | bool | 否 | 是否要求回复非空 |
| per_customer_even | bool | 否 | 是否按 customer 均分 |
| random_seed | int\|None | 否 | MySQL RAND seed |

## Outputs

| 类型 | 说明 |
|------|------|
| dict | 下载摘要，含样本路径、总数、按 customer 计数 |

## SQL

通过 `fetch_random_chat_sample` 只读 `data_chat_history`；本函数不直接执行 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
