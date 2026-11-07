# excel_qa_segment_upload_control._jsonl_has_ori_image_path

## 描述
扫描结构化 Excel 转换后的 JSON Lines 文件，判断是否存在非空 `ori_image_path` 字段，用于决定是否进入结构化图片理解阶段。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| data_file | str | 是 | JSON Lines 文件路径 |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 任意有效 JSON 行存在非空 `ori_image_path` 时返回 True；文件不存在、字段为空或解析异常时返回 False |

## 逻辑

1. 校验文件路径存在。
2. 逐行读取 JSON Lines，跳过空行和无法解析的行。
3. 发现非空 `ori_image_path` 即返回 True。
4. 扫描结束或异常时返回 False，并记录 warning。

## SQL
无。
