# kdb.mining.chat.generation.extractor.ChatQAExtractor

## Signature

`ChatQAExtractor(self, system_prompt: Optional[str]=None, client: Optional[str]=None, model: Optional[str]=None, max_retries: int=2, max_tokens: int=16000, temperature: float=0.2, timeout: int=180, usage_out: Optional[dict]=None)`

## Description

Dify workflow「对话QA抽取-norm-nomixv1」（`data/对话QA抽取-norm-nomixv1.yml`）的本地实现。
把一个群的聊天记录送给 LLM，抽出问答对文本。

## 对应关系（本地实现 ↔ 原 Dify 流）

| Dify 节点 | 本地实现 |
|---|---|
| start(paragraph, system_prompt) | `request_dify(paragraph)` + 构造函数的 `system_prompt` |
| if-else：system_prompt 是否为空 | 构造函数：为空用 `prompts/extract.default.md` |
| 默认LLM / 外部入参LLM（anthropic/claude-sonnet-4） | `llm_client.request_llm`，模型取 `config.get_model('extract')` |
| code：清除 `<think></think>` | `qa_extractor.clear_think` |
| end：Final | `request_dify` 的返回值 |

user 消息与原流一致：`以下是对话记录，请进行处理:\n{paragraph}`

## Inputs

构造函数：
- `system_prompt` (str|None) — 任务侧生成的 prompt；为空则用 `prompts/extract.default.md`
- `client` (str|None) — 存在 `prompts/extract.<client>.md` 时把其内容**追加**到 system prompt 之后
- `model` (str|None) — 默认取配置 `models.extract`
- `max_retries` (int) — LLM 返回空时的额外重试次数，默认 2
- `max_tokens` / `temperature` / `timeout` / `usage_out`

`request_dify(paragraph, other_inputs=None)`：
- `paragraph` (str) — 群聊记录文本，为空抛 `ValueError`
- `other_inputs` — 仅为兼容原 Dify 客户端签名，未使用

## Outputs

- `str` — 抽取结果文本，格式为 `问题:...\n答案:...` 以 `###` 分隔，交由
  `kdb.mining.common.schema.qa_model_output.parse_qa_answer` 解析
- `None` — 重试后仍失败。调用方（`process_normal_group_data`）按"跳过该群"处理

## SQL

无 SQL 读写。

## 注意

- **不分块**：与原 Dify 流一致，一个群的整个时间窗是一次调用。发起大时间窗任务前需按
  `Σ(len(send_user)+2+len(content)+8)` 估算最大群的 prompt 长度。
- 只覆盖「普通群 + 非 mix」这一条分支。转发群和 mix 分支是另外的 Dify 应用，仍走 Dify。
- 凭证来自 `config/llm_config.json`（不入库），缺失时调用方会回落 Dify，见
  `gen_knowledge_from_chat._build_norm_nomix_provider`。

## Source

`src/kdb/mining/chat/generation/extractor.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
