# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.insert_data

## Signature

`SearchDataInterface.insert_data(self, data: Dict[str, Any], check_duplicate: bool=None, index_name: str=None, is_update_data: bool=False, is_only_title: bool=False, basic_threshold: float=0.7, title_basic_threshold: float=0.95, refresh_imm: bool=False, is_need_llm: bool=None) -> bool`

## Inputs

data、可选 check_duplicate、index_name、is_update_data、is_only_title、阈值、refresh_imm、is_need_llm；实际默认值见签名。

## Outputs

实际返回 (success, message)。在处理副本前，若调用方 data 的 _id 非 truthy，会把原 data 的 _id 设为当时值（可能为 None）；其余处理在 deepcopy 上执行。process_one_data 失败返回 False/数据处理失败；重复且不覆盖时返回 False/数据重复。允许覆盖时先软删重复；软删失败只记录后仍尝试写入，最终返回引擎写入结果。

## SQL

无直接 SQL；embedding/类目/查重经当前配置接口，ES 软删重复记录并插入目标 index。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。所列 SQL 表字段来自此实现的参数化查询；未取得额外 DDL，不宣称完整表结构已核验。
