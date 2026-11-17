# kdb.retrieval.ontology.repository.get_connector

## Signature

`get_connector(config_path: Optional[str]=None)`

## Inputs

按设计 v8 对应文档模型、请求模型或模块参数；Python 3.9 / Pydantic v2。

## Outputs

get/resolve 返回行或 None；list 返回 (元数据列表,total)；insert 返回 ontology_id；UPDATE 返回 rowcount，0 交 service 区分 404/409；故障明确抛 422/503/500，不伪装空结果。

## SQL

无业务 SQL；懒初始化 kdb.shared.database.mysql.MySQLConnector。配置显式参数→KDB_MYSQL_CONFIG→project_path(config/mysql_conn_config.json)，线程锁保护进程单例；不自行创建另一种连接池。

## Source

`src/kdb/retrieval/ontology/repository.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
