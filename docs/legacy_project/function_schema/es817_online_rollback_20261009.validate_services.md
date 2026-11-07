# validate_services

Inputs: activation journal with exact retrieval/mining parent PID, creation time, command line and expected interpreter. Outputs: validated psutil Process instances and their current descendants. Require cwd=/root/knowledge_database_builder, known original service script and exact command line/interpreter; no broad process-name matching. Reject PID reuse or unrelated process before sending any signal. Read-only process inspection, no SQL/ES.
