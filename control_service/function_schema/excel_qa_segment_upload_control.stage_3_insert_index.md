# excel_qa_segment_upload_control.stage_3_insert_index

## 描述
将结构化 Excel 路径产出的 JSON Lines 文件插入搜索索引。入库文件由 `index_input_file_path` 决定：可能是 Excel 转换输出，也可能是图片理解后的输出。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| self.index_input_file_path | str | 是 | 当前入库 JSON Lines 文件 |
| self.index_name | str | 是 | 目标索引名 |
| self.script_dir | str | 是 | 项目脚本目录 |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 入库命令成功返回 True；文件/配置缺失或命令失败返回 False |

## 逻辑

1. 更新任务阶段为 `index_insert`。
2. 校验 `index_input_file_path` 存在。
3. 调用 `_get_index_config_path()` 获取索引配置。
4. 使用 argv list + `shell=False` 经 `_run_command` 执行 `search_index_data_interface.py insert_data_to_search_index`。

## SQL
无直接 SQL；入库命令内部按搜索索引接口逻辑处理。
