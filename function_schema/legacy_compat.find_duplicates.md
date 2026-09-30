# LegacySearchDataInterfaceMixin.find_duplicates

## Inputs
旧版 `find_duplicates(data, topK, is_need_llm, index_name, exclude_self, is_only_title,
basic_threshold, title_basic_threshold)`。

## Outputs
返回重复文档列表；候选来自 ES8.17 检索，精确判断使用旧 SimilityTools 兼容实现。

## SQL
无；读 Elasticsearch。
