# kdb.mining.common.runtime.accounting.predict_credits

## Signature

`predict_credits(self)`

## Inputs

同一管道 self.status_updater 与 self.task_id。

## Outputs

原 update_predict_credits(task_id,-1) 调用；成功 True，捕获异常记录后 False。

## SQL

未新增 SQL。状态写入通过原实例的 status_updater，表字段见 kdb.mining.tasks.status.TaskStatusUpdater 对应契约。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.mining.chat.pipeline.ChatQAMiningTaskController.predict_credits`
- `kdb.mining.document.pipelines.qa.DocumentQAMiningTaskController.predict_credits`
- `kdb.mining.document.pipelines.qa_segment.DocumentQAMiningTaskController.predict_credits`
- `kdb.mining.web.pipeline.HtmlKgGenTaskController.predict_credits`

## Source

`src/kdb/mining/common/runtime/accounting.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
