# run

Inputs: raw clients, new directory, prepared <=105 cases. Outputs: progressively persisted exact paired replies/checks/source cache/native counts, final statistics and unchanged implementation hashes. Alternate old/new request order sequentially with pacing, no silent retry or skipped failures. Re-HEAD original request indexes before service requests; HTTP read endpoints only. Previous 148-case artifacts never overwritten. Small textless membership pools may be fetched fully only if exact count<=30. Close all HTTP sessions. SQL: none.
