# test_insert_ext_info_20261005.test_partial_update_extension_has_no_control_fields

Inputs: offline service fixture and omitted/null/empty/explicit ext_info variants. Verify actual partial insert/update preserves absence of title, ID/upsert contract and excludes request controls from ext_info. No real ES write or SQL.
