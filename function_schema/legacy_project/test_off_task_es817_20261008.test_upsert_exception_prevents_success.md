# test_upsert_exception_prevents_success

Inputs: actual CLI/batch and ES boundary raises update exception. Outputs: controller nonzero/failure, batch failure statistic and no success. SQL/side effects: offline captured write/exception only.
