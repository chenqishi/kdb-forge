# LegacySearchDataInterfaceMixin.get_unique_values

## Inputs
旧 index_name、field_name、size、include_doc_count、extra_query。

## Outputs
唯一值列表或带计数的字典列表。

## SQL
无；读 Elasticsearch terms aggregation。
