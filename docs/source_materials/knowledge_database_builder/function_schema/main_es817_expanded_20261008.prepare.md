# prepare

Inputs: existing ES8 config only; 12 saved Local/Olive historical/title queries and 25 saved search/category cases. Outputs: 37 in-memory cases over unchanged public/private physical indices, 24 cached query vectors generated in batches of at most 8 by existing AliEmbedding, actual ES8/router/count modules and unchanged business rerank methods. Source/query fingerprints only saved. SQL/side effects: no old ES client, no ES preparation writes/reads, local embedding calls only; disable index ensure and mapping mutation in a copied in-memory config.
