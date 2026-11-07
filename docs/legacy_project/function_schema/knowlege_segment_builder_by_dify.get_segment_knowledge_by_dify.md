# knowlege_segment_builder_by_dify.get_segment_knowledge_by_dify

## 描述
获取分段知识库。对 PDF JSON 文件进行分段并通过 dify 获取索引信息。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| pdf_json_file | str | 是 | PDF JSON 文件路径 |
| dify_segment | DifyWorkFlowRequest | 是 | 分段 dify 请求实例 |
| dify_index | DifyWorkFlowRequest | 是 | 索引 dify 请求实例 |
| from_file_name | str | 是 | 来源文件名 |
| platform | str | 否 | 平台名称 |
| use_image_content | int | 否 | 是否使用图片内容，默认0 |

## Outputs

| 类型 | 说明 |
|------|------|
| List[Dict] | 段落信息列表，每个包含 keywords, phrases, topics, content, from_file_name, index_file_name, pages |

## 逻辑

1. 加载 PDF JSON，合并所有页面内容用于判断是否需要分段
2. 若内容 < 2000 字符：直接调用 dify_index 获取索引 → 返回
3. 若内容 >= 2000 字符：
   a. 先用 `build_page_chunks` 按页边界生成硬窗口，默认每个窗口不超过 40 页 / 80000 字符
   b. 对每个硬窗口调用 dify_segment，使用 `normalize_segments_in_chunk` 将返回页码限制在当前窗口内
   c. 若当前硬窗口分段异常或无有效结果，使用 `fallback_page_segments` 在当前窗口内按固定页数兜底，不回退到整篇文档
   d. 若 Dify 返回了部分有效分段但漏页，使用 `fill_uncovered_segments_in_chunk` 对未覆盖页按固定页数补段
   e. 对每个语义段调用 dify_index 前，使用 `split_segment_for_qa` 再限制为默认不超过 10 页 / 30000 字符
   f. dify_index 返回为空时跳过该子段，其他子段继续处理
4. 每个硬窗口分段和每个索引子段都会输出 warning 级进度日志，便于线上观察长任务卡点
5. 添加 platform 信息并返回

## 依赖函数

- `merge_segment_content(data_json, segment, ...)` — 合并指定页面范围文本
- `parse_dify_segment(segment_answer)` — 解析 dify 分段结果
- `build_page_chunks(data_json, max_chars, max_pages)` — 按页边界生成硬窗口
- `normalize_segments_in_chunk(segments, hard_chunk)` — 限制 Dify 返回页码不越过硬窗口
- `fallback_page_segments(hard_chunk)` — 分段失败时按固定页数生成兜底段
- `fill_uncovered_segments_in_chunk(segments, hard_chunk)` — Dify 部分分段漏页时补齐未覆盖页
- `split_segment_for_qa(data_json, segment, ...)` — 调用 index 模型前再次按页/长度限制输入
- `parse_index_answer(answer, from_file_name, pages, data_json)` — 解析索引答案
- `DifyWorkFlowRequest.request_dify(content)` — 调用 dify 工作流

## SQL

No SQL access.

## 空段落与单段异常的处理（2026-09-02 补）

调用 `dify_index.request_dify` 前必须先判空：只有图片、没有文字的页会被切出
`chars=0` 的段，而 `dify_tools.request_dify` 对空 paragraph 直接
`raise ValueError("inputs is empt")`。历史上这条异常会一路穿透到 `fire.Fire`，
把整批任务打死（wayfair 任务 74256b78 第二次重跑即因此在第 7 个文件处全批阵亡）。

现在的行为：

- `segment_content` 为空或全空白 → 记 warning 并跳过，不请求 Dify
- 单个子段请求抛异常 → 记 error 并跳过该子段，其余子段继续
- 短文档分支（整篇 < 2000 字符）内容为空时直接返回 `[]`

## SQL

No SQL access.
