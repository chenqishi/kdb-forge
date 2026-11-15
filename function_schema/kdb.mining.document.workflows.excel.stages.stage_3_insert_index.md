# kdb.mining.document.workflows.excel.stages.stage_3_insert_index

## Signature

`stage_3_insert_index(self)`

## Inputs

控制器 self，使用 task_id、status_updater、index_input_file_path、index_name，以及 `_get_index_config_path()` 返回的配置路径。输入文件必须存在；结构化图片处理成功后 index_input_file_path 为 image_processed_json_file_path，否则沿用 json_file_path。

## Outputs

先更新阶段为 index_insert；文件或配置缺失返回 False。调用 `_run_command(cmd, 'insert_index')` 后按结果返回 True/False；try 块内异常记录并返回 False。状态更新位于 try 之前，其异常不由本函数捕获。

## 路径和子进程契约

使用 argv 列表，保留含空格路径：`sys.executable -m kdb.entrypoints.cli.retrieval insert_data_to_search_index --data_file=<index_input_file_path> --config_path=<配置路径> --is_update_data=1 --index_name_assign=<index_name>`。阶段由 ExcelQASegmentUploadController.run_all_stages 调度，实际命令执行交给控制器的 `_run_command`。

回归见 `tests/mining/test_excel_qa_segment_upload_control.py` 的 stage_3 测试；替换命令执行和状态更新，不启动真实任务、不写 ES。

## SQL / ES

本函数不直接执行 SQL 或 ES 请求；任务阶段更新委托 status_updater.update_task_stage，沿其已有 SQL 契约；索引写入委托 insert_data_to_search_index，沿其入库参数和写入契约。这里不声明完整数据库表结构已核验。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.mining.document.pipelines.excel.ExcelQASegmentUploadController.stage_3_insert_index`

## Source

`src/kdb/mining/document/workflows/excel/stages.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
