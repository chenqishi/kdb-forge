# export_local_qa_result

## 所属文件
`knowledge_crawler_tool/web_crawl/single_page_local_crawl.py`

## 功能
把 `quality_tools/qa_quality_tools.py run_batch_re_clear_qa_info` 产出的
`*_qa_quality_re_clear.json`（`{high, mid, low}` 分档字典）拍平成人工可读的
QA 清单与统计 manifest，供本地审核，不入 ES。

## Inputs
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| reclear_map_file | str | 是 | - | `web_crawler_reclear_qa_<flag>.txt`，每行最后一列是 `_re_clear.json` 路径 |
| output_dir | str | 是 | - | 产物目录 |
| flag | str | 否 | `'local'` | 产物文件名后缀 |
| source_url | str | 否 | `''` | 写入 manifest 的来源 URL；为空则取 TSV 第 1 列 |

## Outputs
| 类型 | 说明 |
|------|------|
| dict | `{'qa_result_file': str, 'manifest_file': str, 'qa_count_by_level': dict, 'qa_total': int}` |

落盘文件：

- `qa_result_<flag>.json` — JSON 数组，每项
  `{quality_level, q, a, from_file_name, quality_info, category_name, original_url}`，
  按 `high → mid → low` 排序
- `manifest_<flag>.json` — `{source_url, generated_at, pages, qa_count_by_level, qa_total, files{...},
  char_stats{html_bytes, formatted_text_chars, firecrawl_chars, translated_chars}}`

## 逻辑说明
1. 逐行读 TSV，取 `fields[-1]` 作 `_re_clear.json`，`fields[1]` 作 crawl_url
2. 按 `high/mid/low` 顺序展开每档 QA 列表，逐条取 `q/a/from_file_name/quality_info/category_name/original_url`
3. 字数统计回溯同一行的页面 JSON（TSV 第 5 列 `<slug>.json`）与其 `_trans.json`（若存在），
   分别统计 `html_content` / `formatted_text` / `firecrawl_content` / `translated_text` 长度
4. 写两个 JSON，返回统计字典

## SQL
无。
