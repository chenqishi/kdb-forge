# scripts.testing.architecture.inspect_imports

## Signature

`inspect_imports(source_root)`

## Inputs

src 目录。仅解析 Python AST，不导入业务代码。

## Outputs

当前模块到文件映射及 source/target/line 依赖边，解析相对导入。

## SQL

无；不导入产品，不连接外部服务。

## Source

`scripts/testing/architecture.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
