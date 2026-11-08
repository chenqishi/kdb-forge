# kdb.entrypoints.http.tasks.bootstrap.parse_args

## Signature

`parse_args()`

## Inputs

sys.argv：script-dir、port、host、resource-config、max-concurrency。

## Outputs

argparse Namespace；默认端口 6000、host 0.0.0.0、max-concurrency 10，其余可选路径为 None。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/entrypoints/http/tasks/bootstrap.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
