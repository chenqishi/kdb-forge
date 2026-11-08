# kdb.mining.document.maintenance.repair_images.remap_parsed_images

## Signature

`remap_parsed_images(parsed_json, md5_map)`

## Purpose

把重新解析得到的 `{page: [item]}` 结构中的 image item，按内容 md5 替换成
已有的多模态结果（`public_url` / `s3_path` / `image_understanding` / `image_ocr` /
`is_valid*` 等），保留新解析的正确页归属与新的 `image_path` / `fileName`。

## Inputs

- `parsed_json` (dict): 重解析产物，`{页码字符串: [item]}`。
- `md5_map` (dict): `build_image_md5_map` 的输出。

## Outputs

- `tuple[dict, dict]`:
  - 新的 `{page: [item]}`，image item 已补齐多模态字段；
  - 统计 `{'images': 总图数, 'matched': 命中且有多模态结果, 'matched_no_mm': 命中但旧数据本来就没多模态结果,
    'missed': 旧数据里找不到该 md5, 'missed_files': [...]}`。

`matched_no_mm` 不是问题：多模态阶段会把 logo/装饰类小图判为无效，不上传也不做理解，
这类图在旧解析里 `public_url` 就是空的。只有 `missed` 才代表新解析出了旧解析没有的图。

未命中的图片保留原样（`public_url=None`），下游会当作无公网图处理，不会中断。

## SQL

No SQL access.

## Source

`src/kdb/mining/document/maintenance/repair_images.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
