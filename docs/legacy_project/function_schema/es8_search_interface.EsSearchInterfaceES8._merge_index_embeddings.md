# EsSearchInterfaceES8._merge_index_embeddings

## Inputs
同一文档两条 BM25/native KNN 结果。
## Outputs
无返回；分别按indexes/image_indexes的text补齐缺失embedding，不覆盖已有值，不串文本和图片数组。没有可确定text映射就不猜测对应关系，保留现存数组/metadata。
## SQL
无。
