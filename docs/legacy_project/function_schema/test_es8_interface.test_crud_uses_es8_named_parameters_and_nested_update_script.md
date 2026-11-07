# test_crud_uses_es8_named_parameters_and_nested_update_script

Inputs: original routed fake clients. Outputs: Serverless insert/partial update retains ES8 named doc API; PaaS conditional update retains native nested Painless assignment. Serverless conditional update is independently covered by actual business/service + PIT/CAS tests. Do not demand banned script serialization on Serverless just to preserve an obsolete transport assertion; public request semantics remain unchanged. Only mocked client boundary, no live calls.
