# kdb.integrations.data_control.prune_page_mismatched_images.page_items_for_range

## Signature

`page_items_for_range(per_page: Dict[int, List[Dict[str, Any]]], page_range: Tuple[int, int]) -> List[Dict[str, Any]]`

## Description

取页码区间内**上传过**（有 `s3_path`）的正确图，按页号、再按 `fileName` 排序，同一张图只取一个地址。
用于「话术指着的图被裁光了，而该页确实有图」时把正确的图挂回去。

## Inputs

- `per_page` (Dict[int, List[Dict]]) — `build_page_image_index` 里某个文件的页→图
- `page_range` (Tuple[int,int]) — 闭区间，允许反序

## Outputs

`List[Dict]` — 每项带 `md5` / `s3_path` / `public_url` / `fileName` / `image_ocr`。

## 为什么要过滤 s3_path

修复版解析里有一部分图 `s3_path` 为空——多模态阶段判为无效、从未上传的 logo/装饰图
判「属于本页」时要计入 md5 集合，但**不能**挂回去（没有地址可挂）。

## SQL

无。

## 测试

`tests/test_prune_page_mismatched_images.py`

## Source

`src/kdb/integrations/data_control/prune_page_mismatched_images.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
