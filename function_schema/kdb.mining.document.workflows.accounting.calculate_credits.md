# kdb.mining.document.workflows.accounting.calculate_credits

## Signature

`calculate_credits(self)`

## Inputs

原 self.file_mapping_path/status_updater/task_id。

## Outputs

逐文件调用 access_document_clear_price(re_parse=False)，累计成本并四舍五入两位写回；异常与跳过规则不变。

## SQL

未新增 SQL。状态写入通过原实例的 status_updater，表字段见 kdb.mining.tasks.status.TaskStatusUpdater 对应契约。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.mining.document.pipelines.qa.DocumentQAMiningTaskController.calculate_credits`
- `kdb.mining.document.pipelines.qa_segment.DocumentQAMiningTaskController.calculate_credits`

## Source

`src/kdb/mining/document/workflows/accounting.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
