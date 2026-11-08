# scripts.testing.architecture.import_cycles

## Signature

`import_cycles(modules, edges)`

## Inputs

模块集合与依赖边。

## Outputs

Tarjan 强连通分量，返回长度大于 1 的模块环；忽略模块自身边。

## SQL

无；不导入产品，不连接外部服务。

## Source

`scripts/testing/architecture.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
