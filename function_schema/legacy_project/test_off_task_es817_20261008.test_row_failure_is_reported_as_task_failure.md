# test_row_failure_is_reported_as_task_failure

Inputs: controller+actual Fire/batch+external embedding boundary TimeoutError. Outputs expected: stage False when insert_failure_num>0 and no ES update attempted; preserve actual counterexample as strict xfail, not green equivalence. Use realistic preprocessing failure rather than inventing an ES update result enum. SQL/side effects: no real model/ES call.
