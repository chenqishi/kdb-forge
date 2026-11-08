# kdb.shared.config.paths.module

## Inputs

Published runtime resource arguments, existing cwd, environment and unchanged business function signatures.

## Outputs

Use kdb.shared.config.paths to resolve project-local configuration/data/output. Remove fake __legacy_source_file__ and all root-package sys.path injection. Existing prompt content stays under resources/prompts/mining/chat_qa_extract. Default language model is resources/models/lid.176.ftz; missing resource is reported, never downloaded or created. Flask source roots are real canonical source directories. Existing resource load timing is retained.

## SQL

No SQL/ES changes or external actions.

## Source

`src/kdb/shared/config/paths.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
