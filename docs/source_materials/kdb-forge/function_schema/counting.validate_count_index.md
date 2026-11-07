# counting.validate_count_index

## Inputs
`value: Optional[str]`：原始单个索引名。

## Outputs
保留 `None`、空串或合法字符串原值。拒绝非字符串、联合索引、通配符、空白、
远程集群/日期表达式、ES 非法字符/前缀以及 UTF-8 长度超过 255 的名称，抛 `ValueError`。
不转小写、不裁剪、不查 alias 元数据、不添加索引后缀。

## SQL
无；纯本地函数，无外部 I/O。
