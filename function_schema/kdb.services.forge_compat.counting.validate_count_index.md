# kdb.services.forge_compat.counting.validate_count_index

## Signature

`validate_count_index(value: Optional[str]) -> Optional[str]`

## Inputs

`value: Optional[str]`：原始单个索引名。

## Outputs

保留 `None`、空串或合法字符串原值。拒绝非字符串、联合索引、通配符、空白、
远程集群/日期表达式、ES 非法字符/前缀以及 UTF-8 长度超过 255 的名称，抛 `ValueError`。
不转小写、不裁剪、不查 alias 元数据、不添加索引后缀。

## SQL

无；纯本地函数，无外部 I/O。

## Source

`src/kdb/services/forge_compat/counting.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
