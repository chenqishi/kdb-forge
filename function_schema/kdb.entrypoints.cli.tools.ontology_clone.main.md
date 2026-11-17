# kdb.entrypoints.cli.tools.ontology_clone.main

## Signature

`main(argv=None, service=None) -> int`

## Inputs

按设计 v8 对应文档模型、请求模型或模块参数；Python 3.9 / Pydantic v2。

## Outputs

resolve源文档→校验→深拷贝并改目标作用域→重校验→create，默认draft；dry-run只输出摘要不写。目标客户非空；不修改源行，不合并，不覆盖已有行。退出0成功、2源不存在、3同业务键已存在、4校验失败、5数据库不可用；非0 JSON错误写stderr。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/entrypoints/cli/tools/ontology_clone.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
