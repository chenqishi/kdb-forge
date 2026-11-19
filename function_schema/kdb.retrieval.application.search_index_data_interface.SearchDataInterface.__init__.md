# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.__init__

## Signature

`SearchDataInterface.__init__(self, search_engine: SearchEngine=None, config_path: str=None, **kwargs)`

## Inputs

参数以签名为准。

## Outputs

初始化接口
Args:
    search_engine: 实现了基本检索操作的搜索引擎实例

## SQL / ES

无新增SQL；ES字段及更新由conflict_store/原引擎契约管理，任务原SQL表不变。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`
