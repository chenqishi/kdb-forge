# LegacySearchDataInterfaceMixin category methods

## Inputs/Outputs
保留 `load_search_engine`、`load_category_map_dict`、`map_cate_name_to_id`、
`get_category_parent_chain` 的旧参数和返回结构。

类目只解析上游显式给出的信息；Payoneer Olive 自动推断归挖掘侧，不在本次兼容范围。
不根据 marketplace/model_platform、标签或标题猜测类目，也不按模型来源丢弃上游类目。

## SQL
无；类目来源为配置的 HTTP 服务，知识文档读写 Elasticsearch。
