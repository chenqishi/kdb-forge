# 美客多知识库术语对齐挖掘（翻译失真词 → 常用词）

> **状态：2026-08-06 已执行完毕并写入 `mercado_local`。**
> 结果与踩坑见文末「执行记录」。本文前半部分是方案，后半部分是实际结果。

## 背景与目标

美客多巴西/墨西哥知识是从 pt-BR / es 网页翻译后抽 QA 的，部分名词失真，导致**卖家用惯用词搜不到知识**。
典型：知识里写「销售费用」，卖家实际说「佣金」。

目标：产出一张**可验证**的术语对照表 `失真词/直译词 → 常用词`，带类型、站点范围、置信度和证据，
用于提升检索召回，并作为后续翻译的 glossary 防止再次失真。

不是目标：全量重译、批量改写知识原文（改写只对高置信且明显错误的做，且需人工确认）。

## 数据源（均已本地实测连通，2026-08-06）

### A 面 = 失真侧（翻译产出的知识）

ES（`config/config_es_engine.json`，本地可直连）：

| 索引 | QA 总数 | 翻译来源 QA（html+doc+pdf） | 说明 |
|---|---|---|---|
| `mercado_local` | 5690 | 4827+151+45 = **5023** | 本土（巴西/墨西哥） |
| `mercado` | 16491 | 5936+1495+540 = **7971** | 跨境 |

`from_type` 全量分布：
- `mercado_local`：html 4827 / chat_auto 618 / doc 151 / pdf 45 / chat 13 / 其余手工少量
- `mercado`：chat_auto 6992 / html 5936 / doc 1495 / pdf 540 / chat 289 / 其余

**只有 html/doc/pdf 是翻译产物 = 失真嫌疑侧**；`chat_auto`/`chat` 来自真实对话，是天然的口语侧参照。

实测失真样本（`mercado_local`，一次抽样就撞到两类问题）：

> 巴西 除了我的页面的固定费用外，还需要支付哪些费用？
> 除了拥有我的页面的固定费用外，您还需支付**梅卡多 livre**的**销售费用**，就像您现在所做的那样。

`梅卡多 livre` = 音译混排（应为 美客多 / Mercado Livre），`销售费用` = 直译生硬（常用「佣金」）。

### B 面 = 口语侧（真实对话）

`data_chat_history`（`config/mysql_conn_config.json`）实测 customer 分布：

| customer | 条数 |
|---|---|
| `mercado` | 1,332,841 |
| `mercado_local` | **34,268** |
| `mercadochelsea` | 1,917 |
| `mercadoceline` | 269 |
| `test_mercado` | 82 |

用户指定的本土数据 `mercado_local` 存在。**不要私自把 `mercadochelsea`/`mercadoceline` 并进来**
（历史教训：`letain` 不存在于 customer 时也没有私自替换，见 `docs/ecommerce_query_mining_workflow.md`）。

### LLM

`google/gemini-3-flash-preview`，走 `commons/local_llm_adapter.request_knowledge_llm`
（已封装 agents 项目的 `commons/llm_client.py`，渠道配置读 `/Users/chenqishi/stone_fish/agents/config/agent_service_config.json`，
provider=`openrouter`）。**已实测可用**：

```
问：销售费用在美客多中文语境里常被卖家叫作什么？只回答一个词。
答：佣金        （36 prompt tokens / 2 completion tokens）
```

一次答对，印证用户说的「gemini 对美客多数据处理较多」。

## 核心思路

两侧独立挖词，再对齐——**不是让模型凭空想同义词**，而是让它在「知识库里出现的词」和「真实对话里出现的词」之间连线。

```
A 面：翻译 QA（html/doc/pdf）──抽术语──▶ 候选失真词
                                            │
                                            ├─ 强信号：归一化后的偏好倒挂 lean
                                            │         （见下方订正：不是「零频次」）
                                            ▼
                                       LLM 对齐（gemini-3-flash-preview）
                                            ▲
B 面：mercado_local 对话 + chat_auto QA ──抽术语──▶ 常用词表（带频次）
                                            │
                                            ▼
                                       证据校验（检索召回实测）
                                            │
                                            ▼
                                  term_mapping.csv + synonyms_title 回写
```

关键判断信号（不花钱就能拿到）：**A 面词在 B 面对话里的相对偏好**。
LLM 只负责给出对应关系和分类，不负责决定「哪个词是常用的」。

> ⚠️ **执行时订正**：原本设想的「在真实对话里近乎为零」是错的。
> `销售费用` 实际在对话里出现 17 次并不低，卖家只是更爱说「佣金」（197 次）。
> 必须按语料体量归一化后算 lean 才捞得到，详见文末踩坑记录第 1 条。

## 执行阶段

### Phase 0 — 数据一次性落地（之后全离线迭代）

沿用既有约定：**数据库/ES 只下载一次，后续调规则、调 prompt、重跑 LLM 都读本地文件**
（`docs/ecommerce_query_mining_workflow.md` 已确立的做法，避免反复打库）。

- A 面：复用 `data_control_tools/relabel_qa_quality_by_llm.py` 里的 `EsHttpClient` + `download_docs`
  （已有 `iter_search_after` 分页），按 `data_type=qa` + `from_type in (html,doc,pdf)` 下载两个索引 → JSONL
- B 面：复用 `query_understanding_analysis/ecommerce_query_mining.py --mode download_sample`
  （`--customers mercado_local`），已内置寒暄/广告/告警噪声过滤 → JSONL
- B 面补充：ES 里 `from_type in (chat_auto,chat)` 的 QA 也一起下（`mercado_local` 631 条 + `mercado` 7281 条），
  它们是「从对话里长出来的中文」，口语度高

### Phase 1 — 双侧候选术语抽取（纯规则，不调模型）

- 分词/n-gram 聚合出名词短语，按频次收敛
- A 面额外打特征标（**以实际实现为准，下面是设想版**）：
  - **音译特征**：已知音译片段独立扫描。⚠️ 原设想的「中文夹拉丁字母」当音译信号是错的，
    `Full发货系统`、`Mercado Pago账户` 都会误报，实测会把候选表淹掉
  - **偏好倒挂 lean**：归一化后知识库词频率 / 对话词频率 ← 真正的最强信号
  - 零对话频次只是 lean 的一个特例，单独用会漏掉 `销售费用` 这类
- 输出 `candidates_a.csv`（词 + 频次 + 特征标 + 3 条 QA 出处）与 `candidates_b.csv`（词 + 对话频次 + 3 条原话）

这一步把 ~13000 条 QA 收敛到预计几百~一两千个候选词，LLM 成本才可控。

### Phase 2 — LLM 对齐（gemini-3-flash-preview）

分批送「A 面候选词 + 其 QA 上下文片段 + B 面高频词表」，要求结构化输出：

| 字段 | 说明 |
|---|---|
| `source_term` | 知识库里的写法 |
| `canonical_term` | 建议的常用词 |
| `aliases` | 其它可接受说法 |
| `relation` | `音译错误` / `直译生硬` / `术语不一致` / `正确无需改` / `应保留原文` |
| `site_scope` | `巴西` / `墨西哥` / `通用` |
| `confidence` | 0~1 |
| `reason` | 判定依据 |

**`应保留原文` 这一档是必须的**：`Full`、`Mercado Envios`、`Flex`、`Colecta`、`NF-e`、`RFC`、`CPF/CNPJ`
这类专有名词/税务证件保持原样比翻译更好，不能无脑中文化。
**`site_scope` 也是必须的**：巴西和墨西哥的物流/税务术语本就不同，一刀切会把正确的词改错。

### Phase 3 — 证据校验（把「模型说的」变成「可信的」）

三个**不依赖模型自评**的客观校验：

1. **对话频次校验**：`canonical_term` 与 `source_term` 在 `data_chat_history` 的出现次数对比。
   若建议词在真实对话里也几乎不出现 → 打回，说明模型在编。
2. **检索召回实测（最关键）**：拿 `canonical_term` 当 query 检索，
   看含 `source_term` 的那条 QA 能否召回、排第几。
   ⚠️ 搜索服务 `120.77.147.247:8003` 本地不通，实际改为**直连 ES 并逐字复现**
   `es_search_interface.py` 的 BM25 与向量查询，见踩坑记录第 7 条。
   **这直接量化「改了到底有没有用」**——召回没变化的映射没有落地价值。
3. **反向校验**：`source_term` 当 query 是否本来就能召回。防止把本来就好的词改坏。

只有过了校验的才进最终词表；未过的单独存 `rejected.csv` 备查。

### Phase 4 — 产出与落地

主产物 `term_mapping.csv` / `.json`（含上述全部字段 + 三项校验结果）。

三条落地路径，**按风险从低到高**：

| 路径 | 做法 | 风险 |
|---|---|---|
| a) `synonyms_title` 回写 | 把 `canonical_term` 作为同义问写入 QA 的 `synonyms_title`，**并同步追加到 `indexes[]` 生成向量** | **最低，不改原文**。⚠️ 只写字段不补 `indexes` 只有 BM25 生效、向量召回拿不到，见踩坑第 8 条 |
| b) 翻译 glossary | 注入后续翻译流程，防止再次失真 | 中，见下方待确认项 |
| c) 改写 title/content | 仅对 `音译错误` 且高置信的（如「梅卡多 livre」） | 最高，**必须人工确认后再执行** |

默认 **dry-run**，人工审核后才回写（沿用 `relabel_qa_quality_by_llm.py` 的既有约定）。
回写前按既有做法备份（无向量 NDJSON），并保留 rollback 文件。

## 待确认项（**已全部拍板，2026-08-06**）

1. **范围** → 只做 `mercado_local`，且只要 **high 质量 QA**（实际 4632 条）。跨境 `mercado` 未做。
2. **落地到哪** → 词表 + `synonyms_title` 回写 + 高置信音译错误改原文，三条都要。
3. **翻译 glossary** → **不做**，用户明确说用不到 Dify 侧，直接改旧 QA 即可。

## 成本与工期估计

- Phase 0 下载：ES ~13000 条 QA + 3 万条对话，一次性，分钟级
- Phase 2 LLM：候选收敛后预计 ~1000 个词，批量 30/次 ≈ 35 次调用，gemini-3-flash-preview 成本极低
- Phase 3 检索校验：每个候选 1~2 次搜索请求，需搜索服务可达
- 主要人力在 Phase 4 的人工审核

## 复用清单（不新写的部分）

| 能力 | 复用 |
|---|---|
| ES 下载/分页/批量回写 | `data_control_tools/relabel_qa_quality_by_llm.py`（`EsHttpClient`、`download_docs`、`bulk_update_field`、rollback） |
| 对话采样 + 噪声过滤 | `query_understanding_analysis/ecommerce_query_mining.py --mode download_sample` |
| LLM 调用 | `commons/local_llm_adapter.request_knowledge_llm` |
| MySQL 连接 | `commons/mysql_connector.MySQLConnector`（注意：`get_connection()` 只返回 connection，需自己 `conn.cursor()`） |

新写的只有：双侧术语抽取、对齐 prompt、三项证据校验、词表汇总。

---

# 执行记录（2026-08-06 ~ 08-07）

范围按用户指定：`mercado_local` 的 **high 质量 QA**。落地方式：词表 + `synonyms_title` 回写 + 高置信音译错误改原文；**不做** Dify 翻译 glossary（用户明确说用不到）。

## 脚本

| 脚本 | 作用 |
|---|---|
| `query_understanding_analysis/term_alignment_mining.py` | 挖掘，四阶段 `--mode download/extract/align/verify` |
| `data_control_tools/apply_term_alignment.py` | 落地，`--mode synonyms/rewrite/index_backfill/all`，默认 dry-run |

```bash
export PYTHONPATH=$PWD
PY=/opt/anaconda3/envs/py39/bin/python     # 需 jieba/requests/numpy
W=output/mercado_local_term_alignment

$PY query_understanding_analysis/term_alignment_mining.py --mode download
$PY query_understanding_analysis/term_alignment_mining.py --mode extract
$PY query_understanding_analysis/term_alignment_mining.py --mode align    # ~48 批，gemini-3-flash-preview
$PY query_understanding_analysis/term_alignment_mining.py --mode verify

# 先 dry-run 看计划，确认后加 --apply
$PY data_control_tools/apply_term_alignment.py \
  --mapping-file=$W/term_mapping.json --qa-file=$W/qa_translated.jsonl \
  --index=mercado_local --mode=all [--apply]
```

## 数据规模

| 项 | 数量 |
|---|---|
| A 面 high 翻译 QA（html 4437 + doc 151 + pdf 44） | 4632 |
| B 面 high 口语 QA（chat_auto） | 246 |
| B 面真实对话（`data_chat_history` customer=`mercado_local`，仅 send_content） | 26990 |
| 候选术语 | 1200 |
| LLM 对齐产出 | 1144 |

## 最终结论分布

| verdict | 条数 | 落地 |
|---|---|---|
| `synonym` | 366 | 写 `synonyms_title`，影响 **2073 条 QA** |
| `no_action` | 490 | 不动 |
| `rejected` | 286 | 丢弃（多数是建议词在真实对话里 0 次） |
| `rewrite` | 2 | 改原文，影响 **4 条 QA** |

写入结果：`synonyms 2073 更新 / 0 失败`，`rewrite 4 更新 / 0 失败`。
回滚文件在 `output/mercado_local_term_alignment/apply_20260807_020525/`。

改原文的两条：`自由市场 → 美客多`（Mercado Libre 被字面直译成"自由市场"）、
`梅卡多 livre → 美客多`（硬音译）。

## 高价值映射样例（证据俱全）

| 失真词 | 常用词 | 对话频次 失真词→常用词 | 原词能召回 | 常用词能召回 |
|---|---|---|---|---|
| 卖方 | 卖家 | 0 → 2638 | rank 2 | **召回不到** |
| 电子邮件地址 | 邮箱 | 1 → 1181 | rank 4 | **召回不到** |
| 运输费用 / 运输成本 | 运费 | 0 → 432 | rank 11 / 2 | **召回不到** |
| 买方 / 购买者 | 买家 | 0 → 341 | rank 2 / 6 | **召回不到** |
| 全仓 | Full仓 | 0 → 285 | rank 11 | **召回不到** |
| 协作账户 | 子账号 | 0 → 166 | rank 1 | **召回不到** |
| 销售费用 | 佣金 | 17 → 197 | rank 8 | **召回不到** |

「原词能召回、常用词召回不到」正是问题本身，也是这批改动的价值所在。

## 写入后实测

```
查询「销售佣金」   → top1/top2 命中原本写"销售费用"的 QA（靠新同义问）
查询「如何减少佣金」→ top1 = 巴西 有哪些折扣促销方式可以减少销售费用？
查询「卖家」1106 条、「买家」860 条、「Full仓」561 条、「订单号」522 条、「子账号」66 条、「邮箱」23 条
改写后正文：…您还需支付美客多的销售费用…（梅卡多已消除）
改写后向量与新文本 cos=0.999999
```

短 query「佣金怎么算」纯 BM25 下仍打不中（被"怎么办"类 QA 挤掉），
线上是混合检索会好一些；纯词面手段到此为止。

## 踩坑记录（下次直接照做）

### 1. 「对话零频次」不是失真信号，**相对偏好倒挂**才是

第一版按"知识库有、对话没有"筛，**把最典型的目标词整个漏掉**：
`销售费用` 对话里出现 17 次一点都不低，问题是卖家更爱说「佣金」（197 次）。
必须按语料体量归一化后比较：`lean = (kb_rate+1)/(chat_rate+1)`，`销售费用` 实测 lean=4.82。
候选分两池取（零频次池 / 倒挂池各一半），否则零频次词数量太多会把倒挂词全挤掉。

### 2. 抽词只收纯中文

第一版把英文并进名词短语，`Mercado Livre上` 被切出 `Livre上`、`Pago账户`，
候选表前 30 条全是碎片。让拉丁字母和标点当断句点即可。
含拉丁的词（`Full`、`NF-e`）本来就属于"应保留原文"，不需要挖。

### 3. B 面只能用 `send_content`

`reply_content` 是机器人基于知识库回复的，拿它当"口语参照"是**循环论证**——
会把知识库里的失真词又统计回来。

### 4. 改原文必须挡三类模型误判

实测 11 条"音译错误"里有 9 条不能改：

| 类型 | 例子 | 危害 |
|---|---|---|
| 切词碎片截断 | `时所→时`、`金额时→金额` | 互为子串，替换毁句子 |
| 切词碎片改写 | `账时间→回款周期` | 「到账时间」会变成「到回款周期」 |
| 人名音译 | `保拉→Paula`、`毛罗→Mauro` | 改案例正文，无检索收益 |
| 长词碎片 | `木马→轮播图` | 实为 `旋转木马`(carousel) 的碎片，替换出「旋转轮播图」 |

护栏：互为子串拒绝、功能性单字结尾（时/所/间/后…）拒绝、纯拉丁建议词拒绝、confidence≥0.9。
另外"建议词在真实对话 0 次"这一条规则顺手挡掉了人名和 `木马`。

### 5. synonyms_title 生成的三个 bug

- `膳食补充剂` 和 `补充剂` 同时命中 → 生成「膳食**膳食补充剂**」。**长词优先，重叠只取最长**。
- aliases 没经过口语频次/召回校验，产出「如何**机制**闪电活动」「同一**出单**中」等病句。**只用 canonical_term**。
- 常用词本来就在标题里还替换 → 叠词。**先判断 canonical 是否已存在**。

### 6. 改文本必须同步重算向量

真正参与检索的是 `indexes[].embedding`（`MEMORY.md` 2026-07-24 已记）。
好消息是向量**可确定性复现**：搜索服务与挖掘脚本共用 `config/config_ali_embedding.json`
（text-embedding-v3 / 1024 维），实测重算与库存 **cos=1.000000**。
所以回滚备份只存文本，回滚时按旧文本重算即可，不必存 1024 维数组。

注意 `indexes[].text` **不等于 `title`**：它是**不带国别前缀**的原始问题
（title 是 `巴西 xxx？`，indexes.text 是 `xxx？`），要单独做替换，不能拿 new_title 覆盖。

### 7. 环境

- 搜索服务 `120.77.147.247:8003` **本地不通**（empty reply），所以检索校验直连 ES，
  按 `es_search_interface.py` 逐字复现 BM25（`multi_match title^2/content^1.5/indexes.text` +
  `match synonyms_title^1.8`）和向量（`nested indexes.embedding cosineSimilarity`）。
- `commons/mysql_connector.MySQLConnector.get_connection()` **只返回 connection**，
  需自己 `conn.cursor()`，且 `close_connection(conn, cursor)` 要两个参数。
- 模型偶发错别字 relation（`直育生硬` 20 条），已在 `RELATION_ALIASES` 归一化。

## 未做 / 可继续

- `mercado`（跨境索引，7971 条翻译 QA）没做，客群和口语词与本土不同，建议单独跑一套。
- 366 条 synonym 只按 **title** 匹配写入；`销售费用` 这类还有 12 条只出现在正文里的 QA 没覆盖到
  （按正文匹配会污染同义问，是有意为之）。
- 词表可以反向用于后续翻译的 glossary，本次按用户要求没做。

### 8.（重要补记）只写 `synonyms_title` 只能拿到一半效果

本次先用 ES `_bulk` 直接写 `synonyms_title`，后来核对搜索服务 `/insert` 才发现漏了一步：

`knowledge_interface_tools/search_index_data_interface.py:463-482` 的 `insert_data` 会把
**`synonyms_title` 的每一条也追加进 `indexes[]` 并各自生成 embedding**。

所以只写字段本身的结果是：

| | 效果 |
|---|---|
| `synonyms_title` 字段 | 有 |
| BM25 词面召回（`match synonyms_title^1.8`） | ✅ 生效 |
| **向量召回** | ❌ **不生效**，`indexes[]` 里没有同义问条目 |

「`synonyms_title` 是纯文本字段、不涉及向量」这个判断是**错的**——
字段本身确实是文本，但标准入库流程会从它**派生**出带向量的索引条目。

补救：`apply_term_alignment.py --mode index_backfill`，复刻 `insert_data` 那段逻辑
（保留原有 indexes + 追加同义问 + 各自生成向量）。2073 条已补齐，0 失败。

两个实现要点：
- `indexes` 是**全量替换**，必须「读旧的 + 追加」，不能只写新的
  （`insert_data:513` 也注明 indexes 不允许在更新时被清空）
- **必须跨文档合批算向量**。第一版逐条调用产生 2000+ 次串行请求，10 分钟没跑完被打断
  （所幸代码是先全量规划再批量写，中断没有产生半写状态）

补齐后实测向量检索：

```
「降低佣金的方法」→ top1 巴西 有哪些折扣促销方式可以减少销售费用？(0.741)
                    top2 巴西 如何参与促销活动以降低销售费用？(0.711)
                    top3 巴西 参与促销活动以降低销售费用的条件是什么？(0.700)
```

**下次直接结论**：往已有 QA 上加同义问，要么走 `/insert`（原 `_id`，服务自动处理），
要么直接写 ES 时**同时**更新 `synonyms_title` 和 `indexes[]`，只写前者等于白做一半。

### 9. 写入的是哪套 ES

本次写入 `config/config_es_engine.json` → 阿里云 serverless
`for-kuajing-bot-a4d.public.cn-shenzhen.es-serverless.aliyuncs.com:9200`，索引 `mercado_local`。
`config_for_search_index.json` 的 `search_engine_config_path` 指向的也是这套。

仓库里还有 `config/config_es_engine_aws.json`（东京 OpenSearch
`search-marsmindes-...ap-northeast-1.on.aws`），**本地网络不通，本次没有往那边写过任何数据**。
如果线上实际跑在 AWS 那套，这批改动需要另行同步。
