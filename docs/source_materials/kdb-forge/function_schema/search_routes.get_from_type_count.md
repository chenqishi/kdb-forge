# search_routes.get_from_type_count

## Inputs
POST `/get_from_type_count`，FromTypeCountRequest；沿用搜索接口 Basic 认证与显式直接 loopback 例外。
在 retrieval_app 和完整 app 中由共用 search_router 提供。

## Outputs
HTTP 200：`{"success": true, "count": N, "message": ""}`，或
`{"success": false, "count": 0, "message": "统计失败"}`。
空/缺/null index 直接成功 0，无 Service 初始化；非空请求经真实 Service/Repository/Engine。
非法参数 422；认证行为与现有接口一致（401/配置缺失503）。
缺失索引不创建；异常细节不会进入 HTTP 响应或日志。

## SQL
无；仅原索引 native `_count`，无 ES 写入或 routing/alias 修改。
