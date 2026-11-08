# kdb.mining.common.schema.review_import.trans_web_excel_to_json_file

## Signature

`trans_web_excel_to_json_file(excel_file: str, output_file: str, list_field_names: Union[str, List[str]]=None, image_save_dir: str=None, extra_field_name_dict: Dict[str, Any]=None)`

## Inputs

审核 Excel、输出路径、图片目录、列表字段名和外部补充字段，见签名。

## Outputs

按原表头映射与类目补全规则生成 JSONL；保留图片处理、字段优先级及异常。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/common/schema/review_import.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
