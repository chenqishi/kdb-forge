# kdb.retrieval.ingestion.writes.insert_data

## Signature

`insert_data(self, data: Dict[str, Any], check_duplicate: bool=None, index_name: str=None, is_update_data: bool=False, is_only_title: bool=False, basic_threshold: float=0.7, title_basic_threshold: float=0.95, refresh_imm: bool=False, is_need_llm: bool=None) -> bool`

## Inputs

data、可选 check_duplicate、index_name、is_update_data、is_only_title、阈值、refresh_imm、is_need_llm；实际默认值见签名。

## Outputs

实际返回 (success, message)。在处理副本前，若调用方 data 的 _id 非 truthy，会把原 data 的 _id 设为当时值（可能为 None）；其余处理在 deepcopy 上执行。process_one_data 失败返回 False/数据处理失败；重复且不覆盖时返回 False/数据重复。允许覆盖时先软删重复；软删失败只记录后仍尝试写入，最终返回引擎写入结果。

## SQL

无直接 SQL；embedding/类目/查重经当前配置接口，ES 软删重复记录并插入目标 index。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.insert_data`

## Source

`src/kdb/retrieval/ingestion/writes.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
