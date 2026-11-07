# run

## Inputs
Actual isolated old/new API model classes, safe request matrix.

## Outputs
Import actual old and new request models without service lifespan/client construction; evaluate identical valid/invalid HTTP JSON payloads, normalize local dates for comparison, empty names equivalent, compare defaults/alias preservation/rejections. Output sanitized mismatches only. No ES/service requests.

## SQL
None; no database I/O.
