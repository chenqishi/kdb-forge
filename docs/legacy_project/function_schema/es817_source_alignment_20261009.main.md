# main

## Inputs / Outputs
Read verified private200-query fixture locally; select one QA public/private query with synonyms and top20 from each of four public indexes. SSH stdin carries private inputs to isolated nice15 process on120 existing ES8 venv with bytecode disabled. Write new sanitized evidence locally only; no production code/config/index writes, deployment, restart, embedding or live service HTTP. Preserve all earlier evidence and protect private fixture.

## SQL
None.

Optional --case restricts to one of the four originally selected cases; reject unknown selection. Required --private-output is new local0700 directory; private_failure events save input/changed actual docs0600 there, public evidence strips private events. Preserve original completed evidence and write repeat to separate new output directory.
