# kdb.mining.common.runtime.results.count_qa_results

## Signature

`count_qa_results(self)`

## Inputs

原管道 self.search_data_file_path 指向的 JSONL。

## Outputs

统计 quality_level=high 且 data_type=qa 的条数；逐行跳过非法 JSON，缺文件/异常返回 qa_num=0。

## SQL

无直接 SQL。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.mining.document.pipelines.qa_segment.DocumentQAMiningTaskController.count_qa_results`
- `kdb.mining.web.pipeline.HtmlKgGenTaskController.count_qa_results`

## Source

`src/kdb/mining/common/runtime/results.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
