# Claude 执行任务：通用 document_qa_segment_mining 上下文增强改造

## 背景

Payoneer 公众号文章任务已经验证了一批质量策略，但这些策略目前主要在 `payoneer_article_mining/` 一次性脚本里，尚未进入线上通用 `document_qa_segment_mining` 流程。

本任务要求 Claude Code 接手实现通用流程改造，而不是继续只修 Payoneer 产物。

执行前请先确认 Claude Code 当前模型，优先使用并记录 `claude-opus-4-8`；如果不是 4.8，需要说明原因。

## 总目标

让通用 `document_qa_segment_mining` 在不破坏旧任务的前提下，支持客户业务上下文增强：

1. 前端/任务可传入业务背景文本。
2. 可从 `data_chat_history` 提炼该客户真实用户 query/高频意图。
3. 可选从网络检索客户业务背景，并缓存，避免每次任务都搜索。
4. QA 和 Segment 生成时使用 `business_context + query_intents + extraction_rules`。
5. 增加通用质量后处理，解决悬空指代和栏目式泛标题问题。
6. 默认不改变旧任务行为；新增能力必须由 task 字段开关启用。

## 非目标

- 不要求本次直接把所有旧 Dify 节点移除。
- 不要求默认开启网络搜索。
- 不要求自动入库 Payoneer 本次审核产物。
- 不允许把网络检索内容直接当作文档事实写入知识答案；网络只用于业务背景和抽取方向。

## 当前关键文件

通用任务入口：

- `control_service/document_qa_segment_mining.py`

当前 QA 生成：

- `knowledge_clear_tool/knowledge_clear_by_dify_model_longcontent.py`

当前 Segment 生成：

- `knowledge_generate/knowlege_segment_builder_by_dify.py`

当前 QA 质量：

- `quality_tools/qa_quality_tools.py`

当前 Schema 转换：

- `commons/schema_trans.py`

Payoneer 验证脚本，可参考但不要直接耦合：

- `payoneer_article_mining/run_payoneer_article_mining.py`
- `payoneer_article_mining/repair_self_contained_rows.py`
- `payoneer_article_mining/context/payoneer_business_context.md`

通用方案文档：

- `docs/payoneer_article_knowledge_mining_plan.md`

## 新增 task 字段

`document_qa_segment_mining` 的 `task_info` 增加以下可选字段：

```json
{
  "business_context_text": "用户/前端输入的业务背景，可选",
  "knowledge_objective": "本次希望抽取的知识目标，可选",
  "quality_profile": "business_task_knowledge",
  "enable_context_enrichment": false,
  "enable_chat_query_context": false,
  "enable_web_context": false,
  "context_cache_ttl_days": 30,
  "llm_backend": "dify",
  "llm_model_name": "openai/gpt-4.1-mini",
  "llm_provider": "openrouter",
  "review_only": false
}
```

兼容要求：

- 字段不存在时，行为与现在一致。
- `enable_context_enrichment=false` 时，不构建业务上下文，不改 prompt。
- `enable_web_context=false` 时，绝不发起网络检索。
- `review_only=true` 时，生成审核文件或中间文件，但跳过 ES 插入阶段。

## 建议新增模块

### 1. `knowledge_clear_tool/business_context_builder.py`

职责：

- 构建并缓存业务上下文。
- 合并前端输入、chat history 意图、已有知识边界、可选网络背景。

建议函数：

```python
def build_business_context(
    *,
    client: str,
    knowledge_objective: str | None,
    business_context_text: str | None,
    enable_context_enrichment: bool,
    enable_chat_query_context: bool,
    enable_web_context: bool,
    cache_dir: str,
    ttl_days: int = 30,
    task_info: dict | None = None,
) -> dict:
    ...
```

返回结构：

```json
{
  "client": "payoneer",
  "context_text": "...给 LLM 的最终业务背景...",
  "query_intents": [
    {"intent": "Shopee 店铺绑定 Payoneer", "sample_queries": ["3pf 怎么绑定payoneer"]}
  ],
  "business_boundaries": {
    "keep": ["步骤", "条件", "费用", "时间地点报名方式"],
    "reject": ["品牌宣传", "版权隐私", "关注公众号"]
  },
  "sources": {
    "frontend_context": true,
    "chat_history": true,
    "existing_knowledge": false,
    "web_search": false
  },
  "cache_hit": false,
  "cache_path": "..."
}
```

### 2. `knowledge_clear_tool/chat_query_context.py`

职责：

- 从 `data_chat_history` 抽取同 client 的用户 query，并聚类为高频意图。
- 只用于“抽取方向”，不能直接生成知识。

建议函数：

```python
def load_client_queries(
    *,
    client: str,
    admin_user_id: str | None = None,
    app_id: str | None = None,
    days: int = 180,
    limit: int = 1000,
) -> list[str]:
    ...

def summarize_query_intents(
    queries: list[str],
    *,
    client: str,
    model_name: str | None = None,
    provider: str | None = None,
) -> list[dict]:
    ...
```

SQL 注意：

- 项目已有 `commons/sql_tools.py` 和 `config/mysql_conn_config.json`。
- 需要先确认本地实际 `data_chat_history` 字段名，再写 SQL。
- 只取用户侧 query，过滤空文本、图片链接、纯表情、过短寒暄、重复 query。
- 如果字段无法确认或数据库不可用，函数应降级返回空列表，不中断主任务。

### 3. `knowledge_clear_tool/web_business_context.py`

职责：

- 可选网络检索客户业务背景。
- 默认关闭，只有 `enable_web_context=true` 时使用。
- 结果必须缓存。

建议函数：

```python
def build_web_business_context(
    *,
    client: str,
    knowledge_objective: str | None,
    cache_dir: str,
    ttl_days: int = 30,
) -> dict:
    ...
```

规则：

- 只生成客户业务画像、术语、产品边界、目标用户。
- 不得把网络事实直接写入 QA/Segment 答案。
- 如果当前运行环境没有可用搜索工具或网络失败，应返回空上下文并记录 warning。
- 需要有缓存文件，例如 `data/business_context_cache/{client_hash}.json`。

### 4. `knowledge_clear_tool/generic_knowledge_quality.py`

职责：

- 通用后处理 QA/Segment，避免 Payoneer 那种问题再次出现。

建议能力：

- 修复悬空指代：`第一期`、`本次`、`此次`、`该活动`、`该服务`、`该合作`。
- 修复栏目式泛标题：`活动概述与目标`、`适合对象`、`推广内容`、`服务内容`、`详情`、`核心优势`。
- 检查活动类知识：有原文时间则标题或内容必须带时间；线下有地点则必须带地点。
- 拒绝 boilerplate：版权、隐私、关注公众号、点赞、阅读原文、免责声明。
- 输出 repair/reject report，不能静默修改。

注意：

- 这个模块必须是通用的，不能硬编码 Payoneer。
- 允许使用 `from_file_name` 作为兜底主体，但优先用 LLM/规则提取更短的业务主体。

建议函数：

```python
def repair_self_contained_knowledge_rows(
    rows: list[dict],
    *,
    business_context: dict | None = None,
    source_title_field: str = "from_file_name",
) -> tuple[list[dict], dict]:
    ...

def filter_business_quality_rows(
    rows: list[dict],
    *,
    quality_profile: str = "business_task_knowledge",
) -> tuple[list[dict], list[dict]]:
    ...
```

## 通用流程接入点

### `control_service/document_qa_segment_mining.py`

建议改造：

1. `__init__` 读取新增 task 字段。
2. 新增路径：
   - `self.business_context_path`
   - `self.quality_report_path`
   - `self.review_excel_path` 或 `self.review_output_path`
3. 在 `stage_5_generate_qa` 前新增 stage：
   - `stage_4_5_build_business_context`
   - 只在 `enable_context_enrichment=true` 时执行。
4. `stage_5_generate_qa` 调用 QA 生成脚本时传入 `--business_context_path` 或 `--business_context_text_file`。
5. `stage_6_qa_quality` 后追加通用质量后处理。
6. `stage_9_generate_segment` 调用 Segment 生成脚本时也传入业务上下文。
7. `review_only=true` 时跳过 `stage_8_insert_index` 和 `stage_11_insert_segment_index`。

### QA 生成脚本

`knowledge_clear_tool/knowledge_clear_by_dify_model_longcontent.py`

建议兼容改造：

- 新增 CLI 参数：
  - `--business_context_path`
  - `--quality_profile`
  - `--llm_backend`
  - `--llm_model_name`
  - `--llm_provider`
- `llm_backend=dify` 时保持旧行为。
- `llm_backend=local_llm` 时调用 `agents/commons/llm_client.py` 或新增适配层。
- prompt 必须包含：
  - 业务背景；
  - 用户高频 query/intents；
  - 保留/拒绝边界；
  - 自包含标题规则；
  - 活动时间地点规则；
  - 答案事实必须来自当前文档。

### Segment 生成脚本

`knowledge_generate/knowlege_segment_builder_by_dify.py`

建议兼容改造：

- 与 QA 生成类似新增上下文参数。
- Segment 不允许直接整篇灌入。
- Segment 标题必须自包含，不能是栏目式标题。

## LLM 调用要求

用户明确要求：可以用 Dify 的地方，后续都可以直接用本地 LLM 替代；LLM 调用方法在 `agents` 项目中。

优先参考：

- `/Users/chenqishi/stone_fish/agents/commons/llm_client.py`
- `/Users/chenqishi/stone_fish/agents/function_schema/llm_client.request_llm.md`

如果需要在本 repo 封装，建议新增：

`commons/local_llm_adapter.py`

并提供：

```python
def request_knowledge_llm(...):
    ...
```

不要让通用流程强依赖 Payoneer 目录或 Payoneer prompt。

## 验收标准

### 单元/离线验收

1. 老任务兼容：
   - 不传新增字段时，`document_qa_segment_mining` 命令构造与旧流程等价。
2. 上下文构建：
   - 传 `business_context_text` 时，生成 cache/context 文件。
   - `enable_chat_query_context=false` 时不查 `data_chat_history`。
   - `enable_web_context=false` 时不发起网络搜索。
3. 质量后处理：
   - 输入标题 `活动概述与目标` + `from_file_name=北美采购订单渠道对接会`，输出标题必须带主体。
   - 输入 `第一期直播主要讨论什么`，输出必须补活动名/时间，或标记 reject/needs_review。
   - 输入版权/关注公众号/阅读原文类内容，必须进入 rejected。
4. review_only：
   - `review_only=true` 时不执行 ES 插入。

### 集成验收

用一个小样本文档跑 `document_qa_segment_mining`：

```json
{
  "task_type": "document_qa_segment_mining",
  "client": "payoneer",
  "index_name": "test_index",
  "business_context_text": "客户是跨境支付平台，目标用户是跨境卖家。重点抽取平台收款、账户绑定、提现、费用、KYC、合规、活动时间地点报名方式。不要抽品牌宣传、版权声明、关注公众号等。",
  "knowledge_objective": "平台收款、账户绑定、提现、费用、合规、活动信息",
  "enable_context_enrichment": true,
  "enable_chat_query_context": false,
  "enable_web_context": false,
  "llm_backend": "local_llm",
  "review_only": true
}
```

预期：

- 生成 QA 和 Segment 中间结果。
- 生成 context 文件和 quality report。
- 不插入 ES。
- 输出中不存在裸标题：`适合对象`、`推广内容`、`活动概述与目标`。
- 输出中不存在悬空问题：`第一期直播主要讨论什么`、`本次活动如何报名`。

## 必须同步的文档和 schema

本 repo 要求每个新增/修改函数都写 `function_schema/<file_prefix>.<function_name>.md`。

Claude 执行时必须：

1. 先读同模块已有 `function_schema`。
2. 新增/修改函数后补 schema。
3. SQL 相关函数必须在 schema 的 SQL section 写清表、字段、过滤条件和降级策略。

至少需要新增的 schema：

- `business_context_builder.build_business_context.md`
- `chat_query_context.load_client_queries.md`
- `chat_query_context.summarize_query_intents.md`
- `web_business_context.build_web_business_context.md`
- `generic_knowledge_quality.repair_self_contained_knowledge_rows.md`
- `generic_knowledge_quality.filter_business_quality_rows.md`

## 交付说明

Claude 完成后需要在最终回复里说明：

- 实际改了哪些通用文件。
- 哪些 task 字段已支持。
- 是否查了 `data_chat_history`，如果没查到或数据库不可用，如何降级。
- 网络背景是否默认关闭。
- 如何开启 review_only。
- 跑了哪些测试/命令。
