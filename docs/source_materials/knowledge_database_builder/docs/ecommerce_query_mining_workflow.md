# 电商平台覆盖率测评 Query 挖掘流程

## 目标

从 `data_chat_history` 中挖掘适合评测智能客服知识覆盖率的通用 query。适用场景是电商平台入驻、开店、KYC/资质、商品刊登、运营营销、订单物流、费用结算、售后风控等问题集合建设。

## 脚本

推荐入口：先随机下载本地样本，再基于样本挖掘。

```bash
python query_understanding_analysis/ecommerce_query_mining.py \
  --mode download_sample \
  --customers mercado,letain,wayfair \
  --start-time 2026-06-20 \
  --end-time 2026-07-20 \
  --sample-size 10000 \
  --sample-output-path output/ecommerce_query_mining/random_sample_mercado_letain_wayfair_recent_1m_20k.jsonl \
  --random-seed 20260720 \
  --no-per-customer-even \
  --no-require-reply
```

然后只基于本地样本挖掘：

```bash
python query_understanding_analysis/ecommerce_query_mining.py \
  --mode mine_sample \
  --sample-input-path output/ecommerce_query_mining/random_sample_mercado_letain_wayfair_recent_1m_20k.jsonl \
  --max-candidates 600 \
  --max-queries 350 \
  --batch-size 50 \
  --sample-per-query 2 \
  --per-theme-limit 90 \
  --output-dir output/ecommerce_query_mining/random_sample_recent_1m_20k_mined \
  --model-name openai/gpt-4.1-mini \
  --provider openrouter
```

只验证本地样本规则链路，不调用模型：

```bash
python query_understanding_analysis/ecommerce_query_mining.py \
  --mode mine_sample \
  --sample-input-path output/ecommerce_query_mining/random_sample_mercado_letain_wayfair_recent_1m_20k.jsonl \
  --max-candidates 120 \
  --max-queries 60 \
  --batch-size 40 \
  --output-dir output/ecommerce_query_mining/random_sample_rules \
  --skip-llm
```

## 流程

1. 数据库只负责一次随机抽样下载：`download_sample` 将 `data_chat_history` 文本聊天记录落为本地 JSONL。
2. 后续调规则、调 prompt、重跑 LLM，都走 `mine_sample`，只读取本地 JSONL，不再访问数据库。
3. 本地候选字段优先级：`regular_content` -> `norm_content` -> `send_content`。
4. Python 层过滤寒暄、企业微信提示、广告、卖群、电话/微信、纯 @ 助手等噪声。
5. 按 `normalize_query_key` 合并候选，消除不可见字符、大小写和空白变体。
6. 小批量调用低成本 LLM，把聊天式候选泛化成自包含 query；模型失败时使用规则泛化兜底。
7. 最终执行 `sanitize_query_text`，去掉 @ 人名/助手名、邮箱、长数字订单号/店铺 ID。
8. 通过 `is_alert_noise_query` 过滤告警、通知、消息更新、状态提醒类噪声。
9. 通过 `normalize_platform_specific_query` 增加 `norm_query` 模板，把平台实例替换成 `{platform}`；美客多明确站点会整体作为平台实例，例如 `美客多墨西哥站点`，不再拆成 `美客多平台 + 墨西哥站点`。
10. 根据 `source_customers/platform_scope/query` 抽取目标平台，生成 `target_platforms/platform_queries`，并额外输出按平台展开的一行一 query 文件。

## 输出

每次运行输出：

- `candidates.csv`：规则过滤和合并后的候选及样本。
- `coverage_queries.csv`：测评 query 主文件，适合人工审阅；包含原始 `query`、占位符模板 `norm_query`、`target_platforms` 和 `platform_queries`。
- `coverage_queries_by_platform.csv`：按平台展开的一行一 query 文件，适合直接导入评测。
- `coverage_queries.jsonl`：同内容 JSONL，适合程序读取。
- `report.md`：运行参数、主题分布、Top query；Top 30 中展示 template 和平台实例化 query。

本次随机样本产物：

- 随机样本（推荐使用）：`output/ecommerce_query_mining/random_sample_mercado_letain_wayfair_15k_no_reply_required.jsonl`
- 挖掘结果：`output/ecommerce_query_mining/random_sample_mercado_wayfair_10k_mined/`
- 清洗后推荐使用版：`output/ecommerce_query_mining/random_sample_mercado_wayfair_10k_mined_clean/`

最近 1 个月 2w 产物（当前推荐）：

- 时间范围：`2026-06-20` 到 `2026-07-20`
- 随机样本：`output/ecommerce_query_mining/random_sample_mercado_letain_wayfair_recent_1m_20k.jsonl`
- 挖掘结果：`output/ecommerce_query_mining/random_sample_recent_1m_20k_mined/`
- 清洗后推荐使用版：`output/ecommerce_query_mining/random_sample_recent_1m_20k_mined_platform_placeholder/`
- 推荐模板文件：`output/ecommerce_query_mining/random_sample_recent_1m_20k_mined_platform_placeholder/coverage_queries.csv`
- 推荐评测导入文件：`output/ecommerce_query_mining/random_sample_recent_1m_20k_mined_platform_placeholder/coverage_queries_by_platform.csv`

本次样本情况：

- 请求样本：`mercado,letain,wayfair` 总 15,000，按 customer 均分。
- 实际样本：10,000，其中 `mercado=5000`、`wayfair=5000`。
- `letain` 在 `data_chat_history.customer` 中未命中，未私自替换为其它 customer。

最近 1 个月 2w 样本情况：

- 请求方式：`--no-per-customer-even --sample-size 10000`，即每个 customer 最多抽 10,000。
- 实际样本：20,000，其中 `mercado=10000`、`wayfair=10000`、`letain=0`。
- 本地业务候选：5,505
- 进入 LLM 候选：600
- 模板 query：335
- 按平台展开 query：336，其中 `Wayfair=230`、`美客多平台=100`、`美客多巴西站点=3`、`美客多墨西哥站点=2`、`美客多美国站点=1`、`Letain=0`
- `norm_query` 全部包含 `{platform}`；告警/通知类命中为 0。

本次随机样本 clean 版统计：

- 本地样本记录：10,000
- 本地业务候选：2,571
- 进入 LLM 候选：500
- 最终 query：234

历史 Mercado 聚合产物：

- 小批规则验证：`output/ecommerce_query_mining/mercado_small_rules/`
- 小批 LLM 验证：`output/ecommerce_query_mining/mercado_small_llm/`
- 20k 聚合 + 500 候选 LLM：`output/ecommerce_query_mining/mercado_20k_llm/`
- 清洗后推荐使用版：`output/ecommerce_query_mining/mercado_20k_llm_clean/`

## 已知注意事项

- 优先使用 `download_sample -> mine_sample`。只有需要复查全库高频分布时才使用旧的 `db_aggregate`。
- `letain` 本次在 `data_chat_history.customer` 中不存在；需要用户确认真实 customer 名后再补抽并合并。
- 不要在 `send_content/norm_content/regular_content` 长文本字段上做 SQL `REGEXP` 预过滤，实测会显著拖慢大表查询。
- 远端 MySQL 连接偶发超时，脚本已对连接创建做 3 次重试。
- LLM 网络偶发 SSL EOF 或 fallback 超时。脚本会按批次降级到规则泛化；如果需要更高质量，可对失败批次后续重跑或提高模型稳定性。
- `coverage_queries.csv` 中 `reason=规则泛化` 的行质量略低，适合人工复核后进入最终评测集。
