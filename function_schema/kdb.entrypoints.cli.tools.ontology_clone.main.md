# kdb.entrypoints.cli.tools.ontology_clone.main

## Signature

`main(argv=None, service=None) -> int`

## Inputs

--source-client/--source-product/--target-client必填，--target-product可选；--status=active/inactive默认active，--review-status=pending/approved/rejected默认pending；--dry-run只预览。service可供测试注入。

## Outputs

新增--review-status（pending/approved/rejected，默认pending），--status改为active/inactive默认active；dry-run同样显示两个状态。源必须启用且审核通过，克隆件不继承源的审核结果。

select_ontology源文档→校验→深拷贝并改目标作用域→重校验→insert_ontology，默认active且review_status=pending；dry-run只输出摘要不写。目标客户非空；不修改源行，不合并，不覆盖已有行。退出0成功、2源不存在、3同业务键已存在、4校验失败、5数据库不可用；非0 JSON错误写stderr。

## SQL

无直接 SQL，通过 OntologyRepository 访问 dops_ontology；元信息及纯校验不连接数据库。

## Source

`src/kdb/entrypoints/cli/tools/ontology_clone.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
