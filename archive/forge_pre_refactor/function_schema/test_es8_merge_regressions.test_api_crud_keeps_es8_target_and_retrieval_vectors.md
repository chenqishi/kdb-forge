# test_api_crud_keeps_es8_target_and_retrieval_vectors

## Inputs
es8_stack, monkeypatch and serverless/paas index parameters.

## Outputs
Real HTTP insert/modify/delete reaches real ES8 client at intended provider/index; audit=2, synonyms/custom/image indexes preserved, modified title updates native KNN vector, refresh and delete correctly target same index.

## SQL
None; offline only.
