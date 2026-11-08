# tests.conftest.module

## Inputs

当前项目tests/conftest位置。

## Outputs

裸pytest和offline_runner共用同一offline_guard模块，先install再prepare_paths，始终使用当前src和private测试SDK，无旧根路径。默认整套测试与明确排除规则同runner。

## SQL

禁止真实SQL/网络/子进程；仅当前项目/临时/显式证据目录可写。

## Source

`tests/conftest.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
