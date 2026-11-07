# test_address_only_does_not_select_es8

Inputs: real legacy factory autodetection helper and mocked info boundary reporting ES8.17. Outputs: current helper still selects es7; proves canonical explicit es_version8.17 is required and URL-only swap insufficient. Not counted as new unresolved implementation regression because original factory promises ES7/OpenSearch autodetect and explicit ES8 selection. SQL/side effects: no old ES client/network; only info fixture response.
