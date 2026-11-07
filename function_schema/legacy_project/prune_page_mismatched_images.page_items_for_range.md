# page_items_for_range

## 所属文件
`data_control_tools/prune_page_mismatched_images.py`

## 功能描述
取页码区间内**上传过**（有 `s3_path`）的正确图，按页号、再按 `fileName` 排序，同一张图只取一个地址。
用于「话术指着的图被裁光了，而该页确实有图」时把正确的图挂回去。

## Inputs
- `per_page` (Dict[int, List[Dict]]) — `build_page_image_index` 里某个文件的页→图
- `page_range` (Tuple[int,int]) — 闭区间，允许反序

## Outputs
`List[Dict]` — 每项带 `md5` / `s3_path` / `public_url` / `fileName` / `image_ocr`。

## 为什么要过滤 s3_path
修复版解析里有一部分图 `s3_path` 为空——多模态阶段判为无效、从未上传的 logo/装饰图
（508b09ae 实测 457 个图 item 里只有 227 个有 s3_path）。它们不会出现在 ES 正文里，
判「属于本页」时要计入 md5 集合，但**不能**挂回去（没有地址可挂）。

## SQL
无。

## 测试
`tests/test_prune_page_mismatched_images.py`
