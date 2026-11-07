# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.infer_payoneer_olive_category

## Signature

`SearchDataInterface.infer_payoneer_olive_category(self, client: str, data: Dict[str, Any])`

## Inputs

client 与 data；使用当前客户类目树、ext_info.marketplace/model_platform、ext_info.tags 或 data.tags、title。

## Outputs

只在归一化 client 为 payoneerolive 时尝试。未加载缓存则加载真实类目映射；无匹配返回 (None,None)。按显式平台精确匹配300、标签200、问题文本100排序；同分优先较长类目路径，跳过默认分组。返回 (parent_chain, {category_id,category_name,score:0.9,source})，source 为 model_platform/model_tag/question_text。process_one_data 仅在类目链未解析且不存在手工来源时调用，不覆盖已明确人工类目。

## SQL

无 SQL；类目树来自现有 HTTP 类目服务和当前缓存，不在此函数写 ES。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。所列 SQL 表字段来自此实现的参数化查询；未取得额外 DDL，不宣称完整表结构已核验。
