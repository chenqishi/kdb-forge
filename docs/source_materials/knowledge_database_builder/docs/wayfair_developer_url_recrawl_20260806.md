# Wayfair Developer URL Recrawl 2026-08-06

## Source

Excel workbook:

`/Users/chenqishi/Documents/笔记本地/大模型项目鱼爷/wayfair/官方资料/待爬取知识/开发者门户上传260805.xlsx`

The workbook has one sheet and 26 hyperlinks stored as cell hyperlink targets. The visible cells are labels such as `1. Introduction`, `Graph QL`, and API guide names.

Extracted URL list and reports:

- `output/wayfair_url_recrawl_20260806/developer_urls_260805.json`
- `output/wayfair_url_recrawl_20260806/wayfair_developer_urls_soft_delete_report.json`
- `output/wayfair_url_recrawl_20260806/wayfair_developer_urls_soft_delete_counts.csv`
- `output/wayfair_url_recrawl_20260806/wayfair_developer_urls_recrawl_payload.json`

## Chinese URL Check

> **⚠️ 本节结论已于 2026-08-07 被推翻，勿再据此判断。**
>
> 「没有中文 URL」是对的，但「拿不到中文」是错的。语言由 cookie `DEV-PORTAL-LANGUAGE=zh-CN`
> 控制、URL 不变；而正文可以直接从门户的内容 BFF
> （`POST https://api.wayfair.io/content/v1/developer-portal-bff/graphql`，免鉴权）按 locale 取到
> **官方中文**，26/26 全部有中文版，根本不需要机器翻译。
>
> 详见 `docs/wayfair_developer_zh_content_20260807.md`；抓取脚本
> `knowledge_crawler_tool/web_crawl/wayfair_developer_portal_fetch.py`；
> 官方中文 HTML 已落在 `data/wayfair/html/`。
>
> 教训：对这类 SPA 站点，用「试 URL 变体 + 看返回 HTML 骨架里有没有中文」来判断有没有多语言，
> 必然得出错误结论 —— 骨架里本来就没有正文。应当去读前端 bundle，
> 找它到底向哪个接口、用什么参数取正文。

以下为当时（2026-08-06）的原始记录：

Sample developer pages returned HTML with `lang=en-us` and no `hreflang`, `zh`, `中文`, `简体`, or language-switch links.

Tried common variants for `https://developer.wayfair.io/posts/introduction`:

- `/zh-cn/posts/introduction`: `404`
- `/cn/posts/introduction`: `404`
- `/zh/posts/introduction`: `404`
- `?locale=zh-CN`: still English (`lang=en-us`)
- `?language=zh-CN`: still English (`lang=en-us`)
- `?lang=zh-CN`: still English (`lang=en-us`)

Conclusion: no usable Chinese URL method was found, so the recrawl task sets `is_need_translated=true`.

## Soft Delete

Target index/client: `wayfair`

Exact ES source field: `ext_info.from_file_name.keyword`

Run flag: `20260806`

Results:

- URL count: `26`
- URLs with active old knowledge before delete: `15`
- Active old docs before delete: `303`
- ES `update_by_query`: `303` updated, `0` failures
- Corrected post-verification:
  - total docs all del flags: `358`
  - remaining `del_flag=0`: `0`
  - `del_flag=1`: `358`
  - `del_flag=1 AND flag=20260806`: `303`

No MySQL file-task update was performed for these URL sources: historical HTML crawl tasks live in `rufitai.dops_task_kggen_info`, which has no `del_flag`, and the table is task-level rather than URL-level.

## Personal Index Follow-Up

User noted old URL knowledge also existed in the personal index `wayfair_wayfair_test2`.

Follow-up exact URL soft delete:

- Target index: `wayfair_wayfair_test2`
- URL count: `26`
- Active old docs before delete: `88`
- ES `update_by_query`: `88` updated
- Post-verification:
  - remaining `del_flag=0`: `0`
  - `del_flag=1`: `88`
  - `del_flag=1 AND flag=20260806`: `88`

Report artifacts:

- `output/wayfair_url_recrawl_20260806/wayfair_test2_dryrun/wayfair_soft_delete_20260806_174031.json`
- `output/wayfair_url_recrawl_20260806/wayfair_test2_execute/wayfair_soft_delete_20260806_174048.json`

## Recrawl Task

Submitted to task service:

`http://120.77.147.247:6000/start_task`

Task:

- `task_id`: `1f47a2e7cff6defe869fe1280ec7a8b1`
- `task_type`: `html_qa_segment_mining`
- `client`: `wayfair`
- `user`: `wayfair_test2`
- `index_name`: `wayfair`
- `url_infos`: `26`
- `crawler_degree`: `1`
- `limit_page_num`: `1`
- `is_use_firecrawl`: `true`
- `is_need_translated`: `true`
- `category_name`: `默认分组`
- `category_id`: `1`

Initial status after submission:

- `run_status`: `2`
- `task_stage`: `url_crawl`
- `/health`: one active task, queue size `0`

Follow-up status after personal-index soft delete:

- `run_status`: `2`
- `task_stage`: `segment_generation`

## Task Knowledge Cleanup 2026-08-08

Reason: the 2026-08-06 crawl used the old English + translation path. The crawl plan is being replaced with the newer Chinese content/firecrawl-cookie approach, so knowledge produced by this task was soft-deleted.

Task status before cleanup:

- `task_id`: `1f47a2e7cff6defe869fe1280ec7a8b1`
- `run_status`: `3`
- `task_stage`: `运行完成`
- `task_result.qa_num`: `991`

Soft delete target:

- Query key: `task_id.keyword = 1f47a2e7cff6defe869fe1280ec7a8b1`
- ES flag: `20260808`
- MySQL: no row update; this is URL/html task knowledge, and `dops_task_kggen_info` has no `del_flag`.

Verification:

- `wayfair`
  - before active docs: `1082`
  - deleted docs: `1082`
  - remaining `del_flag=0`: `0`
  - `del_flag=1 AND flag=20260808`: `1082`
  - by type: `qa=965`, `segment=117`
- `wayfair_wayfair_test2`
  - task-id matches: `0`
  - remaining `del_flag=0`: `0`

Execution note: the first `update_by_query` used `scroll_size=100` and hit Aliyun ES Serverless `MAX_WRITE_SIZE_PER_REQUEST` after committing `600` docs. A retry with `scroll_size=10` updated the remaining `482` docs. Always inspect the response body for `error`, not only HTTP/client success.

Report artifacts:

- `output/wayfair_url_recrawl_20260806/delete_task_1f47a2e7_20260808_final_report.json`
- `output/wayfair_url_recrawl_20260806/delete_task_1f47a2e7_20260808_retry_scroll10.json`
