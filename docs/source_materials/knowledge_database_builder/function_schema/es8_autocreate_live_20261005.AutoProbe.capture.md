# AutoProbe.capture

## Inputs / Outputs
Claim only an index observed absent by this execution; require UUID, no aliases, recent creation time. Capture B after actual automatic creation; no takeover of existing index.

## SQL
None.

## Serverless identity
Use UUID stats fallback when metadata masks uuid. Validate creation_date only if exposed; ownership rests on recorded before-absence, known create/API action, UUID and exact fixture document/alias guards. Public fixture _meta owner required. Never replace stored expected UUID before comparison during cleanup.
