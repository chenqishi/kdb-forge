# excel_qa_segment_upload_control.stage_2_5_process_images

## 描述
结构化 Excel 上传的图片理解阶段。仅在 `standard_qa` / `mapped_qa` 路径且 JSONL 中存在 `ori_image_path` 时执行图片理解；否则跳过并保持原 JSONL 作为入库文件。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| self.excel_process_mode | str | 是 | Excel 路由模式 |
| self.json_file_path | str | 是 | 结构化 Excel 转换出的 JSON Lines 文件 |
| self.image_processed_json_file_path | str | 是 | 图片理解后 JSON Lines 输出路径 |
| self.log_dir | str | 是 | 图片理解 stderr 日志目录 |
| GLOBAL_CONFIG.dify_api_key_mluti_vision_forward_nomix | str | 否 | 图片理解 Dify API key，缺省使用旧脚本默认值 |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 阶段跳过或图片理解成功返回 True，执行失败返回 False |

## 逻辑

1. `unstructured_excel` 路径跳过。
2. 调用 `_jsonl_has_ori_image_path` 判断是否需要图片理解。
3. 使用 argv list + `shell=False` 调用 `commons/image_data_tools.py process_search_data_image_file`，避免路径空格问题。
4. 将 stdout 写入 `image_processed_json_file_path`，stderr 写入 `excel_image_process.log`。
5. 成功后将 `index_input_file_path` 切换到图片理解输出文件。

## SQL
无。
