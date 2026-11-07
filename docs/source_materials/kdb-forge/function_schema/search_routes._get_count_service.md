# search_routes._get_count_service

## Inputs
进程 KDB_FORGE_CONFIG，缺省 config/config_search_runtime.local.json。

## Outputs
独立锁保护的懒加载统计 Service 缓存，调用 KnowledgeService.from_count_config。
与搜索 Service 缓存独立，避免冷启动触发普通 Service 的建库/embedding 初始化。
初始化失败上抛由 count API 转为失败响应；成功时不输出配置或连接信息。

## SQL
无；本地配置读取及无请求的客户端初始化。
