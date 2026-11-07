# LegacySearchDataInterfaceMixin.web_search_data

## Inputs
旧版 `query/client/index_names/condition_dicts/page_size/page_num/score_threshold`。

## Outputs
返回 `(candidate_docs, total_num)`；保留类目名称转 ID、默认 page_size=10000、多模态 URL
渲染和 `score=min(score/5, 1)`。
index_names 接受逗号分隔字符串或列表；类目名映射可用注入的 category_client，
未注入则复用现有通用 map_cate_name_to_id。

## SQL
无；读 Elasticsearch。
