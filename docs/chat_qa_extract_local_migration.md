# 聊天 QA 抽取/质检本地化与 joint_login 优化

日期：2026-08-01

## 背景

joint_login 接入挖掘后（见 `docs/joint_login_chat_mining_diagnosis.md`），产出质量不达标：

- 抽出来的 QA 大量是个案流水，例如
  `原编号:BR1090H-SL 公司名:深圳盛世达电子商务有限公司 … 收款:杭州公司公户 金额:21600元 销售:Allen`
- 答案是内部转派口吻（`告知他8月起 数据同步后…`）而不是直接回答
- 这类 QA 还被质检**判为 `#优质`** 进了 high

抽样量化：joint_login 当前 1108 条 high 里，随机 40 条有 26 条（65%）含明显个案标识。

## 改造内容

### 1. 新增 `chat_qa_extract` 模块，替代两个 Dify 流

| 原 Dify 流 | DSL | 本地实现 |
|---|---|---|
| 对话QA抽取-norm-nomixv1 | `data/对话QA抽取-norm-nomixv1.yml` | `chat_qa_extract/qa_extractor.py` |
| qa选择过滤 | `data/qa选择过滤.yml` | `chat_qa_extract/quality_filter.py` |

两个类都保留 `.request_dify(paragraph)` 接口，与 `commons.dify_tools.DifyWorkFlowRequest` 兼容，
所以调用点是就地替换。

LLM 客户端 `chat_qa_extract/llm_client.py` 移植自 `stone_fish/agents/commons/llm_client.py`
（多渠道路由 + 备选模型 + 输出退化检测），**去掉了硬编码凭证**，改为从
`config/llm_config.json` 注入（该文件已加入 `.gitignore`，模板见 `config/llm_config.json.example`）。

替换范围：
- 已替换：普通群 + 非 mix 分支（`gen_knowledge_from_chat._build_norm_nomix_provider`）、QA 质检（`qa_quality_tools.build_qa_filter`）
- **未替换**：转发群、mix 平台。这两条是另外的 Dify 应用，没有拿到 DSL，仍走 Dify
- 凭证缺失时两处都自动回落 Dify，保证线上不会因为没配置而中断

### 2. 修掉质检的条数错位（不只是 joint_login 的问题）

原 Dify 流把**整份** QA 清单编号后一次调用，而
`commons.qa_text_tools.parse_qa_quality_result` **忽略模型打印的序号**、按出现顺序重新编号。
模型少回一条，其后全部错位；`add_quality_info_to_qa_json_by_dify` 里
`if i + 1 in quality_info` 取不到就把 `quality_info` 置空 → 强制降级 mid。

实测各任务打标率（打上标签的 QA / 总 QA）：

| 任务 | QA 数 | 打标 | 比例 |
|---|---|---|---|
| 517c14ac | 427 | 424 | 99% |
| 9767b9a0 | 540 | 529 | 98% |
| 224b5f62 | 205 | 189 | 92% |
| 14457e6c | 397 | 123 | 31% |
| 05fd6af6 | 933 | 185 | 20% |
| 17b833db | 485 | 2 | 0.4% |

本地实现的改法：
- 按 `batch_size`（默认 40）分块，块内保留全局序号
- 每批产出条数必须等于投入条数，不等先重试
- 重试后仍不等 → 该批退化为「原文无标签」，把损失限制在本批而不是整个任务错位

原流用 `google/gemini-2.5-flash-lite`，本地默认换成 `google/gemini-2.5-flash`。

### 3. joint_login 专用规则

按 client 命中 `chat_qa_extract/prompts/{extract,quality}.<client>.md`，**内容追加**在原提示词之后。
没有对应文件的客户提示词保持原样，存量客户行为不变。

抽取侧（`extract.joint_login.md`）：
- 只抽政策规则 / 操作流程 / 判断标准 / 原因解释 / 方案建议
- 单店铺单客户的状态同步、金额确认、催办寒暄一律不抽
- 问题必须泛化：去掉店铺代号、公司名、人名、税号、金额、单号
- 答案改写成直接回答，去掉「告知他/回复客户说」这类内部转派口吻
- 整段没有可复用知识时输出 `all null`

质检侧（`quality.joint_login.md`）新增判定：
- `#不通用` — 只对某个具体店铺/客户/单据成立
- `#需要修改` — 内部转派口吻
- `#无实质答案` — 问答同句复述
- `#不清晰` — 用「这个店铺/这个主体」指代未说明的主体
- `#优质` 收紧为「换个店铺换个客户依然成立」

`#不通用` 已加进 `qa_quality_tools.LOW_QUALITY_TAG`，直接降 low 而不是留在 mid。

## 验证

### A/B（同模型同分块，只比提示词），joint_login 现有 high 抽样 40 条

| | 默认规则 | joint_login 增强 |
|---|---|---|
| 判为 high | 34 (85%) | 4 (10%) |

被拦下的 30 条包括 `BR0332A的通道费是多少？→249.21巴币`、
`杭州乾跃进出口有限公司 理由是什么？→首款（60000/100000）`、
`第二季度报税费用已支付→第二季度报税费用已支付`，这些原来**全部**被判 `#优质`。

### 端到端本地跑（joint_login 同 12 个群，对照生产任务 9767b9a0）

| | 生产（旧） | 本地（新） |
|---|---|---|
| 抽取 QA | 97 | 38 |
| high | 63 | 29 |
| **high 中含个案标识** | **38 条 (60%)** | **0 条 (0%)** |
| 质检打标率 | 见上表，20~99% 波动 | 38/38 (100%) |

新流程 high 样例：Anvisa 认证风险等级要求、公户开户费用与月费、美客多申诉网址、
子账号开通步骤、运费政策（R$79 强制包邮等）、FULL 仓覆盖范围、起飞计划准入条件。

## 如何使用

```bash
cp config/llm_config.json.example config/llm_config.json   # 填入真实凭证
```

本地跑（需要 PYTHONPATH 指到仓库根）：

```bash
PYTHONPATH=/path/to/knowledge_database_builder python3 chatknowledge/gen_knowledge_from_chat.py \
    run_batch_robot_chat_data --data_file=... --output_dir=... --data_file_field_num=3 \
    --robot_room_type_config_file=... --robot_process_record_file=... \
    --robot_white_list_file=... --filter_group_name=all --prompt_file_map=... --flag=...

PYTHONPATH=/path/to/knowledge_database_builder python3 quality_tools/qa_quality_tools.py \
    run_batch_add_dify_quality_and_resplit --input_file=... --output_file=... \
    --process_field_num=4 --dify_qa_filter_name=chatknowledge_qa_filter_for_chathistory \
    --client=joint_login --flag=...
```

给新客户加定制规则：在 `chat_qa_extract/prompts/` 下建
`extract.<client>.md` / `quality.<client>.md` 即可，无需改代码。

## 遗留

1. **joint_login 存量数据没有回补**。ES 里现有约 2489 条是旧流程产出，其中 high 约六成是个案流水。
   要清理需要单独决策：按 `update_time` 定位旧批次 → 软删或重跑覆写。
2. 转发群、mix 平台仍走 Dify，缺 DSL。
3. 分块后跨批的 `#重复-{index}` 检测失效；上游 `deduplicate_qa_list` 和下游 `re_group_qa_list`
   仍在做字符级去重，可接受。
4. `payoneer_chat_mining/llm_client.py` 是另一份单渠道 OpenRouter 封装且密钥硬编码（未入库）。
   后续可迁到 `chat_qa_extract.llm_client` 统一管理。
