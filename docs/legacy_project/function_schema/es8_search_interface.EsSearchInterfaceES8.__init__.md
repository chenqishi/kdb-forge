# EsSearchInterfaceES8.__init__

## 所属文件
`knowledge_interface_tools/es8_search_interface.py`

## Inputs
保持旧位置参数顺序：`hosts, index_name, username, password, vector_fields, config_path, extra_params`；额外支持 keyword-only `config`、注入测试用 `router`、`ensure_index`。
## Outputs
初始化按 index 路由的 ES8.17 native KNN 引擎；默认检查/创建 HNSW mapping。
## SQL
无。

## Runtime safety
`extra_params.ensure_index_on_init=false` 可在只读盘点或空目标集群启动服务时关闭初始化建索引。缺省仍保持 `ensure_index=True`。旧 ES7 未索引 dense_vector 不能原地升级，检测到后抛出迁移错误。
