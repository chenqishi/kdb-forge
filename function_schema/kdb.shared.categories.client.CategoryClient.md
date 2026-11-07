# kdb.shared.categories.client.CategoryClient

## Signature

`CategoryClient(self, service_url='', update_interval=36000)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

类目服务数据接口（HTTP GET 类目树 → 本地 name/id 反映射缓存）。复刻旧 `SearchDataInterface` 内嵌的 `load_category_map_dict` / `map_cate_name_to_id` / `get_category_parent_chain`，抽成独立数据模块供 `KnowledgeService.web_search` 做 `category_names→category_ids` 映射。**未配置 service_url 时全部方法安全降级（不发 HTTP，返回 None/[]）**，与旧实现 `category_service_url=''` 行为一致。

## 构造

`__init__(service_url: str = "", update_interval: float = 36000)`
- `service_url`：旧 config `category_service_url`；空串=禁用。
- `update_interval`：每 client 缓存刷新间隔秒（旧 `category_update_time_interval`）。

## 方法 Inputs/Outputs

- `load_category_map_dict(client, user=None) -> True|None`：GET `service_url?client=...`，响应 `data` 为类目树（节点含 categoryId/categoryName/level/children）；构造 `{name_map_dict: {"根-…-叶全路径": chain}, id_map_dict: {id: chain}}` 存入 `all_client_category_dict[client]`。缓存间隔内/无 URL/请求失败 → None。
- `map_cate_name_to_id(client, category_name) -> id|None`：全路径名 → 末级 category_id；未命中先尝试加载一次。
- `get_category_parent_chain(client, cate_id=None, cate_name=None) -> List[Dict]`：根→当前完整链；未命中允许强制加载一次再查。

## 关键依赖

`requests`（超时 10s）。

## SQL

无（HTTP 数据接口）。

## Source

`src/kdb/shared/categories/client.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
