# payoneer_olive 自动学习 QA 质量重打标

日期：2026-08-05

## 背景

`payoneer_olive` 索引里自动学习（`from_type=chat_auto`）产出的 QA，`quality_level=high` 档
大量是**个案对话流水**而不是可复用知识，全部被旧质检判成 `#优质` 进了 high，污染检索：

```
Q: ebay-我已经提交了ebay的入驻申请
A: 我们已经收到了您通过橄榄枝计划线上开店平台提交的表格, 会尽快进行审核和推进。

Q: chewy-你的证明信还没开吧            A: 开了
Q: bol-你这边就用一个入驻哈            A: 我们只能给你入驻一个
Q: Bol-GC#23176 -76343569（EU）-…     A: 1 填写你现有的最好的链接…
```

根因和 joint_login 一样：旧 Dify「qa选择过滤」流的 `#优质` 门槛太松。
`chat_qa_extract` 已经针对 joint_login 收紧过一版（见 `docs/chat_qa_extract_local_migration.md`），
但那只作用于**新产出**，存量从未回补。

原始 chat history 数据源已不在，本次**只重新打标，不重新抽取**。

## 生产现状（执行前，直连 ES 只读核实）

ES 是 `config/config_es_engine.json` 里的阿里云 Serverless 集群，**本机可直连**，不用上 `main`。

- 索引 `payoneer_olive` 真实文档 14964 条
  （`_cat/indices` 的 30896 含 nested 子文档，**不是真实条数**，对账要用 `_count`）
- 自动学习 QA = `from_type=chat_auto` + `data_type=qa`，共 **14050** 条，`del_flag` 全 0
- **`from_type_norm` 有两种历史写法**：`auto_learning` 12141 + `自动学习` 1909。
  `knowledge_tools.get_from_norm_type` 后来把中文改成英文但存量没迁移，
  **按 `from_type_norm` 过滤会漏掉 1909 条，必须按 `from_type=chat_auto` 过滤。**
- 质量分布 high 6312 / mid 4894 / low 2844
- `audit_result`：-1 共 11206（= high + mid），0 共 2844（= 全部 low）

## 本次口径

| 项 | 决定 |
|---|---|
| 重打标范围 | 只重打 `quality_level=high` 的 6312 条 |
| 写回字段 | **只写 `quality_level`**，不动 `audit_result` / `ext_info.quality_info` / `update_time` |
| 判定输入 | **只用 Q/A**，不喂群聊上下文——判定标准就是「脱离上下文也成立」 |

检索侧默认条件是
`(quality_level=high AND audit_result∈[1,2,-1]) OR audit_result∈[1,2]`
（`search_index_data_interface.py:698-704`）。本批 `audit_result` 只有 -1/0，
所以**只改 `quality_level` 就足以把差 QA 挡在检索之外**。

> 若将来对 `audit_result∈[1,2]` 的数据做同样的事，只改 `quality_level` **不够**，
> 必须同时把 `audit_result` 改掉。

## 实现

### 1. `chat_qa_extract/prompts/quality.payoneer_olive.md`

按 client 自动追加，零代码改动（`quality_filter.py:84-90`）。
payoneer_olive 的质量问题和 joint_login 不一样，规则按实际抽样重写：

| 规则 | 标签 |
|---|---|
| 0. **平台前缀不是个案标识**（`chewy-` / `Bol-` / `Trendyol-`）——先写这条，否则模型大面积误伤 | — |
| 1. 问题不是可复用的问题：陈述汇报 / 名词短语 / **进度催办** / 问卖家自身情况 / 索要联系方式 | `#不通用` |
| 2. 答案是空确认（`可以的`/`对`/`开了`）、时效性传闻、客服模板回执 | `#无实质答案` |
| 3. 个案标识：`GC#23176`、公司名、人名、邮箱、店铺链接、金额、税号 | `#不通用` |
| 4. 主体指代不清（`这个到时能改吧？`） | `#不清晰` |
| 5. 内部办事流水 / 转派口吻（`表单我可以驳回 稍等一下`） | `#不通用` |
| 6. 答非所问 | `#不相关` |
| 7. `#优质` 门槛：换个卖家换个店铺依然成立 + 自足 + 属于平台规则/资质/材料/步骤/费用时效/原因解释 | `#优质` |
| 8. 禁止 `#优质` 与降级标签共存；不确定标 `#不通用` | — |

规则 1.3（进度催办）、1.4（卖家自身情况）、2.2（时效性传闻）是**第一轮抽样后补的**：
首轮只降了 36%，这几类漏杀最多；补完后降级率升到 39~52%，且没有引入误伤。

标签→档位沿用 `quality_tools/qa_quality_tools.py:13-17`。

### 2. `data_control_tools/relabel_qa_quality_by_llm.py`

通用脚本（index / client / 过滤条件都是参数），joint_login 的存量回补可以直接复用。

```
download (search_after) → relabel (分块并发 LLM) → report → [--execute] bulk 写回 quality_level
```

三条**不能错**的语义（全部有单测覆盖）：

1. **判不出来就不动**。模型少回条 / 文本对不上（`context_dice < 0.9`）/ 返回为空 →
   `new_level = old_level`，记 `skip_reason`。
   生产流程 `add_quality_info_to_qa_json_by_dify` 对不上是**强制降 mid**，
   重打标绝不能这么干。
2. **无标签 ≠ mid**。`QaQualityFilter` 对齐失败时整批退化成「原文无标签」，
   如果按「模型判成 mid」处理，一批 20~40 条 high 会被静默降级。
   实测首次全量跑就触发了 4 次整块退化——这个兜底是必需的，不是理论风险。
   整块未判出时**不写块缓存**，重跑自动重试。
3. **降级标签优先于 `优质`**。`judge_qa_quality` 是 HIGH 优先，
   `['优质','不通用']` 会判成 high；这里反过来（`judge_level_strict`）。

其它工程细节：

- 正文含 `###` / `问题:` / `答案:` 的 QA 会破坏分隔协议，**直接跳过不动**（`is_protocol_safe`）
- ES 走裸 HTTP（`requests`）不引 `elasticsearch` 客户端：
  本机没装该包；Serverless 不支持 `scroll` 只能 `search_after`；
  且 `EsSearchInterface.__init__` 会 `_ensure_index` 建索引/改 mapping，只读场景不能碰
- 写回只发 `new_level != old_level` 的文档，写前先落 `rollback.jsonl`
- `_bulk` 遇 `413` 自动折半重试（Serverless 单请求 15MB 上限）
- 默认 dry-run，`--execute` 才写 ES；每阶段产物落盘可断点续跑

## 运行环境

本机 `/usr/bin/python3`（Python 3.9），**不用上 `main`**：
LLM 凭证 `config/llm_config.json` 只在本机有（gitignore），生产 ES 本机可直连。

```bash
pip3 install --user openpyxl pytest    # 唯一缺的依赖
```

## 使用

```bash
# 1) 抽样 dry-run，人工看降级是否合理（必过的闸门）
/usr/bin/python3 data_control_tools/relabel_qa_quality_by_llm.py \
    --index payoneer_olive --client payoneer_olive --limit 100 \
    --batch-size 20 --concurrency 3 \
    --work-dir output/payoneer_olive_relabel_sample

# 2) 全量 dry-run
/usr/bin/python3 data_control_tools/relabel_qa_quality_by_llm.py \
    --index payoneer_olive --client payoneer_olive \
    --batch-size 20 --concurrency 6 \
    --work-dir output/payoneer_olive_relabel_20260805

# 3) 确认后写回（复用同一 work-dir 的缓存，不会重新调模型）
... 同上 --execute

# 4) 回滚
/usr/bin/python3 data_control_tools/relabel_qa_quality_by_llm.py \
    --index payoneer_olive \
    --rollback output/payoneer_olive_relabel_20260805/rollback.jsonl --execute
```

`batch-size` 建议 20：40 时模型退化（条数对不上）明显更频繁。

## 验证

### 定点用例（18 条手工标注，`grep 符合预期` 的那次跑）

用户点名的 10 条坏样例全部 → `low`；8 条应保留的好知识 7 条 → `high`，
1 条（`chewy-可以用中国大陆的主体入驻吗？→可以`）因模型改写了答案触发 `text_mismatch`
被安全跳过（保持 high）。**17/18 符合预期，0 误伤。**

### 100 条抽样 dry-run

| | 首版规则 | 补规则后 |
|---|---|---|
| high→high | 64 | 61 |
| high→low | 28 | 35 |
| high→mid | 8 | 4 |
| skipped | 3 | 5 |

人工复核降级样例：**未发现把通用知识误降的情况**；
保留下来的 high 读起来基本都是平台规则/操作步骤/材料要求（Cdiscount 注册邮箱限制、
BestBuy 绑定派安盈流程、Chewy DSCO 仓库代码修改、chewy collect 取货模式等）。

### 单测

`/usr/bin/python3 -m pytest tests/test_relabel_qa_quality.py tests/test_chat_qa_extract.py -q`
→ 23 + 14 通过。覆盖：标签映射、LOW 优先、错位/少回条/无标签/空返回全部保持原档位、
协议分隔符检测、只写变化文档、dry-run 不写、查询按 `from_type` 而非 `from_type_norm`、
prompt 追加。

### 全量 dry-run（6312 条）

```
work-dir: output/payoneer_olive_relabel_20260805
batch-size 10, concurrency 8, retry-rounds 3, model google/gemini-2.5-flash

total 6312   aligned 6307   skipped 5
  skip: no_tag 3 / text_mismatch 1 / protocol_unsafe 1

high -> high  3199
high -> low   2341
high -> mid    772
changed       3113  (49.3%)
```

**重试轮是必需的**：只跑一轮时 730 条（11.6%）停在原档位没判出来
（其中 663 条是整块退化导致的 `no_tag`）。加了三轮缩小分块重试后降到 5 条。
分块退化在这个数据集上是常态而不是异常——632 块里有 30~50 块会退化，
`batch-size` 从 20 降到 10 并没有改善（不是长度问题，最长的块也没失败）。

人工复核最终样本：保留下来的 high 基本都是平台规则/资质/操作步骤
（Cdiscount 注册邮箱限制、ManoMano 会员制、chewy collect 取货模式、DSCO 对接 FedEx、
美客多审核时效、Bol 转人工排查步骤等）；降级的都是个案流水，未见通用知识被误降到 low。
少数带 `#不清晰` 的有用 QA 被降到 mid（如「chewy-采购是指从中国发货到CHEWY的仓库吗→美国仓库」），
属于偏保守，mid 同样不进默认检索，效果与 low 一致。

### 全量执行记录（2026-08-05 已写入生产）

```
--execute  work-dir: output/payoneer_olive_relabel_20260805
写回 3107 条，失败 0；只写 quality_level 一个字段
rollback: output/payoneer_olive_relabel_20260805/rollback.jsonl
```

执行时 `--execute` 复用了已有分块缓存，但 3 轮重试又把上一轮剩下的 5 条判出来了 2 条，
所以最终 `changed` 是 3107 而不是 dry-run 的 3113（`high->low` 2345 / `high->mid` 762）。

`from_type=chat_auto AND data_type=qa AND del_flag=0` 的 14050 条，执行前后分布：

| | 执行前 | 执行后 |
|---|---|---|
| high | 6312 | **3205** |
| mid | 4894 | 5656 |
| low | 2844 | 5189 |
| `audit_result=-1` | 11206 | 11206（未动） |
| `audit_result=0` | 2844 | 2844（未动） |

逐条核对：6312 条下载文档在 ES 里的当前 `quality_level` 与 `decisions.jsonl` **完全一致**，
3107 条变更全部落库，0 条错漏。

> 写完立刻做聚合会读到 refresh 前的旧值（实测第一次读到 high 3370），
> 对账要么稍等再查，要么按 `_id` 逐条核。脚本里 `after_distribution` 就踩了这个，
> 报告里那个数不可信，以事后复核为准。

### 第二轮：用户反馈后补规则重跑（2026-08-05）

用户在第一轮结果里挑出仍为 high 的：

```
Q: chewy-就是发了邮件不回复，也没有一个大概的时间给到我，我就有点懵了。
A: 因为这个不是你邮件过去的那位经理能一个人决定的，这个需要chewy内部多个部门的同步，所以她也无法回复你具体时间
```

漏杀的是两个没写进提示词的模式，顺带抽查 3205 条现存 high 又找出两个：

| 补的规则 | 标签 |
|---|---|
| 1.2 情绪表达 / 抱怨 / 担忧陈述（`我就有点懵了`、`我担心是不是…`、`库存不多，我去搬点货`） | `#不通用` |
| 5 答案针对**具体当事人**解释（`你邮件过去的那位经理`、`她`），区别于泛指卖家的「你/您」 | `#不通用` |
| 2.3 问答同句复述 | `#无实质答案` |
| 2.4 答案是反问 / 要求对方提供材料 | `#无实质答案` |

16 条回归用例 15 命中（唯一偏差落到 mid 而非 low，同样不进检索），10 条应保留的好知识 0 误伤。

第二轮只处理当时的 3205 条 high（已降级的不再回捞）：

```
work-dir: output/payoneer_olive_relabel_20260805_pass2
total 3205  aligned 3202  skipped 3
high->high 2717 / high->low 329 / high->mid 159
写回 488 条，失败 0，逐条核对不一致 0
```

**两轮累计**，`from_type=chat_auto AND data_type=qa` 的 14050 条：

| | 初始 | 第一轮后 | 第二轮后 |
|---|---|---|---|
| high | 6312 | 3205 | **2717**（-57%） |
| mid | 4894 | 5656 | 5815 |
| low | 2844 | 5189 | 5518 |

第二轮的降级质量不如第一轮——容易的垃圾第一轮已清完，第二轮动的是边界地带，
抽查约 10% 属于可惜的误伤（如 `DSCO 二次验证码失败找谁重置→联系dsco support`
被判 `#不通用`）。用户确认「宁可错杀」后全量写入。误伤可按
`output/payoneer_olive_relabel_20260805_pass2/rollback.jsonl` 单条捞回。

检索抽查（按生产默认过滤条件
`(quality_level=high AND audit_result∈[1,2,-1]) OR audit_result∈[1,2]`）：
「Chewy 入驻需要什么材料」「Trendyol 禁售类目」「Bol 包装 荷兰语」「Cdiscount 注册邮箱」
「manomano 收款账户 同名」五个 query 的 top3 全部是应保留的通用知识，个案流水不再出现。

## 回滚

`output/<work-dir>/rollback.jsonl` 记录每条被改文档的原 `quality_level`，
用 `--rollback <file> --execute` 原样写回。

## 附带发现：原始群聊上下文其实还在

每条自动学习 QA 的 `ext_info.from_chat_history` **完整保存了来源群的聊天窗口原文**
（14050 条全有，涉及 1218 个群，`ext_info.from_file_name.keyword` 是群名）。

所以「原始 chat history 已不在、无法重新生成」这个前提**不成立**——
后续可以另开一轮「用 `from_chat_history` 重新抽取 QA」的任务，从根上解决抽取质量，
而不只是给已经抽错的 QA 重新打标。

本次判定**故意不喂**这份上下文：重打标的标准就是「脱离上下文也成立」，
喂了上下文反而会让模型觉得这些个案 QA 说得通。

## 遗留

1. joint_login 的存量回补（`docs/chat_qa_extract_local_migration.md` 遗留第 1 条）还没做，
   现在可以直接用这个脚本：`--index joint_login --client joint_login`。
2. 部分答案正文里带 ` ``` ` / `"""` 残留符号，属于抽取阶段的脏数据，本次不处理。
3. `ext_info.quality_info` 保留的是**旧标签**，与新的 `quality_level` 不一致；
   新标签只在 `decisions.jsonl` 里。如果前端审核页会展示 quality_info，需要另外决策是否同步。
