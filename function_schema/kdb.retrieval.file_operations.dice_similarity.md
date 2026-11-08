# kdb.retrieval.file_operations.dice_similarity

## Signature

`dice_similarity(cls, a: str, b: str) -> float`

## Inputs

两个文件名字符串。

## Outputs

字符 bigram Dice 浮点相似度。

## SQL

无。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.dice_similarity`

## Source

`src/kdb/retrieval/file_operations.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
