# kdb.__init__.__getattr__

## Signature

`__getattr__(name)`

## Inputs

`name`: the requested public package attribute.

## Outputs

`SearchDataInterface` lazily resolves to the existing retrieval application class. All other names raise `AttributeError`. Importing the package does not eagerly import the retrieval application or initialize external clients.

## SQL

None. Attribute lookup does not create a service instance or query a backend.

## Source

`src/kdb/__init__.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
