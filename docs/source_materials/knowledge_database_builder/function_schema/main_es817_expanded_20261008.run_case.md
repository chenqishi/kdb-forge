# run_case

Inputs: one saved real text/category case and fixed cached query embedding; real engine context. Outputs: actual search_multi with dual mode,size10 (eachindex/route5), merge and exact business QA/synonym rerank formula. Metrics/candidate IDs, field/dimension/soft-delete/category checks, final top5 IDs/scores; no raw text/embedding/source saved. Fail missing routes/errors instead of accepting engine fallback silently. SQL/side effects: four bounded ES search reads normally, read-only.
