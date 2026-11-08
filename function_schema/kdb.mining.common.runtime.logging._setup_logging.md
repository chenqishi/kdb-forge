# kdb.mining.common.runtime.logging._setup_logging

## Signature

`_setup_logging(self)`

## Inputs

原控制器实例，沿用 logging root。

## Outputs

清除原 root handlers，按原格式与 INFO 级别输出到 sys.stdout；不改变调用时机。

## SQL

无直接 SQL。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.mining.chat.pipeline.ChatQAMiningTaskController._setup_logging`
- `kdb.mining.document.pipelines.qa.DocumentQAMiningTaskController._setup_logging`
- `kdb.mining.document.pipelines.qa_segment.DocumentQAMiningTaskController._setup_logging`
- `kdb.mining.document.pipelines.excel.ExcelQASegmentUploadController._setup_logging`
- `kdb.mining.web.pipeline.HtmlKgGenTaskController._setup_logging`

## Source

`src/kdb/mining/common/runtime/logging.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
