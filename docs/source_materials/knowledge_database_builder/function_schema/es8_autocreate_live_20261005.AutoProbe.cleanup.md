# AutoProbe.cleanup

## Inputs / Outputs
Before deleting exact approved index validate captured UUID, empty aliases, at most approved source-probe doc with synthetic owner, private B empty. Require delete acknowledgement and independent404. Preserve unknown/foreign state.

## SQL
None.

## Serverless identity
Use UUID stats fallback when metadata masks uuid. Validate creation_date only if exposed; ownership rests on recorded before-absence, known create/API action, UUID and exact fixture document/alias guards. Public fixture _meta owner required. Never replace stored expected UUID before comparison during cleanup.
