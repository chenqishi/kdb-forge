# KnowledgeService.from_count_config

## Inputs
运行配置路径；读取 engine_config_path 及可选 default_index_name/test_index_name。

## Outputs
构造真实 RoutedLegacyEngine、Repository、KnowledgeService 的统计专用实例。
同时传入 ensure_index=False 和 extra_params.ensure_index_on_init=False，覆盖配置中的建库开关。
embedding_client 为 None；不调用普通 from_config、不读取 embedding/legacy search 配置。
引擎仍校验已有 ES8.17 配置、默认索引与 vector_fields；初始化错误由 API 转为失败响应。

## SQL
无。读取本地配置，创建 ES 客户端；不请求 ES、不建库、不更新 mapping。
