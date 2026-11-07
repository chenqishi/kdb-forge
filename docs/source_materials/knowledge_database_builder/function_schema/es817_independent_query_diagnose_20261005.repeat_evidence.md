# repeat_evidence

Repeat exactly the five completed segment requests whose top1 changed, once per service (ten sequential HTTP queries), after exact ten-index HEAD preflight using guarded raw clients. No arbitrary request/index/body construction. Compare repeated IDs/order to initial per service and between services using pure compare; save only IDs/scores/status/time, no original content. Fail HTTP200 error sentinel. No mutations or implementation change.

SQL: none.
