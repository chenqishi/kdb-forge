# main

Inputs: current ES8 diagnostic interpreter and optional test evidence environment variable. Outputs: run only new off-task tests plus relevant existing ES8/insert/duplicate tests using pytest; ensure imported Elasticsearch remains8.17. Print dependency provenance. Existing retrieval-only ES8 venv lacks Fire; sideload only existing pure-Python Fire/termcolor/six for the test process, explicitly report production dependency gap. SQL/side effects: isolated process and tmp/evidence files only, no network/ES writes/deploy/restart/install.
