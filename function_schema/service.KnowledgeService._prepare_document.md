# KnowledgeService._prepare_document

## Inputs
Mutable document, optional index_name.
## Outputs
Prepared document. Merge retains audit_result=2; truthy invalid audit values and
non-string from_type are normalized for both new and existing IDs. New-document
defaults remain guarded by absence of _id. Keyword/from_type_norm runtime errors
propagate to insert_data's existing processing-failure response. Empty index text
filtering, generic category defaults and ES8 vector preparation stay unchanged.
## SQL
None; embedding and explicit category lookup only.
