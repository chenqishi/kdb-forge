# kdb.mining.chat.query_analysis.ecommerce.create_mysql_connector

## Signature

`create_mysql_connector(mysql_config_path: str, retries: int=3, sleep_seconds: float=3.0) -> MySQLConnector`

## Description

创建 `MySQLConnector`，对远端 RDS 偶发连接超时做有限重试。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| mysql_config_path | str | 是 | MySQL 配置路径 |
| retries | int | 否 | 最大尝试次数，默认 3 |
| sleep_seconds | float | 否 | 每次失败后的等待秒数 |

## Outputs

| 类型 | 说明 |
|------|------|
| MySQLConnector | 成功创建的连接器 |

## SQL

无 SQL。本函数只创建连接池，不执行查询。

## Source

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
