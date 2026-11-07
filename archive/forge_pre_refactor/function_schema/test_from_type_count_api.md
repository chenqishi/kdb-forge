# test_from_type_count_api

## Inputs
真实 FastAPI 应用、Service、Repository、RoutedLegacyEngine、IndexClientRouter；仅外部 ES 客户端替换。
两 provider 的外部文档包含不同来源、审核、软删、类型及时间边界。

## Outputs
验证精确 DSL、原索引路由、两应用挂载、别名/严格参数、无附加业务过滤、双端闭区间、
有效单边忽略、倒序自然 0、0/超过 10000 精确统计及 malformed/partial/ES 异常失败 0。
额外覆盖空索引零初始化、冷启动关闭配置中的 ensure、无 embedding/建库请求、认证与日志不泄漏。

## SQL
无；离线回归，无 ES 网络或写入。
