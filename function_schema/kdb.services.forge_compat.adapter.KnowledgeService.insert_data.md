# kdb.services.forge_compat.adapter.KnowledgeService.insert_data

## Signature

`KnowledgeService.insert_data(self, data, **kwargs)`

## Inputs

调用方 data 字典与原插入关键字参数。

## Outputs

先 deepcopy 调用方数据，再委托同一 SearchDataInterface.insert_data；保留 (success,message) 返回与插入/重复处理，避免把原接口的 _id 赋值副作用传回 Forge 调用方。

## SQL

无直接 SQL；委托当前检索应用实现执行 ES 和已配置外部接口。

## Source

`src/kdb/services/forge_compat/adapter.py`。所列 SQL 表字段来自此实现的参数化查询；未取得额外 DDL，不宣称完整表结构已核验。
