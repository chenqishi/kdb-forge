# local_llm_adapter.request_knowledge_llm

## 描述
知识挖掘统一 LLM 调用入口。内部优先复用 agents 项目的 `commons.llm_client.request_llm`（多渠道、自动路由、失败 fallback）。可选增强，导入失败/配置缺失时优雅降级返回空字符串。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | str | 是 | 用户 prompt（待抽取正文/段落） |
| system_message | str | 是 | 系统 prompt（业务背景 + 抽取规则） |
| model_name | str\|None | 否 | 模型名，按名自动路由渠道 |
| provider | str\|None | 否 | 显式渠道 |
| image_urls | list[str]\|None | 否 | 多模态图片 URL |
| temperature | float | 否 | 默认 0.1 |
| max_tokens | int | 否 | 默认 8000 |
| usage_out | dict\|None | 否 | 回填 token 用量 |
| agents_root | str\|None | 否 | 覆盖 agents 项目根目录 |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 模型回复文本；后端不可用/失败时返回 "" |

## 配置/降级
- agents 根目录：环境变量 `AGENTS_PROJECT_ROOT`，默认 `/Users/chenqishi/stone_fish/agents`。
- LLM 渠道配置：环境变量 `AGENTS_LLM_CONFIG`，默认 `agents/config/agent_service_config.json` 的 `llm` 节。
- 导入失败 / 调用异常 → 记录 warning/error，返回 ""，调用方需降级。

## 依赖
- 跨项目 `commons.llm_client.configure_providers` / `request_llm`。
- 参考 `/Users/chenqishi/stone_fish/agents/function_schema/llm_client.request_llm.md`。
