# kdb.retrieval.ontology.schema.module

## Signature

`python -m kdb.retrieval.ontology.schema --write | --check`

## Inputs

--write或--check（二选一）；读取OntologyDocument.model_json_schema()，以及schema.py内的版本/大小/分页/状态/作用域/保留键常量。

## Outputs

模型单一真值生成 Draft 2020-12 JSON Schema，固定$id、indent=2、ensure_ascii=False、sort_keys=True和末尾换行。--write覆盖包内ontology.schema.json；--check一致退出0，否则1。不导入仓储/HTTP，不连接数据库；模块再导出限制常量与枚举；DEFAULT_PAGE_SIZE=100、MAX_PAGE_SIZE=100，由路由、service和repository复用。

## SQL

无直接 SQL。

## Source

`src/kdb/retrieval/ontology/schema.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
