# kdb.retrieval.ontology.errors.module

## Signature

`kdb.retrieval.ontology.errors (module)`

## Inputs

OntologyError(code:str,http_status:int,message:str,details=None)，以及11个稳定错误码常量。

## Outputs

to_body() 返回 {success:false,code,message,details}；details总是列表，缺省[]。异常只承载业务错误，不含SQL/HTTP依赖、不泄露堆栈。

## SQL

无直接 SQL。

## Source

`src/kdb/retrieval/ontology/errors.py`。设计依据：业务本体实现级设计说明书 v8；实现中的最小修正见 `docs/api.md` 的业务本体说明。
