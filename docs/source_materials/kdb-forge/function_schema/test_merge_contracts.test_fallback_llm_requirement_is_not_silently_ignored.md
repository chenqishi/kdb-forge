# test_fallback_llm_requirement_is_not_silently_ignored

## Inputs
Two compatible documents whose cosine scores are between basic and strict thresholds.
## Outputs
Local fallback raises RuntimeError when LLM is requested and unavailable.
## SQL
None.
