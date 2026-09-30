# RoutedLegacyEngine.__init__

## Inputs
engine config 或 config_path、默认 index、向量字段、额外参数、可选 router；`ensure_index` 控制初始化时是否检查/创建 ES8 native KNN mapping。
## Outputs
初始化按 index 路由的 ES8.17 native 查询引擎。
## SQL
无。

## Runtime safety

`extra_params.ensure_index_on_init=false` 可在只读盘点或空目标集群启动服务时关闭初始化建索引；缺省仍保持原有 `ensure_index=True` 行为。该开关不改变检索 DSL，只避免启动时写入缺失索引。
