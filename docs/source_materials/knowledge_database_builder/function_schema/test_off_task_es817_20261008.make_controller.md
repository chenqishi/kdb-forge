# make_controller

Inputs: actual controller class module, fresh tmp directories, index/row. Outputs: real class instance via __new__, initialized only needed stage fields and offline status boundary; does not run generation constructor side effects. Invoke actual config selection/insert stage/subprocess wrapper, no engine mocking. SQL/side effects: tmp JSONL/log files only.
