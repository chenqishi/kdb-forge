# kdb.shared.clients.local_llm_adapter.request_knowledge_llm

## Signature

`request_knowledge_llm(query: str, system_message: str, *, model_name: Optional[str]=None, provider: Optional[str]=None, image_urls: Optional[List[str]]=None, temperature: float=0.1, max_tokens: int=8000, usage_out: Optional[dict]=None, agents_root: Optional[str]=None) -> str`

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

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Description

知识挖掘统一 LLM 调用入口。内部优先复用 agents 项目的 `commons.llm_client.request_llm`（多渠道、自动路由、失败 fallback）。可选增强，导入失败/配置缺失时优雅降级返回空字符串。

## 配置/降级

- 运行时只使用显式配置的外部 client 插件：`KDB_LLM_CLIENT_PATH` 指向实现文件；必须提供 `configure_providers(llm_config)` 与支持现有参数（包括 image_urls）且返回3元组的 `request_llm`。
- 保留已显式提供的 `agents_root` 参数或 `AGENTS_PROJECT_ROOT` 环境变量兼容；不再提供Mac/旧仓默认根目录。该兼容入口仅按明确传入根目录找 commons/llm_client.py，不加入sys.path。
- 可选渠道配置：`KDB_LLM_CONFIG`，仍兼容显式 `AGENTS_LLM_CONFIG`；没有任意旧仓隐式配置查找。
- 未配置插件、导入失败或调用异常 → 明确日志并返回空字符串，调用方保留既有Dify/频次兜底。不能替换为本仓返回2元组的kdb.mining.quality.chat_qa_extract.llm_client。

## 依赖

只由用户显式配置的插件；新增配置仅描述现有外部调用协议，不改变采样、模型、返回值或降级算法。无SQL。

## Source

`src/kdb/shared/clients/local_llm_adapter.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
