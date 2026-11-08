# kdb.mining.common.generation.long_qa.build_page_chunks

## Signature

`build_page_chunks(data_json, max_chars=SEGMENT_MAX_CHARS, max_pages=SEGMENT_MAX_PAGES, use_image_content=0)`

## Description

按页边界把解析后的文档 JSON 切成提交给 Dify 分段模型的硬窗口，避免一次传入整篇长文超过 Dify `paragraph` 长度限制。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| data_json | dict | 是 | PDF/DOCX 解析后的页内容字典，key 为页码字符串，value 为页面元素列表 |
| max_chars | int | 否 | 单个硬窗口最大字符数，默认 80000 |
| max_pages | int | 否 | 单个硬窗口最大页数，默认 40 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 每项格式为 `{"pages": [start_page, end_page]}`，只按整页切分 |

## 行为约束

- 只使用文本内容计算分段输入长度，调用 `merge_segment_content(..., need_add_page_num=True, use_image_content=0)`。
- 不拆单页；若单页超过 `max_chars`，记录 warning 并保留为单页窗口。
- 保持页码顺序，输出窗口不重叠、不跳页。

## SQL

不读写数据库。

## Source

`src/kdb/mining/common/generation/long_qa.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
