# kdb.integrations.data_control.refix_doc_images.build_image_md5_map

## Signature

`build_image_md5_map(multimodal_data_info_path)`

## Purpose

从任务的 `multimodal_data_info.json` 建立「图片内容 md5 → 多模态条目」映射，
用于把已完成的图片理解/OCR/公网 URL 结果按内容复用到重新解析出的图片上，
避免重跑 VLM 与重复上传。

产出的图片字节与旧版 `_extract_pdf_resource_images` 完全一致，故可按 md5 对齐。

## Inputs

- `multimodal_data_info_path` (str): 任务目录下 `multimodal_data_info.json` 路径。
  该文件是 `{public_url: item}`，item 结构与 `content_multimodal.json` 的 image item 相同。

## Outputs

- `dict[str, dict]`: `{图片文件内容 md5: 多模态 item}`。
  同一 md5 出现多次时保留第一条（内容相同，结果等价）。
  `image_path` 指向的本地文件不存在时跳过该条并计数。

## SQL

No SQL access.

## 同模块 build_file_md5_map

`build_file_md5_map(old_parsed_json) -> dict[str, dict]`

从单个文件**自己**的旧解析产物（`content_multimodal.json`）建 md5 映射。
比全局 `multimodal_data_info.json` 更全：后者只收录上传成功的图，
而被多模态阶段判为无效（`public_url` 为空）的图也必须能对上，

`refix_task_documents` 的查表顺序：单文件映射优先，全局表兜底。

## Source

`src/kdb/integrations/data_control/refix_doc_images.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
