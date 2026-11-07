# load_sources

Inputs: exact current engine/router/count module source in encrypted stdin and extracted rerank/oracle/snapshot definitions. Outputs: isolated in-memory module namespace only, no sys.path import of service engine or old engine; logging disabled to avoid source text exposure. SQL/side effects: no files/install/deploy/service changes.
