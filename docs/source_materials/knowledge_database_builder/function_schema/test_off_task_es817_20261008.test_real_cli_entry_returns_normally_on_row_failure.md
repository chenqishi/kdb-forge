# test_real_cli_entry_returns_normally_on_row_failure

Inputs: actual search_index_data_interface.py __main__ source run with actual Fire via runpy; external embedding boundary TimeoutError and synthetic file/config/resultfile. Outputs: real entry returns normally and writes failure1/success0 counters with zero ES upserts; independent confirmation that O01 is not caused by subprocess stub. No claim an OS child actually ran. SQL/side effects: temporary files/stdout only; block sockets, external embeddings/LLM/SQL. Preserve source/configs.
