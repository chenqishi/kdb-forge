# prepare

Inputs: unchanged existing ES8 provider config and two historical positive category requests for mercado_local/payoneer_olive from the saved 20261008 matrix.
Outputs: build the actual current old-project ES8 BM25/native-KNN query using the real builder, five hits per route and full source. Generate only two query embeddings locally, reuse them for both locations. Return in-memory connection information and four bounded requests; never print/save credentials or vectors. Reuse exact-index read_es to HEAD existing targets locally. Record query/source fingerprints.
SQL/side effects: no SQL or ES writes; two existing embedding calls, no LLM. No engine construction/ensure or configuration mutation.
