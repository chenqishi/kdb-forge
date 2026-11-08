# kdb.retrieval.categories.inference.infer_payoneer_olive_category

## Signature

`infer_payoneer_olive_category(self, client: str, data: Dict[str, Any])`

## Inputs

client 与 data；使用当前客户类目树、ext_info.marketplace/model_platform、ext_info.tags 或 data.tags、title。

## Outputs

只在归一化 client 为 payoneerolive 时尝试。未加载缓存则加载真实类目映射；无匹配返回 (None,None)。按显式平台精确匹配300、标签200、问题文本100排序；同分优先较长类目路径，跳过默认分组。返回 (parent_chain, {category_id,category_name,score:0.9,source})，source 为 model_platform/model_tag/question_text。process_one_data 仅在类目链未解析且不存在手工来源时调用，不覆盖已明确人工类目。

## SQL

无 SQL；类目树来自现有 HTTP 类目服务和当前缓存，不在此函数写 ES。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.infer_payoneer_olive_category`

## Source

`src/kdb/retrieval/categories/inference.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
