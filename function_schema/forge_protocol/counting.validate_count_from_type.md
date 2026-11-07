# counting.validate_count_from_type

## Inputs
`value: str`：调用方传入的来源值。

## Outputs
非空字符串原样返回；空串或非字符串抛 `ValueError`。
不 trim、不做规则映射、不替换为 `from_type_norm`。

## SQL
无；纯本地函数。
