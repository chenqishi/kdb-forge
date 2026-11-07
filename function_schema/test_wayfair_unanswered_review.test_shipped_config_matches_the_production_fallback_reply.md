# test_shipped_config_matches_the_production_fallback_reply

Locations: tests/test_wayfair_unanswered_review.py and its unchanged-logic baseline_legacy copy.

Inputs: existing shipped fallback config; fixture reply text. Only the customer/team contact literal in that reply is replaced by synthetic support@example.invalid; no production config or matching logic is changed.
Outputs: original assertions still require the same fallback classification; platform-specific test retains Wayfair positive, Mercado negative, and Mercado positive checks. Assertions and other fixture content remain unchanged.
SQL/external operations: none. Pure offline pytest under network/SQL/ES/LLM guard. Original files preserved in private remediation snapshots; values never included in metadata.
