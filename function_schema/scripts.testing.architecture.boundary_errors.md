# scripts.testing.architecture.boundary_errors

## Signature

`boundary_errors(edges)`

## Inputs

实际静态依赖边。

## Outputs

禁止方向的边及原因；校验公共层、检索桥、业务/入口、独立项目边界。

## SQL

无；不导入产品，不连接外部服务。

## Source

`scripts/testing/architecture.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
