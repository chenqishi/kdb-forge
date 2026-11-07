# _FallbackSimilityTools.is_simility_knowledge

## Inputs
Two documents; is_need_llm, is_only_title, basic_threshold, title_basic_threshold.
## Outputs
0/1 from the remote implementation's legacy cosine thresholds; mismatched platform
or data_type yields 0. If thresholds cannot decide and LLM is requested, raise
RuntimeError (no silent acceptance when LLM is unavailable).
## SQL
None. No network.
