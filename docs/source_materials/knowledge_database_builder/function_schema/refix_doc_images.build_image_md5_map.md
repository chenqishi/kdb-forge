# refix_doc_images.build_image_md5_map

## Purpose

从任务的 `multimodal_data_info.json` 建立「图片内容 md5 → 多模态条目」映射，
用于把已完成的图片理解/OCR/公网 URL 结果按内容复用到重新解析出的图片上，
避免重跑 VLM 与重复上传。

前提（已实测）：修复版 `parse_pdf_to_json` 走 `_extract_rendered_pdf_images`
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
否则会被误报成"未命中"。实测该任务 939 张唯一图里只有 503 张有 `public_url`。

`refix_task_documents` 的查表顺序：单文件映射优先，全局表兜底。
