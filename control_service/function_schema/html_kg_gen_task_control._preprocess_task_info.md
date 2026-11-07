# _preprocess_task_info

## 所属文件
`html_kg_gen_task_control.py` - `HtmlKgGenTaskController` 类方法

## 功能
预处理 task_info，补齐类目信息（category_name / category_id），并为缺少 `keep_attr_name` 的 url_info 设置默认值 `"all"`。

## Inputs
无显式参数，使用 `self.task_info` 字典：
| 字段 | 类型 | 说明 |
|------|------|------|
| client | str | 客户端名称，用于获取类目树 |
| url_infos | list[dict] | URL 信息列表，每项可包含 category_name、category_id、keep_attr_name 等 |

## Outputs
无返回值，就地修改 `self.task_info` 中的 `url_infos`。

## 逻辑说明
1. 根据 `client` 获取类目树，构建 name↔id 双向映射
2. 补齐 `task_info` 顶层的 category_name / category_id
3. 遍历 `url_infos`，对每个 url_info：
   - 补齐 category_name / category_id
   - 若 `keep_attr_name` 不存在，默认设为 `"all"`
