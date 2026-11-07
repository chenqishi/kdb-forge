# extract_functions

Inputs: Python source and exact named functions/methods. Outputs: AST-extracted unchanged function bodies, error when a requested name is missing; used for prior snapshot, membership oracle and existing rerank methods. SQL/side effects: source parsing only; never mutate implementation.
