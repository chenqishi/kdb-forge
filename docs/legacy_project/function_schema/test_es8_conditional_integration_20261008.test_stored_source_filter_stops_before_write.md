# test_stored_source_filter_stops_before_write

Inputs/Outputs: Parametrize disabled/excludes/includes source storage mapping and public update_value/update_by_query. Expected False/visible error before PIT/bulk; documents unchanged. Migration target complete _source is required, request source=True does not restore storage-excluded fields.
SQL and persistent side effects: none.
