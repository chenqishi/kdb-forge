# Architecture Overview Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        External Clients                             │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ HTTP POST
          ┌─────────────────┼──────────────────────┐
          │                 │                      │
          ▼                 ▼                      ▼
┌──────────────────┐ ┌─────────────────┐  ┌──────────────────────────┐
│  Search Service  │ │  Task Control   │  │   CSAT Report Service    │
│  (FastAPI :8000) │ │ (Flask :6000)   │  │   (Flask :7100)          │
│                  │ │                 │  │                          │
│ /search          │ │ /start_task     │  │ POST /csat_report        │
│ /insert          │ │ /task_info      │  │  ├─ verify_signature()   │
│ /delete          │ │ /stop_task      │  │  │   md5(secret+ts)      │
│ /update_by_cond  │ │ /health         │  │  │   timestamp ≤5min     │
│ /modify_knowledge│ └────────┬────────┘  │  └─ query_csat_sessions()│
│ /web_search      │          │           └──────────┬───────────────┘
│ /get_value_coll  │          │                      │
└────────┬─────────┘          │                      │
         │                    │               ┌──────┴──────────────┐
         ▼                    │               │  Config Files       │
┌─────────────────────────────┤               │  csat_auth_config   │
│  knowledge_interface_tools  │               │  {client: secret}   │
│  SearchDataInterface        │               └──────────────────────┘
│  ├─ insert_data()           │
│  ├─ search_data()           │               ┌──────────────────────┐
│  └─ delete_data()           │               │  data_csat_result    │
│                             │               │  (MySQL)             │
│  EsSearchInterface          │               ├──────────────────────┤
│  ├─ vector search           │               │  data_online_sessions│
│  ├─ BM25 hybrid             │               │  (MySQL)             │
│  └─ index management        │               └──────────────────────┘
└──────────┬──────────────────┘
           │
    ┌──────┴──────────────────────────────────┐
    │              commons/                   │
    │  embedding_tools  (Aliyun DashScope)    │
    │  dify_tools       (LLM workflows)       │
    │  simility_tools   (semantic dedup)      │
    │  schema_trans     (format conversion)   │
    │  sql_tools        (MySQL)               │
    │  mysql_connector  (connection pool)     │
    │  es_http_client   (raw ES, read-only)   │
    └──────┬──────────────────────────────────┘
           │
    ┌──────┴──────────────────────────────────┐
    │           External Storage              │
    │  Elasticsearch / OpenSearch  (search)   │
    │  MySQL                       (tasks/chat│
    │  MinIO / S3                  (files)    │
    │  Aliyun DashScope            (embed)    │
    │  Dify                        (LLM)      │
    └─────────────────────────────────────────┘
```

## Payoneer Chat Mining (offline pipeline)

```
data/payonner/chat_data_sample_*.xlsx
        │
        ▼
┌──────────────────────────────────────────────┐
│ payoneer_chat_mining/                        │
│                                              │
│  data_loader.load_and_group_chat()           │
│        │ (按 Content.接收人 分组, 时间排序)   │
│        ▼                                     │
│  conversation_segmenter.segment_group()      │
│        │ (>500 条按 1 天间隔切, 200 条硬上限)│
│        ▼                                     │
│  ┌──────────────────────────┐                │
│  │ rag_suitability_classifier│ ─┐            │
│  │ (openai/gpt-5.4-mini)     │  │            │
│  └──────────────────────────┘  │            │
│                                ├─ llm_client │
│  ┌──────────────────────────┐  │ (OpenRouter)│
│  │ qa_extractor              │ ─┘            │
│  │ (google/gemini-3-flash-   │               │
│  │   preview)                │               │
│  └──────────────────────────┘                │
│        │                                     │
│        ▼                                     │
│  pipeline.run_pipeline()                     │
└──────────────────────────────────────────────┘
        │
        ▼
output/payoneer/
  ├─ customer_questions_classified.xlsx (任务1)
  ├─ extracted_qa_pairs.xlsx            (任务2: q/a + is_high_quality + is_general)
  ├─ run_metadata.json
  └─ cache/{task1,task2}/<hash>.json     (重跑命中)
```

## CSAT Report Service — Auth & Data Flow

```
Client Request (POST /csat_report)
  │  body: {start_time, end_time, channel_type, client, signature, timestamp}
  │
  ▼
verify_signature(client, signature, timestamp, client_secrets)
  ├─ timestamp within 5 min?  → 401 timestamp expired
  ├─ client in secrets?       → 401 unknown client
  └─ md5(secret+ts)==sig?     → 401 invalid signature
  │  ✓ pass
  ▼
query_csat_sessions(mysql, start_time, end_time, channel_type, client)
  ├─ SELECT data_csat_result  (filter: create_time range + channel_type + client)
  ├─ SELECT data_online_sessions (filter: session_id IN <csat sessions> + channel)
  ├─ Group messages by session_id
  ├─ For each survey: determine time window → filter messages
  │     survey[0]: lower = last "正在帮您转人工" before survey_time (or session start)
  │     survey[i]: lower = surveys[i-1].create_time
  └─ Build output: survey_instance_id, query_session_id, session_create_datetime,
                   escalated, escalation_datetime, satisfaction, chat_detail
  ▼
Response JSON {code, message, data}
```

## Zhiqu external_id → cid 映射 cron

```
┌──────── 人工触发（账号增减/改名时跑一次）────────┐
│                                              │
│  data_control_tools/                         │
│    build_zhiqu_assistant_id_map.py           │
│      ① 拉 rfwkt corp=1970325020467087        │
│        (美国国际销售深圳代表处) 的 16 个       │
│        we_com_account.nick_name              │
│      ② 拉致趣 contact/list 聚合 user_owner    │
│      ③ 按 nick_name 撞                       │
│      ④ 落 config/zhiqu_assistant_id_map.json  │
│        (zhiqu employee_user_id ↔ rfwkt uid)   │
└──────────────────────────────────────────────┘
                  │
                  ▼  (cron 只读 json)
┌──── crontab: 0 * * * *  ────────────────────────────────────┐
│  control_script/zhiqu_external_id_map_cron.sh               │
│         │                                                   │
│         ▼                                                   │
│  data_control_tools/build_zhiqu_external_id_map.py          │
│    1. load config/zhiqu_assistant_id_map.json (16 项 scope) │
│    2. fetch 致趣 contact/list 全量 (~96k)                   │
│    3. filter owner.employee_user_id ∈ map → in-scope ~32k   │
│    4. wecom_name_matcher.match_within_scope                 │
│       scoped_index = 同账号 + name → cid，两表并集：         │
│         ├─ rf_wkt_we_com_contact  (75.9% 客户)              │
│         └─ lm_channel_contact     (43.2%，与上表互补)        │
│       并集 86.4%；企微口径下约 99.6%                          │
│    5. 候选 cid:                                             │
│       └─ 1 个 → 差集 INSERT data_scrm_id_map                 │
│       │        (cid, client, type='zhiqu_external_id', sid)  │
│       ├─ 0 个 → logs/unmatched_zhiqu_*.tsv                   │
│       └─ ≥2 → logs/ambiguous_zhiqu_*.tsv (歧义不写库)        │
│    6. 已存在 (cid, sid) 跳过 → 幂等                          │
└─────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌──── /inner_external_user_id_map 查询双通道 ────┐
│  single_service/user_id_map_query.py           │
│    Step 1: data_scrm (cid + customer_profile)  │
│    Step 2: data_scrm_id_map (双 type IN ...)    │
│            ├─ 致趣 → external_id (优先字段)    │
│            └─ 公众号 → external_ids 列表       │
│    Step 3: 输出 {cid, email,                   │
│                 external_id (致趣或 null),      │
│                 external_ids: [{id, source}]}  │
└────────────────────────────────────────────────┘
```

桥接事实：`rf_wkt_we_com_contact.we_com_contact_user_id` (数字) ≡ `data_scrm.cid`。
致趣 `wx_external_userid`（wm/wo... 形式）不直接在 rfwkt 表里，要通过 `name + 同账号 scope`
反查 `we_com_contact_user_id` 间接拿到 cid。

好友名称索引的数据源是**两张表的并集**（2026-08-19 起），二者互补，缺一都会丢客户：

| 表 | 助手字段 | cid 字段 | 名称字段 | 过滤 |
|---|---|---|---|---|
| `rf_wkt_we_com_contact` | `we_com_user_id` | `we_com_contact_user_id` | `we_com_contact_nick_name` / `real_name` | `relation_type=2 AND type=1 AND del_flag=0` |
| `lm_channel_contact` | `account_id` | `user_id` | `nickname` / `real_name` | `del_flag='0'`(字符串) AND `channel_type='we_com_wkteam'` AND `user_id<>account_id` |

`lm_channel_contact` 的 `channel_type` 另有 `wx_wkteam`（个人微信，`account_id` 为 `wxid_*`），
这类客户不在企微好友体系内、拿不到致趣 external_id，必须过滤掉。

## Generic Mining Context Enrichment (document_qa_segment_mining / html_kg_gen_task_control)

通用文档与 HTML 网页挖掘流程的可选业务上下文增强（默认关闭，新增 task 字段全部缺省时旧流程不变）。

```
stage_2 文档解析
   │   ├── PDF 图片优先用 PyMuPDF rendered image blocks，仅导出页面实际绘制图片
   │   └── rendered block 提取异常时回退 legacy page.get_images() 资源提取
   ▼
stage_3 多模态处理
   │   ├── 每个 content.json 预扫描本地图片内容 SHA-256
   │   ├── image_hash_blacklist_threshold 默认 10，超过阈值的 hash 加黑名单
   │   └── 黑名单图片跳过上传 / OCR / 图片理解
   ▼
stage_4 翻译
   │
   ▼
stage_4_5 构建业务上下文 ── business_context_builder.build_business_context
   │   ├── 前端 business_context_text（最高优先级）
   │   ├── chat_query_context.load_client_queries + summarize_query_intents  (enable_chat_query_context)
   │   └── web_business_context.build_web_business_context  (enable_web_context, 默认关闭)
   │   → data/off_task_data/<task>/business_context.json
   │   → data/business_context_cache/ctx_<hash>.json  (共享缓存，命中后不重复挖 query)
   ▼
stage_5 QA生成
   │   ├── 文档：knowledge_clear_by_dify_model_longcontent (llm_backend: dify|local_llm|auto)
   │   │        dify 后端先按页硬分段（默认 ≤40 页/80k 字符），再语义分段
   │   │        QA 抽取前再限制 ≤10 页/30k 字符；local_llm 经 commons.local_llm_adapter.request_knowledge_llm
   │   └── HTML：knowledge_html_clear_by_dify（沿用 Dify，附加业务抽取约束）
   ▼
stage_6 QA质量(dify) → stage_6_5 通用质量后处理 ── generic_knowledge_quality
   │   repair_self_contained_knowledge_rows + filter_business_quality_rows
   │   → generic_quality_report.json（悬空指代/栏目泛标题/boilerplate）
   ▼
stage_7 schema → stage_8 ES插入  (review_only=true 时跳过)
   ▼
stage_9 段落生成（文档 Dify 同样先按页硬分段 ≤40 页/80k 字符，再限制 index 输入 ≤10 页/30k 字符；HTML 沿用 Dify 并附加业务抽取约束）
   → stage_10 schema → stage_11 ES插入 (review_only 跳过)
```

关键开关字段：`enable_context_enrichment` / `enable_chat_query_context` / `enable_web_context` /
`business_context_text` / `knowledge_objective` / `llm_backend` / `llm_model_name` / `llm_provider` /
`quality_profile` / `review_only` / `business_context_cache_dir`。默认缓存目录为
`data/business_context_cache`，cache key 由 `client + knowledge_objective + business_context_text + context sources`
组成；同类任务在 TTL 内复用上下文，避免重复挖掘用户 query。文档 local LLM 调用统一经
`commons/local_llm_adapter.py`，复用 agents 项目 `commons/llm_client.py`，Dify 作为兼容回退。
所有子来源不可用时降级，不中断主任务。

## Ecommerce Coverage Query Mining (offline evaluation set)

从 `data_chat_history` 挖掘电商平台知识覆盖率测评 query 的离线流程，不写库、不进入 ES，仅产出评测集文件。推荐先随机下载本地样本，再基于本地样本反复挖掘。

```
data_chat_history (MySQL)
  │  one-time random sample download
  ▼
query_understanding_analysis/ecommerce_query_mining.py
  │
  ├─ download_random_sample()
  │    只读随机抽样，写本地 JSONL 样本
  │
  ▼
local random_sample.jsonl
  │
  ├─ mine_queries_from_sample()
  │    后续挖掘只读本地样本，不访问数据库
  │
  ├─ build_candidate_stats_from_rows()
  │    regular_content -> norm_content -> send_content，按 msg_id/id 去重计数
  │
  ├─ is_meaningful_query() / is_business_query() / is_noise_text()
  │    过滤寒暄、企业微信提示、广告、纯 @、电话/微信等噪声
  │
  ├─ merge_candidate_stats()
  │    Python 规范 key 二次合并，消除不可见字符和空白变体
  │
  ├─ llm_generalize_batch()
  │    低成本 LLM 小批泛化为自包含测评 query
  │    └─ fallback_generalize_batch()  (模型失败时规则兜底)
  │
  └─ merge_records() + sanitize_query_text() + normalize_platform_specific_query() + build_platform_queries() + write_outputs()
       去重、按主题/优先级排序、清理 @ 聊天痕迹、过滤告警/通知噪声、生成 {platform} 模板和平台实例化 query
       │
       ▼
output/ecommerce_query_mining/<run>/
  ├─ candidates.csv
  ├─ coverage_queries.csv             (query + norm_query template + platform_queries)
  ├─ coverage_queries_by_platform.csv (platform + instantiated query)
  ├─ coverage_queries.jsonl           (query + norm_query template + platform_queries)
  └─ report.md
```

推荐流程：`--mode download_sample --sample-size 10000~20000` 先落本地样本；然后
`--mode mine_sample` 反复调候选、prompt 和模型参数。`max_candidates` 控制 LLM 成本，先小批
`--skip-llm` 验证规则链路，再用 `openai/gpt-4.1-mini` 等低成本模型跑候选泛化。详细流程见
`docs/ecommerce_query_mining_workflow.md`。

## Stock QA Quality Relabeling (存量质量重打标)

给**已经入库**的 QA 重新判定质量并改写 `quality_level`。用于质检规则收紧后回补存量——
`chat_qa_extract/prompts/quality.<client>.md` 的新规则只作用于新产出，旧数据需要单独跑一遍。

```
ES <index> (from_type=chat_auto, data_type=qa, quality_level=high)
  │  search_after 分页（Serverless 不支持 scroll）
  ▼
data_control_tools/relabel_qa_quality_by_llm.py
  │
  ├─ build_target_query()        按 from_type 过滤，不用 from_type_norm（存量有中英两种写法）
  ├─ download_docs()             → work-dir/downloaded.jsonl  (_id / q=title / a=content / old_level)
  │
  ├─ is_protocol_safe()          正文含 ### / 问题: / 答案: → 跳过不动
  ├─ relabel_all()               分块并发；整块退化不写缓存，重跑自动重试
  │    └─ relabel_chunk()
  │         qajson_to_line_text(add_index=True)
  │           → chat_qa_extract.QaQualityFilter.request_dify()   (prompts/quality.<client>.md)
  │           → qa_text_tools.parse_qa_quality_result()
  │           → context_dice 对齐校验（对不上 = 保持原档位，不降 mid）
  │           → judge_level_strict()   降级标签优先于 #优质
  │
  ├─ build_report()              → work-dir/report.json（transitions + 分组样例）
  │                              → work-dir/decisions.jsonl（新旧标签审计线索）
  │
  └─ [--execute] apply_updates() → work-dir/rollback.jsonl，再 _bulk 只写 quality_level
                                   （413 自动折半重试）
```

### 存量 QA 去重（`data_control_tools/dedup_qa_by_llm.py`）

给**已经入库**的 QA 做去重软删。与重打标正交：重打标改 `quality_level`，去重改 `del_flag`。

```
ES <index> (data_type=qa, del_flag=0)
  │  search_after 拉元数据 + title_embedding（ES 里已存，不重新调 embedding 接口）
  ▼
data_control_tools/dedup_qa_by_llm.py
  │
  ├─ download_docs()            → work-dir/{meta.jsonl, vec.npy}，行已 L2 归一化，命中缓存不重拉
  │
  ├─ build_candidate_groups()   **全库唯一一次匹配**：本地 numpy 分块点积
  │     ├─ 同类目分块           category_path 不同的对直接丢（chewy/bol 同名问题答案不同）
  │     ├─ 阈值只做召回          真重复 0.883 / 假重复 0.963，区间重叠，阈值不能直接删
  │     └─ 贪心成簇             种子按 _survivor_rank 排，全簇受保护的簇不送 LLM
  │
  ├─ judge_all_groups()         一簇一次调用（不是一对一次），并发 + 按「id 集合 + prompt 指纹」缓存
  │    └─ judge_group()         chat_qa_extract.llm_client.request_llm (models.quality)
  │         三分类 dup / junk / distinct；坏 JSON 重试 3 次；
  │         簇外 id → 整簇作废，漏返 id → 补 distinct（只会少删不会多删）
  │
  ├─ plan_deletions()           保护规则：audit_result ∈ {1,2} 永不删；
  │                             一个 dup 组里 ≥2 条已审核 → 一条都不删，进 manual_review.jsonl
  │                             存活优先级：已审核 > high > mid > low > 答案更长 > insert_time 更新
  │                             → work-dir/decisions.jsonl
  │
  └─ [--execute] apply_deletions() → work-dir/rollback.jsonl，再 _bulk 只写 del_flag + flag
                                     （不动 audit_result / quality_level / update_time / 向量）
```

默认 dry-run。只写 `quality_level` 一个字段，不动 `audit_result` / `ext_info.quality_info`。
检索侧默认条件是 `(quality_level=high AND audit_result∈[1,2,-1]) OR audit_result∈[1,2]`，
所以对 `audit_result∈[-1,0]` 的数据只改 `quality_level` 即可下线；
对 `audit_result∈[1,2]` 的数据则**不够**。详见 `docs/payoneer_olive_quality_relabel.md`。

### 存量知识广告清洗（`data_control_tools/filter_ad_knowledge_by_llm.py`）

给**文档挖掘产出**的知识清掉第三方服务商广告。与去重正交：去重删「重复」，这里删「广告」，
两者都只改 `del_flag` + `flag`，跑的顺序是先去重再清广告（避免代表条被广告批次删掉）。

```
ES <index> (del_flag=0, from_type ∈ doc/pdf/html/unknown)   ← 群聊来源默认不进
  │  search_after 拉元数据（**不拉向量**，本方案不做向量召回）
  ▼
data_control_tools/filter_ad_knowledge_by_llm.py
  │
  ├─ download_docs()            → work-dir/meta.jsonl，命中缓存不重拉
  ├─ group_by_source_file()     按 ext_info.from_file_name 分组（广告的粒度是来源文档）
  │
  ├─ judge_all_files()          **每篇一次调用**，三分类 all_ad / mixed / clean
  │    └─ pick_file_sample()    一半名额给促销词命中的条目顶进样本
  │                             （关键词只做抽样偏置，精确率太低不能当判据）
  │        判定失败 → 降级 mixed 交给条目级；--force-all-ad-file 可人工指定整篇下线
  │
  ├─ judge_all_items()          只判 mixed 文档的条目，20 条一批，并发 + 按「id 集合 + prompt 指纹」缓存
  │    └─ judge_item_batch()    送模型的 id 用批内短序号 n1/n2/…，不是 32 位 hex `_id`
  │                             （让模型回抄 hex 一批必错一两个，整批作废 → 一次丢 20 条）
  │
  ├─ plan_deletions()           all_ad → 整篇删；mixed → 逐条判；clean → 一条不删
  │                             判不出来就不删；audit_result=1 进 manual_review.jsonl
  │                             （默认**不**保护 audit_result=2：2 是机审给 high 打的，广告大多是 2）
  │                             → work-dir/{file_report.jsonl, deletions.jsonl}
  │
  └─ [--execute] apply_deletions() → work-dir/rollback.jsonl，再 _bulk 只写 del_flag + flag
```

判定口径：只删「主语是第三方公司、内容是它的商业报价/联系方式/引流」的条目；
平台自己的补贴、激励、冷启计划、佣金优惠一律保留（那是卖家真要查的政策）。
方案与现场盘点见 `docs/payoneer_olive_ad_clean_plan.md`。

## Platform Category Backfill (存量知识按平台回填类目)

群聊自动学习出来的 QA 全挂在「默认分组」，按平台筛不出来。抽取时给标题打的平台前缀
（`chewy-`、`Bol-`、`P-New GC#23621 -Bol-…`）是唯一可用信号。

```
ES <index> (del_flag=0；data_type / quality_level 默认不限)
  │  search_after 分页
  ▼
data_control_tools/assign_platform_category.py
  │
  ├─ load_flat_category_map()    线上类目树 → 一级类目名 → categoryId（别名表里有线上没有的会直接报错）
  ├─ download_docs()             → work-dir/downloaded.jsonl（title + 现有类目字段，文件在就复用）
  │
  ├─ PlatformMatcher.match()     前缀整段 → 段内 token → 短段子串 → 全文搜索 → exclude 否决
  │    别名表 category_sys_manager/data/payoneer_olive_platform_aliases.json
  │    （aliases / prefix_only / non_platform_prefix / exclude 四块，加平台不用改代码）
  │
  ├─ plan_assignments()          默认只动「默认分组」；--include-no-category 才碰无 primary_category 的
  ├─ build_report()              → work-dir/{report.json, decisions.jsonl}
  │
  └─ [--execute] apply_updates() → work-dir/rollback.jsonl，再 _bulk 只写
                                   category_infos + primary_category（413 自动折半重试）
```

默认 dry-run。**不覆盖已经分到具体平台的**（那些是人工/其它流程分好的）。
两个反复踩到的口径问题见 `docs/payoneer_olive_category_backfill.md`：
①「无 `primary_category`」在前端同样显示为「默认分组」，但按类目名过滤筛不出来；
② 类目和 `quality_level` 正交，别用质量档位缩过滤范围。

## Login-Gated Online Doc Crawl (登录态在线文档爬取)

把外部在线文档（飞书 docx/wiki、企微文档、腾讯文档）按 `<平台>/<站点>` 归档到本地，
供后续文档挖掘链路消费。和 `web_batch_crawler.py` 的分工：后者是公开站点的广度 BFS 爬取，
本链路是清单驱动、需登录态、正文虚拟滚动渲染的富文本。

```
Chrome 调试实例（独立 user-data-dir + --remote-debugging-port=9222，登录态常驻）
  │  Chrome 136+ 默认 profile 上该端口会被忽略，必须给独立目录
  ▼
login_doc_crawler.run_crawl(manifest)
  │
  ├─ load_url_manifest()      → [{platform, site, url, doc_type}]
  │
  ├─ doc_type=lark / wecom ──▶ playwright connect_over_cdp（不经 chromedriver）
  │     ├─ is_login_page()      登录页 / 「没有权限访问」页 → status=need_login
  │     ├─ scroll_and_harvest() 逐屏采集块 → merge_blocks 去重 → 按绝对偏移排序
  │     └─ page.on('response') 截获图片响应体（脚本内 fetch 会 401）
  │
  ├─ doc_type=tencent ───────▶ dop-api/opendoc（canvas 渲染，DOM 抓不到）
  │     └─ decode_tencent_attributed_text() base64+protobuf → 文本片段，
  │        在 Word 样式表特征行处截断，截断前先捞图片直链
  │
  ├─ doc_type=web ───────────▶ 普通网页（卖家大学/帮助中心/公众号）
  │     └─ 按实测的正文容器选择器框正文，都没命中则退回「文本最长的容器」
  │
  ├─ doc_type=pdf ───────────▶ 在线 PDF 阅读器
  │     └─ capture_pdf_bytes() 截页面自己加载的 PDF 响应体 → PyMuPDF 解析
  │        （不要 import wordtotext，它顶层的 docx 依赖会在本机直接炸）
  │
  ├─ doc_type=lark_sheet ────▶ 飞书表格（canvas 渲染，数据走 WebSocket）
  │     └─ copy_sheet_via_clipboard() 点网格 → 全选 → 复制 → 读剪贴板 → TSV
  │        复制前必须写哨兵串：失败时读到的是上一张表的残留（静默串数据）
  │        _detect_copy_forbidden() 认出「文档禁止复制」，与技术故障分开
  │
  └─ write_doc_outputs() → data/<client>/<平台>/<站点>/
                             {content.md, content.txt, blocks.json, page.html, images/, meta.json}
                           + <root>/crawl_manifest.json
                             （write_crawl_manifest 按 (platform,site) **合并**写：
                              多份清单共用一个 root 时，覆盖会静默抹掉上一批）
                                      │
                                      ▼
data_control_tools/build_doc_mining_tasks.py
  ├─ 上传 images/ → MinIO，把 content.md 里的 `images/x.png` 改写成公网 URL
  │   （parse_txt_to_json 只下载 http 图片，相对路径会被静默降级成文本）
  ├─ 上传改写后的 md → MinIO（任务侧走 S3 API 拉，不需要公开读）
  ├─ 类目：站点有二级类目挂二级（TikTok Shop-<站点>），否则挂平台一级；缺失直接报错
  └─ POST /start_task  task_type=document_qa_segment_mining（**一篇一个任务**，
                        因为 category_id 是任务级字段）
                        enable_context_enrichment / enable_chat_query_context = true
                        enable_web_context = false
```

平台目录名与线上一级类目名严格一致，后续灌库 `category_name` 直接用目录名。
详见 `docs/payoneer_olive_doc_crawl.md`。

## Single-Page Local Crawl (单页本地抓取旁路)

补一两个 URL、只要本地审核产物不入 ES 时的轻量旁路。绕开 `html_kg_gen_task_control`
（要 MySQL + 远程类目 API、stage 列表硬编码）和 Selenium（chromedriver 版本锁死，
且 Mercado `vendedores/nota` 卖家页在 Selenium 下会卡住）。

```
single_page_local_crawl.crawl_single_page
  │  requests 直取 HTML（不起浏览器）
  │  + Dify firecrawl workflow 取正文 ── 卖家页唯一可靠正文源
  │  复用 WebBatchCrawler 的两个 @staticmethod：
  │    get_filename_from_url / extract_formatted_text_by_flat（不触发 chromedriver 初始化）
  ▼
<slug>.json + crawler_and_process_results_<FLAG>.txt   ← 与 stage 2 输出完全同构
  │
  ├─ knowledge_translate_by_dify   --process_field=firecrawl_content → translated_text
  ├─ knowledge_html_clear_by_dify  --process_field=translated_text   → {high, mid}
  ├─ qa_quality_tools              re_clear                          → {high, mid, low}
  └─ single_page_local_crawl.export_local_qa_result
                                   → qa_result_<FLAG>.json + manifest_<FLAG>.json
```

同构是关键：后三步全部复用现有 CLI，无新逻辑。跳过 stage 3 多模态，
所以 `process_field` 走 `firecrawl_content` / `translated_text`，
**不能**用默认的 `content_with_multimodal_unsderstanding`（字段不存在会整页静默跳过）。
详见 `docs/mercado_br_seller_nota_local_crawl.md`。

## Firecrawl 正文抽取（2026-08-08 起改为直连）

三条爬取路线里凡是 `use_firecrawl=True` 的正文抽取，统一走 `commons/firecrawl_tools.py`，
**不再经 Dify workflow**。

```
web_batch_crawler.process_crawl_url ─┐
single_page_local_crawl.crawl_single_page ─┴─▶ firecrawl_tools.fetch_firecrawl_content
                                                 │  build_cookie_headers 归一 cookie
                                                 │  （仓库里 auth_config['cookie'] 一直是
                                                 │    "k=v; k2=v2" 裸串，firecrawl 要 {"Cookie": ...}）
                                                 ▼
                            POST {firecrawl_api_base}/v2/scrape
                            formats=[markdown] onlyMainContent=1 timeout=30000 waitFor=0
                            （默认值逐项抄自 data/网页爬取url.yml，换实现后产物形态不变）
```

token 在 `config/global_config.json` 的 `firecrawl_api_key`（**该文件已 gitignore**）。

为什么换掉 Dify：原 workflow 用的插件 `langgenius/firecrawl:0.0.3` 的 `headers` 已坏 ——
任何非空 header（哪怕只是 `User-Agent`）都让它 `status=succeeded` 却返回**空串**，
cookie 因此传不进去。空串还会被当正文写盘、下游整页静默跳过而任务显示成功。
直连官方 API 同样参数正常。详见 `docs/wayfair_developer_zh_content_20260807.md`。

## Site Content-API Fetch (站点内容 API 直取)

第三条爬取路线。前两条的分工是：`web_batch_crawler.py` 公开站广度 BFS（Selenium）、
`login_doc_crawler.py` 登录态富文本（playwright CDP）。本路线面向
**SPA + 正文由前端调内容 API 取** 的站点 —— 这类站点渲染出来的 HTML 骨架里没有正文，
而且**多语言常常不体现在 URL 上**（Wayfair 开发者门户就只靠 cookie 切语言），
浏览器抓取既慢又拿不准语言，不如直接调它自己的接口。

```
knowledge_crawler_tool/web_crawl/wayfair_developer_portal_fetch.py
  │
  ├─ extract_urls_from_excel   Excel 单元格超链接 → URL（值是标签，URL 在 cell.hyperlink.target）
  ├─ parse_post_url            /posts/<slug>                → post
  │                            /posts/docs/<apiId>/reference/<proto>/<ver> → reference
  ▼
POST https://api.wayfair.io/content/v1/developer-portal-bff/graphql   （免鉴权）
  │   同域 public/ 403、v1/ 401，只有 content/ 开放
  │
  ├─ post      → query Post($slug,$locale) → Contentful Rich Text JSON
  │              → richtext_to_html（本地渲染，18 种节点 + 4 种 mark，封闭集合）
  │
  └─ reference → query ReferenceHtml($where)，中文版 apiId 拼 "-zh-CN" 后缀
                 → SpectaQL HTML；**9 个里 8 个是无 <body> 的片段，必须补包装**
                    判断不能用 '<body' 子串 —— 代码示例里内嵌了 52 处 <html><body>
  ▼
data/wayfair/html/<slug>.html   （slug 复用 WebBatchCrawler.get_filename_from_url，
  + manifest_wayfair_dev_<locale>_<flag>.json    与既有产物、ES from_file_name 对齐）
```

产物带 `<body>` 是硬约束：下游 `extract_formatted_text_by_flat` 找不到 `<body>` 返回 `""`，
会在 `knowledge_html_clear_by_dify.py:146` 被静默 `continue` 掉。
详见 `docs/wayfair_developer_zh_content_20260807.md`。

## Term Alignment Mining (术语对齐挖掘)

把翻译失真词对齐到卖家常用词（`销售费用`→`佣金`），提升检索召回。
不是让模型凭空想同义词，而是在「知识库里的词」和「真实对话里的词」之间连线。

```
A面 翻译QA(html/doc/pdf, high)  ──jieba抽纯中文术语──┐
B面 data_chat_history send_content + chat_auto QA ──┤
   （只用 send_content：reply_content 是知识库喂出来的，当口语参照是循环论证）
                                                     ▼
                       归一化偏好倒挂 lean = (kb_rate+1)/(chat_rate+1)
                       分两池取（零频次/音译池 + 倒挂池），避免互相挤占
                                                     ▼
                       LLM 对齐（gemini-3-flash-preview，走 local_llm_adapter）
                       relation: 音译错误/直译生硬/术语不一致/正确无需改/应保留原文
                                                     ▼
                       证据校验（都不依赖模型自评）
                         ① 常用词在真实对话里的频次（为0则判定模型在编）
                         ② 用常用词检索能否召回该QA（量化「改了有没有用」）
                         ③ 反向校验，防止把好词改坏
                                                     ▼
                       term_mapping.csv/json + verdict
                         synonym → synonyms_title 追加（不动原文）
                         rewrite → 改 title/content，**必须同步重算 indexes[].embedding**
```

脚本：`query_understanding_analysis/term_alignment_mining.py`（挖掘）、
`data_control_tools/apply_term_alignment.py`（落地，默认 dry-run + rollback）。
详见 `docs/mercado_term_alignment_mining_plan.md`（含 7 条踩坑）。

## Module Responsibilities

| Module | File | Role |
|---|---|---|
| Search Service | `knowledge_database_search_service/src/knowledge_database_search_es.py` | FastAPI主服务，知识库搜索/插入/删除；uvicorn `workers=4`（`SEARCH_SERVICE_WORKERS` 可覆盖，=1 回落单进程）|
| Search Interface | `knowledge_interface_tools/search_index_data_interface.py` | 核心编排：embedding、去重、类目映射 |
| ES Adapter | `knowledge_interface_tools/es_search_interface.py` | ES/OpenSearch 查询构建与执行；召回默认走 **dual 双路**（BM25 一路 + 向量一路合并去重，`extra_params.recall_mode` 可回退 `legacy`）。两路命中同一条时保留先到的那份，并把另一份的 `indexes[].embedding` 合并进来——只有向量路带得回 embedding，不合并会让 `_cal_title_similarity` 的同义问法分支静默失效（详见 `function_schema/es_search_interface.search_multi.md`）；`_ensure_index` 每进程每索引只跑一次，存量索引是否自动 `put_mapping` 由 `extra_params.auto_update_mapping` 控制（默认关）|
| Task Control | `control_service/off_task_control_service.py` | 异步任务队列，MySQL 状态持久化 |
| CSAT Service | `single_service/csat_report_service.py` | CSAT 报告服务，含签名鉴权 |
| CSAT Query | `single_service/csat_data_query.py` | CSAT 数据查询与时间窗口分组逻辑 |
| Commons | `commons/` | 共享工具：embedding、Dify、相似度、MySQL |
| Payoneer Mining | `payoneer_chat_mining/` | 离线挖掘：RAG 适配性分类 + 对话 QA 抽取（OpenRouter LLM） |
| Chat QA Extract | `chat_qa_extract/` | 本地 QA 抽取/质检，替代两个 Dify 流；按 client 追加 `prompts/{extract,quality}.<client>.md` |
| Stock QA Relabel | `data_control_tools/relabel_qa_quality_by_llm.py` | 存量 QA 质量重打标：ES 下载 → LLM 重判 → 只写回 `quality_level`，默认 dry-run |
| QA Dedup | `data_control_tools/dedup_qa_by_llm.py` | 存量 QA 去重：复用 ES 已存的 `title_embedding` 本地向量召回（零 embedding 成本）→ 一簇一次 LLM 三分类裁决（dup/junk/distinct）→ 只写回 `del_flag=1` + `flag`，已审核永不删，默认 dry-run 带 rollback |
| Ad Filter | `data_control_tools/filter_ad_knowledge_by_llm.py` | 文档挖掘知识广告清洗：按 `ext_info.from_file_name` 分组 → 每篇一次 LLM 判 all_ad/mixed/clean → 只对 mixed 文档逐条判 → 只写回 `del_flag=1` + `flag`，人工审核通过的不删，默认 dry-run 带 rollback |
| Content Redaction | `data_control_tools/redact_content_terms.py` | 按人工审定的改写清单改知识正文（如把竞品收款平台名单摘成只留自家）：plan 自检 → 并发校验现值 → 只写 `content` + `content_embedding` + `multimodal_contents` → realtime GET 逐条复查，回滚只存文本（向量可确定性重算），默认 dry-run |
| ES HTTP Client | `commons/es_http_client.py` | 裸 HTTP ES 客户端（search_after / _count / terms agg / _bulk 局部更新）；只读脚本用它绕开 `EsSearchInterface.__init__` 建索引改 mapping 的副作用，Serverless 也不支持 scroll。注意 `terms_agg` 的 `size` 硬编码 50，类目多时会静默截尾 |
| Platform Category Backfill | `data_control_tools/assign_platform_category.py` | 存量知识按平台回填类目：从 `title` 识别平台（前缀 → 段内 token → 短段子串 → 全文，带否决词）→ 只写回 `category_infos` + `primary_category`，默认 dry-run 且只动「默认分组」 |
| QA Excel Export | `data_control_tools/export_qa_to_excel.py` | 按来源类型导出有效 QA 到 Excel：search_after 拉取 → 拍平（含 `primary_category` 类目、来源中文标签）→ 复用 `trans_es_data_to_excel`，双重行数对账 |
| Login Doc Crawler | `knowledge_crawler_tool/web_crawl/login_doc_crawler.py` | 清单驱动的在线文档爬取（飞书 docx/表格、企微、腾讯文档、普通网页、在线 PDF 六类宿主），CDP 连已登录 Chrome，处理虚拟滚动 |
| Doc Mining Dispatcher | `data_control_tools/build_doc_mining_tasks.py` | 把爬到的本地文档上传 MinIO 并按站点类目投递成带上下文增强的文档挖掘任务 |
| Single Page Local Crawl | `knowledge_crawler_tool/web_crawl/single_page_local_crawl.py` | 单 URL 本地抓取（requests + firecrawl，不起浏览器），产出 stage2 同构文件供现有 CLI 复用 |
| Site Catalog Dump | `knowledge_crawler_tool/web_crawl/mx_catalog_dump.py` | **爬之前先盘站点目录**：学习中心 search-cards API + 帮助中心 knowledge-hub BFS + ayuda 搜索三路发现，与 ES 比对算未爬清单并按主题分桶；只发 GET + `_search`。避免拿首页当种子只抓到几十个 URL |
| Term Alignment Mining | `query_understanding_analysis/term_alignment_mining.py` | 翻译失真词→常用词挖掘：双侧抽词 + 偏好倒挂 + LLM 对齐 + 检索召回校验 |
| Gap Material Coverage | `query_understanding_analysis/gap_material_coverage.py` | **灌库前**先测「缺口 query ↔ 已爬材料」覆盖：按 `## 小节` 边界切块（盲切会让块向量代表开头那段、答案永远召不回）→ 关键词+向量双路召回（中文口语 query × 英文材料，关键词跨不过去）→ DeepSeek 判 covered/partial/missing，报告自带 `top_k` 口径。配套爬虫 `knowledge_crawler_tool/web_crawl/bol_partner_portal_fetch.py`（sitemap 驱动、抽 HTML 小节） |
| Unanswered Query Review | `query_understanding_analysis/wayfair_unanswered_review.py` | 线上答不上来的 query 复检：`data_chat_history` 里命中兜底话术的对话 → DeepSeek 多路改写/补全 → 线上同款检索合并 → DeepSeek 判 covered/partial/missing，区分「真缺知识」与「只是没召回/被精排否掉」；定时入口 `control_script/run_wayfair_unanswered_review.sh` |
| Term Alignment Apply | `data_control_tools/apply_term_alignment.py` | 词表落 ES：synonyms_title 追加 / 原文改写（同步重算向量），默认 dry-run |
| Business Context Builder | `knowledge_clear_tool/business_context_builder.py` | 通用业务上下文构建/缓存（前端+chat+web 合并） |
| Chat Query Context | `knowledge_clear_tool/chat_query_context.py` | 从 data_chat_history 提炼用户高频意图（可降级） |
| Web Business Context | `knowledge_clear_tool/web_business_context.py` | 可选网络业务背景（默认关闭，缓存） |
| Generic Knowledge Quality | `knowledge_clear_tool/generic_knowledge_quality.py` | 通用质量后处理：悬空指代/栏目泛标题修复 + boilerplate 过滤 |
| Local LLM Adapter | `commons/local_llm_adapter.py` | 统一 LLM 调用层，复用 agents llm_client，Dify 兼容回退 |
| Dify Workflow Client | `commons/dify_tools.py` | Dify blocking workflow 调用封装，支持按调用方配置 timeout/max_retries |
| Segment Builder | `knowledge_generate/knowlege_segment_builder_by_dify.py` | 文档 segment 生成；长文按硬分页窗口分段，Dify 漏页时按固定页段补齐 |
| User ID Map Query | `single_service/user_id_map_query.py` | 聚合 cid / email / external_id（致趣 + 公众号双通道） |
| Zhiqu Contact Fetcher | `data_control_tools/zhiqu_contact_fetcher.py` | 致趣 OpenAPI 客户端（token 缓存 + 分页） |
| WeCom Name Matcher | `data_control_tools/wecom_name_matcher.py` | 同账号 scoped 姓名匹配公共模块 |
| Zhiqu Assistant ID Map | `data_control_tools/build_zhiqu_assistant_id_map.py` | 一次性脚本：构建 zhiqu employee_user_id ↔ rfwkt we_com_user_id |
| Zhiqu External ID Map Cron | `data_control_tools/build_zhiqu_external_id_map.py` | cron 主流程：致趣 wx_external_userid → data_scrm.cid |

## 检索链路上的索引自检（`_ensure_index`）

```
/search ─► SearchDataInterface.search_data_by_query
             │  embedding(query)
             ▼
           EsSearchInterface.search_multi
             │
             ├─► _get_index_name(index_names)
             │      对每个索引：has_build_index 里有？── 有 ──► 直接返回
             │                        │
             │                       没有
             │                        ▼
             │                   _ensure_index
             │                     ├ 索引不存在 ──► indices.create（完整 mapping）
             │                     └ 索引已存在 ──► update_index_map
             │                            ├ 缺失字段 ──► auto_update_mapping 开？
             │                            │                ├ 开 ──► put_mapping
             │                            │                └ 关 ──► 只记日志（默认）
             │                            └ 已存在但不一致 ──► 记 warning 并跳过该字段
             │                     无论 mapping 是否同步成功，都置位 has_build_index
             │
             └─► _msearch（每索引 top size，全量 _source）
```

### 三个已修的坑（2026-08-19）

1. **`has_build_index` 永远不置位**：原来只在 `update_index_map` 返回 `True` 时才记，
   而该函数对线上每个索引都 raise → 缓存失效 → **每次检索**都重跑一遍，
   双索引检索多打 6 次 ES 元数据请求（实测 50–60ms/请求），
   并把 `es_search_service.log` 刷出 ≥168MB 重复 ERROR（占日志 30%）。
   现改为「本进程检查过就记住」——mapping 不兼容是永久性的，重试无意义。

2. **mapping 比对有三类假冲突**（`_mapping_config_equal`）：
   线上 ES **7.10.0** 的 `dense_vector` 只支持 `dims`，代码里写的
   `similarity: cosine` / `index: false` 会被静默丢弃（实测所有索引的实际 mapping 都是
   `{"type":"dense_vector","dims":1024}`）；`type: object` ES 不回显；
   nested 的 `properties` 原来整体 `!=` 比对。三类合起来让每个索引都判「配置发生变化」。

3. **一个真冲突连坐掉整个同步**：`task_id`（线上 `text` vs 代码 `keyword`，9 个索引）
   原来一 raise 就掐掉整个函数，导致本该新增的字段也一直加不上。现改为跳过该字段继续。

### 为什么 `auto_update_mapping` 默认关

修好比对逻辑后 dry-run 全量索引，放开会一次性写到 **66 个索引**
（`categorys_info` 66、`task_id`/`multimodal_contents` 各 59、`dataset`/`primary_category` 各 22），
且发生在检索热路径上。mapping 字段类型**写进去就改不了**——代码里 `dataset` 是
`{"type":"keyword","index":False}`，`index:false` 对 keyword 是真生效的，
固化后按 `dataset` 做 term 过滤会报 `Cannot search on field [dataset] since it is not indexed`
（`mars_mind` 已踩过）。存量索引补字段应走一次性运维脚本，不该由检索路径顺带完成。


## 召回：双路合并（2026-08-20 起默认）

```
query ──► text2embedding ──► search_multi
                                 │
              ┌──────────────────┴──────────────────┐
              │  一次 _msearch 发出 索引数 × 2 个子请求  │
              ▼                                      ▼
      ┌───────────────┐                     ┌────────────────┐
      │  BM25 路       │                     │  向量路          │
      │ multi_match    │                     │ nested          │
      │  title^2       │                     │ script_score    │
      │  content^1.5   │                     │ cosineSimilarity│
      │  indexes.text  │                     │ score_mode:max  │
      │ synonyms^1.8   │                     │                 │
      │ + nested boost0│◄── 只为拿 inner_hits │                 │
      │   各取 size//2  │                     │  各取 size//2    │
      └───────┬───────┘                     └────────┬───────┘
              └───────────► 按 _id 去重合并 ◄──────────┘
                                 │
                    _source 排除 indexes[].embedding
                    inner_hits 带回 top3 项(text+embedding)
                    按 _nested.offset 塞回 doc['indexes'] 原位
                                 │
                                 ▼
                  本地 _cal_similarity 重排（代码一行未改）
```

### 为什么拆两路
BM25 分量级 26~107、cosine 量级 0~1，融合相加时**向量子句对总分的贡献中位数只有 0.92%**，
去掉它 top80 候选集重合度仍有 99% —— 融合模式下向量那一路等于没参与召回。
而纯向量 top10 与纯 BM25 top10 只重合 0~6/10，向量能捞到「库存可自己修改吗」
「PIS/COFINS Discount 字段适用于什么场景」这类语义相关但字面不撞的知识。

### 为什么下游一行不用改
`_source` 只排除 `indexes.embedding` 子字段，`doc['indexes']` 仍是完整的 N 项（每项有 `text`）；
`inner_hits` 每项带 `_nested.offset`，按下标把 embedding 填回原位。
`_cal_title_similarity` 本来就写着 `and index_info.get('embedding')`，没补到向量的项被自动跳过。

实测：两种模式下共有的 2949 条文档 `similarity` **逐位相同、0 条不同**。

### mercado_local 是最慢的索引组，原因就是回传体积
调用方传 `top_k=40` → `size*2=80`，双索引各取 80 条，每条 `_source` 139KB（97.5% 是向量），
单次回传 **46MB**。改造后 14.9MB。

```
           p50       p90       单query回传
legacy    4.361s    6.025s      46.34 MB
dual      2.080s    3.544s      14.94 MB   ↓52% / ↓68%
```

### 已知取舍
向量路补进来的候选**质量参差**：top1 重合 86.7%，变化的那部分需要人工看样本判断好坏。
`_cal_similarity` 衡量的是「问题像不像」（title 向量相似度 + 0.2×content），不是「答案对不对」，
这个局限与本次改造无关，legacy 下同样存在。


## 并发：单进程串行 → 4 个 worker

11 个 handler 全是 `async def` 包同步阻塞 IO，**全部在事件循环上串行**。
实测吞吐恒定 0.78 req/s、延迟随并发线性增长（并发 8 时 p50 10.6s）。

改为 `workers=4` 后（本地同机同网络对照，唯一变量是 workers）：

```
              workers=1              workers=4
并发2     0.40 req/s  4.83s     0.89 req/s  1.90s
并发4     0.43 req/s  8.75s     1.09 req/s  2.91s
并发8     0.46 req/s 16.79s     1.22 req/s  5.72s
内存        191 MB                 824 MB
```

### 天花板在阿里云 ES，不在进程数
拆开量过：单请求 1.40s = embedding 0.26s(I/O) + 网络与 ES 0.98s(I/O)
+ 客户端 JSON 解析 0.16s(CPU) + 本地重排 0.01s(CPU)，**I/O 占 88%**。
DashScope 并发 8 仍是 28.8 req/s、延迟纹丝不动，不是瓶颈；
阿里云 ES 该查询形态并发 4 约 1.87 req/s、并发 8 不再增长——**worker 再加也吃不到**。

### 一个必须记住的耦合
更早试过 `workers=4` 但**完全无效**（吞吐仍 0.82 req/s）。原因是当时 BM25 路还挂着
`boost:0` 的 nested，ES 天花板只有 1.22 req/s 而单进程已跑到 0.78，没有空间。
**先减 ES 负载（去掉那个 nested），多进程才有意义。** 只调进程数不看下游天花板会白忙。

### 容量与需求
8/19 实测需求峰值 1.90 req/s（10 秒窗口）、瞬时最多 3 req/s，
服务器利用率 17.2%（最忙小时 54%）——秒级突发而非持续过载。4 个 worker 够用且有余量。

### 回滚
`SEARCH_SERVICE_WORKERS=1` 重启即可，不用改代码。

## ES8.17 按索引路由边界（2026-09-30）

旧的 `EsSearchInterfaceOri`（ES 7.10）和 `EsSearchInterfaceOpen`（OpenSearch 2）保持原有默认选择；配置明确声明 `es_version: "es8.17"` 或 `"es8"` 时，工厂选择 `EsSearchInterfaceES8`。ES8 实现位于 `knowledge_interface_tools/es8_search_interface.py`，路由器位于 `es8_client_router.py`，业务层 `SearchDataInterface`、HTTP 接口和两级结构不变。

```text
SearchDataInterface / HTTP
          │  只传 index
          ▼
EsSearchInterface (factory)
   ├─ 无版本 / es7  ─► EsSearchInterfaceOri (ES7 legacy)
   ├─ opensearch     ─► EsSearchInterfaceOpen
   └─ es8.17         ─► EsSearchInterfaceES8
                              │
                 IndexClientRouter.resolve_provider(index)
                      ├─ Serverless client (8.17)
                      └─ PaaS client (8.17)
                              │
                BM25 query + native nested KNN (HNSW)
```

ES8 向量字段必须是 `dense_vector(index=true, similarity=cosine, index_options.type=hnsw)`；检测到旧的未索引 ES7 mapping 会 fail closed，提示新建目标索引并 reindex，不会原地改生产 mapping。`search_multi_by_page` 保持 BM25-only 分页，普通 `search_multi` 的 dual 模式按每索引、每路预算召回后去重。所有 ES8 search/count/aggregation 请求检查 `_shards.failed` 和超时并重试，耗尽直接报错，避免把部分结果当成空结果。

ES8 运行时使用独立环境安装 `requirements-es8.txt` 中的 `elasticsearch>=8.17,<8.18`；项目旧服务的 `requirements.txt` 仍锁定 `elasticsearch==7.10`，不在同一解释器中静默切换客户端。
