# kdb.mining.document.workflows.stages.stage_1_download_files

## Signature

`stage_1_download_files(self)`

## Inputs

原 self.files/downloader/client/data_dir/file_mapping_path 与任务状态对象。

## Outputs

按原顺序下载，校验成功与文件存在，写文件映射；失败短路；任务阶段更新不变。

## SQL

未新增 SQL。状态写入通过原实例的 status_updater，表字段见 kdb.mining.tasks.status.TaskStatusUpdater 对应契约。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.mining.document.pipelines.qa.DocumentQAMiningTaskController.stage_1_download_files`
- `kdb.mining.document.pipelines.qa_segment.DocumentQAMiningTaskController.stage_1_download_files`

## Source

`src/kdb/mining/document/workflows/stages.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
