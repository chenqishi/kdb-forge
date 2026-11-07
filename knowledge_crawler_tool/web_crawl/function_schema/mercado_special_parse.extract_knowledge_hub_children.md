# extract_knowledge_hub_children

## 所属文件
`mercado_special_parse.py` - 模块级函数

## 功能
从 Mercado Livre knowledge-hub 页面的 HTML 中提取嵌入式前端状态 JSON 里的子页面 URL。

## Inputs
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| html_content | str | 是 | HTML 页面原始内容 |
| current_url | str | 是 | 当前页面 URL，需匹配 knowledge-hub pattern 才会执行提取 |

## Outputs
| 类型 | 说明 |
|------|------|
| list[dict] | 子页面信息列表，每项含 `url`（完整 URL）和 `title`（标题，可能为空） |

## 逻辑说明
1. 通过 `is_knowledge_hub_url` 判断 URL 是否匹配 knowledge-hub pattern
2. 在 HTML 中正则查找 `children_data` 数组
3. 优先尝试同时提取 id + title；若失败则退化为仅提取 id
4. 将 id 拼接到 base URL `{scheme}://{netloc}/knowledge-hub/{id}` 形成完整子页面 URL

## 依赖
无外部依赖，仅使用 `re`、`logging`、`urllib.parse`
