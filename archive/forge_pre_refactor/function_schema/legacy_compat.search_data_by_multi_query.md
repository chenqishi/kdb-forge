# LegacySearchDataInterfaceMixin.search_data_by_multi_query

## Inputs
旧版多 query 参数：`query_list`、`index_names`、`condition_dicts`、`size`、检索类型和同义词开关。

## Outputs
返回 `(candidate_docs, total_num)`，保留多 query 合并和异常线程回退。
index_names 同时接受字符串和列表；保留本地最新多模态 URL 渲染。

## SQL
无；读 Elasticsearch。
