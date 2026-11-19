# kdb.mining.document.pipelines.qa_segment.DocumentQAMiningTaskController.run_all_stages

## Signature

`DocumentQAMiningTaskController.run_all_stages(self)`

## Inputs

原控制器任务参数及可选document_dedup。

## Outputs

原bool成功语义；所有文档被skip_new过滤时跳过生成步骤，仍完成统计。所有插入阶段成功后finish_document_dedup核对新知识数量才删除旧快照；任何失败返回False并记录任务失败。

## SQL / ES

原dops_task_kggen_info任务状态更新；ES变更通过bridge，详见document_dedup与conflict_store契约。

## Source

`src/kdb/mining/document/pipelines/qa_segment.py`
