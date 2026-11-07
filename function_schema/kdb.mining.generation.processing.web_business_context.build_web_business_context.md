# kdb.mining.generation.processing.web_business_context.build_web_business_context

## Signature

`build_web_business_context(*, client: str, knowledge_objective: Optional[str]=None, cache_dir: str, ttl_days: int=30, search_callable: Optional[Callable[[str], str]]=None, now_ts: Optional[float]=None) -> dict`

## Description

可选的网络业务背景构建（默认关闭，仅 enable_web_context=true 时被调用）。结果只用于客户业务画像/术语/产品边界，禁止作为文档事实写入答案。结果按 client+knowledge_objective 缓存（TTL 默认 30 天）。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| client | str | 是 | 客户名 |
| knowledge_objective | str\|None | 否 | 知识目标，参与缓存 key |
| cache_dir | str | 是 | 缓存目录 |
| ttl_days | int | 否 | 缓存有效期，默认 30 |
| search_callable | Callable[[str],str]\|None | 否 | 外部注入的检索函数；未提供则不发起检索 |
| now_ts | float\|None | 否 | 时间戳注入（测试用） |

## Outputs

| 字段 | 类型 | 说明 |
|------|------|------|
| context_text | str | 业务背景文本；无检索能力时为空 |
| sources | dict | {web_search: bool} |
| cache_hit | bool | 是否命中缓存 |
| cache_path | str | 缓存文件路径 |
| warning | str | 降级/空结果说明 |

## 降级策略

- search_callable 未注入 → 返回空上下文 + warning，不联网。
- 检索抛异常 → 返回空上下文 + warning。
- 命中未过期缓存直接返回。

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`src/kdb/mining/generation/processing/web_business_context.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
