# kdb.mining.tasks.submission.document_tasks.run

## Signature

`run(args)`

## Inputs

现有命令参数对象 args；字段来自模块 argparse 定义。

## Outputs

载入文档清单、解析类目、上传资源并写 tasks.json；只有 submit 开启时提交任务。未开启 submit 仍有上传行为。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/tasks/submission/document_tasks.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
