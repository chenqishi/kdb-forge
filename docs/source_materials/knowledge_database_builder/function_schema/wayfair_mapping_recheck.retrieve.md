# wayfair_mapping_recheck.retrieve

## Inputs and boundary
User requests a fresh rerun excluding old knowledge during retrieval. Preserve previous 120 samples (116 substantive, 4 invalid historical answers), 42 old files / 46 mappings. Read-only live ES candidate pool: del_flag=0 AND task_id.keyword in confirmed 8 update tasks + earlier 64 new-file task AND must_not ext_info.flag.keyword=wayfair_update_20260922_old. Also assert no candidate ID overlaps the original 1290 old-flag sample-pool IDs. No SQL or production mutations. Time fields are diagnostics, not the sole freshness criterion because upsert may refresh an existing record.

## Functions
`norm(text)` strips whitespace/lowercases only; `terms(text)` returns character bigrams and ASCII words; `rank(query)` returns local TF-IDF candidates from the strictly filtered pool. Scores retrieve candidates, never decide replacement. `md(text)` formats report tables. Do not invoke an external model or production audit.

## Outputs and validation
New output/wayfair_mapping_recheck_20260923 folder, preserving prior artifacts. Live exported candidate records, server filter/count reconciliation and timestamps; reretrieval for all 120 fixed samples; previous support checked for exact title/content/type/file equality and pool membership. Manually assess changed/uncovered cases, including formerly self-only/old-candidate overlap. Any supporting evidence in the final recheck must exist in the clean pool. Formal audit, flags and deletion stay untouched.

## Additional evidence validity check
Read source-segment archive declarations for cited files, even if filenames lack `(Archived)`. This rerun discovered explicit archive declarations in Supplier Transfer_供应商直联买家客服计划简介 and 如何使用管理新产品提交 (Manage Product Submissions)工具. Do not count their text matches as current valid replacements. Final report differentiates content candidates, changed/partial evidence, and valid independent coverage; old-flag exclusion applies even to diagnostic final citations. Final assertions inspect every reretrieval candidate and every selected citation, not only summary counts.
