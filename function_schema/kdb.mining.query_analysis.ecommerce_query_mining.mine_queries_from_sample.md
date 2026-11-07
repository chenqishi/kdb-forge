# kdb.mining.query_analysis.ecommerce_query_mining.mine_queries_from_sample

## Signature

`mine_queries_from_sample(sample_path: str, max_candidates: int=1000, max_queries: int=500, batch_size: int=50, sample_per_query: int=2, model_name: Optional[str]=None, provider: Optional[str]=None, output_dir: str='output/ecommerce_query_mining', skip_llm: bool=False, per_theme_limit: int=0) -> dict`

## Description

只基于本地随机样本挖掘电商平台覆盖率测评 query，不访问数据库。执行候选统计、LLM 泛化、去重排序和输出。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| sample_path | str | 是 | 本地 JSONL 样本路径 |
| max_candidates | int | 否 | 进入 LLM 的候选上限 |
| max_queries | int | 否 | 最终 query 上限 |
| batch_size | int | 否 | LLM 批大小 |
| model_name | str\|None | 否 | 模型名 |
| provider | str\|None | 否 | LLM 渠道 |
| output_dir | str | 是 | 输出目录 |
| skip_llm | bool | 否 | 是否跳过 LLM |
| per_theme_limit | int | 否 | 每主题保留上限 |

## Outputs

| 类型 | 说明 |
|------|------|
| dict | 运行摘要和输出路径 |

## SQL

无 SQL；该函数保证不访问数据库。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
