# Payoneer 公众号文章知识抽取与通用挖掘流程优化方案

## 目标

先完成 Payoneer 公众号文章里的业务/任务知识抽取，再把有效策略固化到通用 `document_qa_segment_mining` 流程里。

原始文章目录：

`/Users/chenqishi/Downloads/wcplusPro_macos_apple_silicon/article/Payoneer派安盈/`

本次首要任务只处理 `.md` 文件，`.html` 不作为正文来源。`.html` 只在必要时用来补充文章标题、发布时间、公众号原文链接等元信息。首批只处理“半年内”的文章，发布时间优先从文章元信息读取；如果只能退化到文件时间，必须在产物元数据里标记 fallback。

## 现有流程简述

现有后台任务是 `document_qa_segment_mining`。

关键入口：

- `control_service/off_task_control_service.py`
- `control_service/document_qa_segment_mining.py`
- QA 生成：`knowledge_clear_tool/knowledge_clear_by_dify_model_longcontent.py`
- QA 质量处理：`quality_tools/qa_quality_tools.py`
- Segment 生成：`knowledge_generate/knowlege_segment_builder_by_dify.py`
- Schema 转换：`commons/schema_trans.py`

当前阶段：

1. 文件下载
2. 文档解析
3. 多模态处理
4. 可选翻译
5. QA 生成
6. QA 质量处理
7. QA Schema 转换
8. QA 入索引
9. Segment 生成
10. Segment Schema 转换
11. Segment 入索引

主要问题：当前 Dify/LLM 节点大多只拿到 `paragraph`，缺少稳定的客户业务背景、目标用户问题、反例、客户知识边界。因此通用化挖掘容易把公众号 footer、版权声明、隐私说明、关注引导、品牌广告、泛泛案例故事抽成知识。

## LLM 调用策略

后续优化不应强绑定 Dify。Dify 节点可以被本地/统一 LLM 调用层替代。

优先复用 `agents` 项目里的 LLM 客户端：

- 代码：`/Users/chenqishi/stone_fish/agents/commons/llm_client.py`
- Claude 可读说明：`/Users/chenqishi/stone_fish/agents/function_schema/llm_client.request_llm.md`

核心接口：

```python
from commons.llm_client import configure_providers, request_llm

configure_providers(llm_config)

content, reasoning, detail_info = request_llm(
    model_name="openai/gpt-4.1-mini",
    query=user_prompt,
    system_message=system_prompt,
    image_urls=None,
    temperature=0.1,
    max_tokens=8000,
    provider=None,
    fallback_model=None,
    fallback_provider=None,
)
```

`request_llm` 的好处：

- 支持 OpenRouter、OpenAI、Qwen、Gemini、Volcengine 等多渠道；
- 按 `model_name` 自动路由；
- 支持主模型失败后的 fallback；
- 支持图片 URL 输入；
- 能返回 usage 信息，方便后续成本统计；
- 已经有 function schema，Claude 容易理解和执行。

建议在本项目新增一个轻量适配层，例如：

`commons/local_llm_adapter.py`

它对知识挖掘侧暴露统一函数：

```python
def request_knowledge_llm(
    query: str,
    system_message: str,
    *,
    model_name: str = None,
    provider: str = None,
    image_urls: list[str] | None = None,
    temperature: float = 0.1,
    max_tokens: int = 8000,
    usage_out: dict | None = None,
) -> str:
    ...
```

内部优先调用 `agents.commons.llm_client.request_llm`。Dify 只作为兼容旧流程或紧急回退，不作为新 Payoneer 挖掘链路的默认方案。

实现方式有两种：

1. **直接跨项目 import**：把 `/Users/chenqishi/stone_fish/agents` 加入 `sys.path`，调用 `commons.llm_client`。适合本地一次性任务。
2. **复制/抽公共包**：长期方案把 `llm_client.py` 抽成共享模块或 vendor 到本项目，避免生产部署时依赖另一个 repo 的绝对路径。

首批 Payoneer 任务建议用第 1 种，快速落地；通用流程上线前再做共享模块治理。

## Payoneer 知识抽取边界

保留能帮助跨境卖家、平台商户、内容创作者、B2B 商户、Payoneer 用户解决实际问题的知识。

应该保留：

- Payoneer 绑定平台账号的方法；
- 注册、认证、授权、提现、收款、对账、账户管理；
- Shopee、Amazon、Walmart、TikTok Shop、Joom、noon、eBay、Lazada 等平台的收款流程；
- 费率、结算周期、支持币种、账户要求、KYC/KYB 材料、合规限制；
- 具体平台规则、操作步骤、资格条件、报错处理；
- 活动/课程知识只有在具备明确业务价值时保留，例如时间、地点、报名方式、议程、适合人群。

应该丢弃：

- “Payoneer 很好”“助力全球增长”这类空泛品牌宣传；
- 版权、隐私、cookie、免责声明、footer、sidebar；
- 关注公众号、扫码关注、点赞、在看、阅读原文等无业务价值引导；
- 纯新闻稿或 PR 里程碑，除非它改变了用户可执行流程；
- 长篇案例故事，除非能提炼出可复用的运营方法、平台规则或收款步骤；
- 只宣传活动但没有时间、对象、报名方式、议程等事实的广告。

目标 QA 示例：

```text
Q: 3PF 怎么绑定 Payoneer？
A: Step 1：登录 Shopee 卖家中心。Step 2：点击左侧导航栏“财务 -> 收款账户”，选择越南 3PF 店铺。Step 3：找到 Payoneer 派安盈图标，登录或注册并完成授权绑定。
```

## 首批 Payoneer 交付流程

先做一个独立、可审核的 Payoneer 挖掘流程，不急着改线上通用任务。

建议目录：

`payoneer_article_mining/`

### 1. Markdown 文章预处理

职责：

- 遍历源目录下 `.md` 文件；
- 读取标题、发布时间、公众号原文链接；
- 过滤到半年内文章；
- 清理 Markdown 明显噪声；
- 切分出业务相关块；
- 输出标准中间 JSONL。

中间结构建议：

```json
{
  "client": "payoneer",
  "source_file": ".../1643e05a305ec60944e68cb8aebfd6bb.md",
  "from_file_name": "Shopee卖家中心主操作界面基本功能介绍",
  "publish_time": "2026-xx-xx",
  "publish_time_source": "html_meta",
  "article_url": "https://mp.weixin.qq.com/...",
  "title": "Shopee卖家中心主操作界面基本功能介绍",
  "clean_blocks": [
    {
      "block_id": "1643...#003",
      "heading": "我的钱包",
      "content": "点击主页面④，进入【我的钱包】...卖家可以绑定 Payoneer 账户至 Shopee 平台并收款。",
      "image_urls": []
    }
  ]
}
```

### 2. 业务上下文包

生成或手写 Payoneer 的业务上下文文件：

`payoneer_article_mining/context/payoneer_business_context.md`

内容包括：

- client：Payoneer / 派安盈；
- 目标用户：跨境卖家、平台商户、内容创作者、B2B 商户；
- 重点平台：Shopee、Amazon、Walmart、TikTok Shop、Joom、noon、eBay、Lazada；
- 应抽知识：平台绑定、收款、提现、KYC/KYB、费用、结算、合规、平台运营；
- 不抽知识：品牌宣传、PR、广告、版权、隐私、关注公众号、无事实活动推广。

这个上下文不应每次任务都重新生成。按 client 缓存，只有这些情况刷新：

- 前端/任务显式传入新的 `business_context_text`；
- 缓存超过 TTL，例如 30 天；
- client 或 `knowledge_objective` 发生明显变化。

### 3. QA 生成 Prompt

使用本地 LLM 调用层生成 QA，要求模型只输出 JSON 数组。

系统提示词应强调：

- 只抽业务/任务知识；
- 一个问题对应一个原子答案；
- 优先保留步骤、条件、费用、时间、链接、平台名；
- 禁止抽版权、隐私、关注引导、营销口号；
- 禁止无依据扩写；
- 广告类内容只有在能提取明确业务规则/操作步骤时才保留。

输出结构：

```json
[
  {
    "q": "...",
    "a": "...",
    "indexes": ["Shopee", "Payoneer绑定", "收款账户"],
    "category": "平台收款",
    "evidence": "...原文依据...",
    "quality_reason": "包含可执行的平台绑定步骤"
  }
]
```

最终入库仍保持现有 QA 类型。`evidence`、`quality_reason` 可以只留在审核中间产物，或者写入备注/extra 字段。

### 4. Segment 生成

Segment 用于兜底召回，但不能直接塞整篇文章。

Segment 只基于清洗后的业务块生成，要求：

- 一段只表达一个相对完整业务主题；
- 保留平台、场景、操作上下文；
- 可包含必要图片链接；
- 不包含 footer、相关文章推荐、关注公众号、版权隐私、空泛广告。

### 5. 后置过滤

加一层确定性过滤 + LLM 标签过滤。

确定性过滤：

- 命中这些 boilerplate 时拒绝：`欢迎点击上方`、`关注我们`、`免责声明`、`隐私政策`、`Copyright`、`阅读原文`、`扫码关注`、`点赞`、`在看`；
- 答案过短且不含具体值/URL/步骤时拒绝；
- QA 不含 Payoneer、平台名、收款/提现/绑定/认证/费用/结算等任务关键词时降权或拒绝；
- 问题像“Payoneer 为什么好”且答案只有宣传时拒绝。

LLM 标签：

- `task_knowledge`：保留；
- `policy_or_condition`：保留；
- `event_fact`：有明确事实才保留；
- `case_insight`：能提炼操作建议才保留；
- `marketing`：拒绝；
- `boilerplate`：拒绝；
- `unrelated`：拒绝。

## 通用流程优化方案

### 当前落地状态

截至 2026-06-18，本次已经执行并验证的是 **Payoneer 一次性公众号文章挖掘链路**，不是线上通用 `document_qa_segment_mining` 的完整改造。

已落地到代码/产物：

- `payoneer_article_mining/run_payoneer_article_mining.py`：Payoneer `.md` 文章抽取、业务关键词过滤、QA/Segment 生成。
- `payoneer_article_mining/repair_self_contained_rows.py`：Payoneer 结果后处理，修复悬空指代和栏目式泛标题。
- `payoneer_article_mining/context/payoneer_business_context.md`：Payoneer 手写业务上下文。
- `data/payoneer_article_mining/run_20260618/payoneer_article_knowledge_audit_20260618.xlsx`：人工审核版结果，未入库。

尚未落地到线上通用流程：

- 从 `data_chat_history` 自动提炼客户真实 query/高频意图。
- 网络检索客户业务背景并生成可缓存的业务上下文。
- 前端传入 `business_context_text` 并随 task 进入任务系统。
- 通用 `business_context` 缓存表/文件。
- `document_qa_segment_mining` 读取上下文并替换/增强 Dify QA 与 Segment 生成。
- 通用质量后处理器接入线上任务。

因此，Payoneer 脚本里的规则只能说明“策略已在一个客户样本上验证有效”，不能等同于通用挖掘流程已经完成改造。

给 `document_qa_segment_mining` 增加可选字段：

```json
{
  "client": "payoneer",
  "business_context_text": "用户在前端输入的业务背景，可选",
  "business_context_id": "缓存上下文 ID，可选",
  "knowledge_objective": "平台收款、账户绑定、提现、KYC、费用、合规、平台运营",
  "source_type": "wechat_article_md",
  "time_window": {
    "start": "2025-12-18",
    "end": "2026-06-18"
  },
  "quality_profile": "business_task_knowledge",
  "enable_context_enrichment": true,
  "llm_model_name": "openai/gpt-4.1-mini",
  "llm_provider": "openrouter"
}
```

兼容规则：这些字段不存在时，旧流程保持不变。

### 上下文增强来源

按优先级使用：

1. 前端传入的 `business_context_text`：最高优先级，成本最低；
2. `data_chat_history` 里同 client 的真实用户问题：提炼用户高频意图；
3. 已有高质量知识：提炼客户知识边界；
4. 网络检索：默认关闭，只有显式开启且缓存命中策略允许时使用。

### 上下文增强落地设计

新增一个通用模块，例如：

`knowledge_clear_tool/business_context_builder.py`

职责：

1. 接收 `client`、`knowledge_objective`、`business_context_text`、`enable_context_enrichment`、`enable_web_context`、`task_id`。
2. 优先使用前端传入的 `business_context_text`。
3. 如果没有前端上下文或上下文太短，从 `data_chat_history` 抽取该 client 的真实用户问题，形成“用户常问什么/真实任务意图是什么”。
4. 可选读取该 client 已有高质量知识，形成“已有知识边界/回答口径”。
5. 网络检索默认关闭；只有 `enable_web_context=true` 且缓存过期时才执行。
6. 将最终上下文写入缓存，后续同 client、同 objective、同来源类型优先复用。

建议输出结构：

```json
{
  "client": "payoneer",
  "knowledge_objective": "平台收款、账户绑定、提现、KYC、费用、合规、平台运营",
  "context_text": "...最终给 LLM 的业务背景...",
  "query_intents": [
    {"intent": "Shopee 店铺绑定 Payoneer", "sample_queries": ["3pf 怎么绑定payoneer", "..."]},
    {"intent": "提现/换汇/费用", "sample_queries": ["..."]}
  ],
  "business_boundaries": {
    "keep": ["操作步骤", "条件限制", "费用费率", "活动时间地点报名方式"],
    "reject": ["品牌宣传", "版权隐私", "关注公众号", "无事实广告"]
  },
  "sources": {
    "frontend_context": true,
    "chat_history": true,
    "existing_knowledge": false,
    "web_search": false
  },
  "generated_at": "2026-06-18 00:00:00",
  "ttl_days": 30
}
```

#### `data_chat_history` 的使用方式

目标不是把聊天内容直接变成知识，而是用真实 query 校准抽取方向。

建议步骤：

1. 按 client/admin_user_id/app_id 查询近 90~180 天用户问题。
2. 只取用户侧问题，过滤客服寒暄、无意义短句、图片消息、重复消息。
3. 用本地 LLM 聚类成 10~30 个高频意图。
4. 产出“应抽知识类型”和“反例”：
   - 应抽：用户真实会问的流程、条件、费用、失败原因、材料要求、时间地点。
   - 不抽：客户不会拿来问答的品牌稿、新闻稿、活动口号。
5. 将这些意图放入 QA/Segment 生成 prompt，让模型优先抽能回答真实 query 的知识。

#### 网络检索的使用方式

网络检索只用于补充客户业务画像，不用于替代原文事实。

原则：

- 默认关闭，避免每个任务都搜索造成成本和不稳定。
- 按 `client + knowledge_objective + source_type` 缓存，TTL 建议 30 天。
- 只检索客户官网、官方帮助中心、官方产品页、可信公开资料。
- 网络内容只能形成“业务背景/术语表/产品边界”，不能直接作为当前文档知识答案，除非来源可追溯且任务明确允许。
- prompt 中明确：答案事实必须来自当前文档/文章；网络背景只帮助判断什么值得抽。

#### 前端输入业务背景

前端新增可选输入：

字段名：`business_context_text`

展示名：`业务背景/知识目标`

说明文案：

```text
请描述本次知识抽取的客户业务、目标用户、希望保留的知识类型和不希望抽取的内容。
例如：客户是跨境支付平台，目标用户是跨境卖家。重点抽取平台收款、账户绑定、提现、费用、KYC、合规、活动时间地点报名方式。不要抽品牌宣传、版权声明、关注公众号等。
```

任务系统将该字段原样传给 `document_qa_segment_mining`，并参与上下文缓存 hash。

建议缓存结构：

```json
{
  "client": "payoneer",
  "context_hash": "...",
  "generated_at": "...",
  "ttl_days": 30,
  "context_text": "...",
  "source_summary": {
    "chat_history_window": "...",
    "web_enabled": false
  }
}
```

### 插入点

推荐插入点：

1. `document_parse` 之后、QA 生成之前：
   - source-specific cleaner；
   - 构建业务上下文包；
   - 输出过滤后的业务块。
2. QA 生成：
   - 输入从 `paragraph` 扩展为 `paragraph + business_context + extraction_rules`；
   - 优先走本地 LLM 适配层。
3. QA 质量：
   - 增加业务相关性标签；
   - 写清楚拒绝原因。
4. Segment 生成：
   - 用清洗后的业务块，不用完整原文。

### 替换 Dify 的方式

现有 Dify 请求：

```json
{
  "inputs": {
    "paragraph": "..."
  }
}
```

新流程推荐改为本地 LLM prompt：

```python
system_prompt = business_context + extraction_rules
user_prompt = article_block

content, _, detail = request_llm(
    model_name=task_info.get("llm_model_name") or "openai/gpt-4.1-mini",
    provider=task_info.get("llm_provider"),
    query=user_prompt,
    system_message=system_prompt,
    temperature=0.1,
    max_tokens=8000,
)
```

若为了平滑迁移仍保留 Dify，可做成策略参数：

```json
{
  "llm_backend": "local_llm"
}
```

可选值：

- `local_llm`：默认，新流程使用；
- `dify`：旧流程兼容；
- `auto`：优先 local，失败后 Dify 回退。

## 实施阶段

### 阶段 A：Payoneer 一次性交付

1. 新建 `payoneer_article_mining/`。
2. 读取 `.md`，恢复元信息，过滤半年内文章。
3. 清洗成业务块。
4. 通过 `agents.commons.llm_client.request_llm` 生成 QA。
5. 生成 segment。
6. 输出审核 Excel / JSONL。
7. 抽样审核后再入 ES。

### 阶段 B：通用流程固化

1. 给任务增加可选上下文字段和 LLM backend 字段。
2. 增加 context cache。
3. 增加 source cleaner registry，首个 source_type 为 `wechat_article_md`。
4. 改造 QA 生成，支持 `business_context`。
5. 改造 QA 质量过滤，增加业务相关性标签。
6. 改造 segment 生成，使用清洗块。
7. 增加任务统计：
   - 原始文件数；
   - 半年内文件数；
   - 清洗块数；
   - 生成 QA 数；
   - 保留/拒绝 QA 数及原因；
   - segment 数；
   - LLM 调用次数与 token 成本。

### 阶段 C：前端支持

前端增加文本框：

字段名：`business_context_text`

展示名：`业务背景/知识目标`

占位文本：

```text
例如：Payoneer 的目标用户是跨境卖家，重点抽取平台收款、账户绑定、提现、费用、KYC、合规和平台运营步骤。不要抽取品牌宣传、版权声明、关注公众号等内容。
```

该字段随 task 一起传到任务系统。

## 给 Claude 的执行说明

Claude 后续执行时：

1. 先读本文件。
2. 再读 `CLAUDE.md`。
3. 通用流程改造必须读 `docs/claude_task_generic_mining_context_enrichment.md`，不要把 Payoneer 一次性脚本当成通用流程已完成。
4. 如果需要调用 LLM，优先参考 `/Users/chenqishi/stone_fish/agents/function_schema/llm_client.request_llm.md`。
5. Payoneer 首批任务优先使用 `/Users/chenqishi/stone_fish/agents/commons/llm_client.py`，不要继续默认使用 Dify。
6. 执行前确认 Claude Code 当前模型。优先使用 `claude-opus-4-8`，并在交付说明中记录实际模型名；如果当前模型不是 4.8，先切换或明确说明原因。Claude Code 中通常可通过 `/model` 查看/切换模型；如使用模型配置覆盖，使用 Anthropic 官方模型 ID `claude-opus-4-8`。
7. 改 Python 函数前，先读对应 `function_schema/<file_prefix>.*.md`。
8. 函数新增或修改后，必须新增/更新对应 function schema。
9. 不传新增 task 字段时，旧 `document_qa_segment_mining` 行为不能变化。
10. Payoneer 一次性脚本放在 `payoneer_article_mining/` 或同等清晰的目录下。
11. 首批只处理 `.md` 正文，不把 `.html` 当正文。
12. 文件修改时间不能默认当文章发布时间；除非没有更可靠元数据，并在结果里标记 fallback。
13. 第一验收目标是可审核 QA/segment 文件，不是直接入库。
