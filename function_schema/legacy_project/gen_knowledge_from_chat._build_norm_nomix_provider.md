# _build_norm_nomix_provider

## 所属文件
`chatknowledge/gen_knowledge_from_chat.py`

## 功能描述
构造「普通群 + 非 mix」分支的 QA 抽取模型工厂，返回 `platform -> model` 的可调用对象。
这条分支从原来的 Dify 流「对话QA抽取-norm-nomixv1」切到本地 `chat_qa_extract`。

## Inputs
- `system_prompt` (str|None) — 任务侧生成的 system prompt（来自 `prompt_file`）

## Outputs
- `callable(platform: str) -> model` — model 具备 `.request_dify(paragraph)` 接口。
  同一 platform 只构造一次（内部 dict 缓存）。

## 选择逻辑
1. 尝试 `chat_qa_extract.load_llm_config()`，若 `llm_client.is_configured()` 为真
   → 返回 `ChatQAExtractor(system_prompt=..., client=platform)`
2. import 失败或凭证缺失 → 回落 `DifyWorkFlowRequest(dify_api_key_normal_nomix)`，
   行为与改造前完全一致

`platform` 即任务的 `index`（通常等于 client），用来命中 `prompts/extract.<platform>.md`。

## 未改动的分支
- 转发群（`group_type='forward'`）：仍用 `dify_api_key_forward_nomix` / `dify_api_key_forward_mix`
- mix 平台（`platform == 'mix'`）：仍用 `dify_api_key_normal_mix`

这两条对应的是另外的 Dify 应用，本地没有实现。

## SQL
无 SQL 读写。
