# Mercado Mexico Help Crawl Task

## When To Use

Use this note when submitting a MercadoLibre Mexico help-center crawl into the async task service on the `main` machine.

## Verification

Before starting the crawl on 2026-07-15, `https://www.mercadolibre.com.mx/ayuda` was checked with and without the provided logged-in cookie.

- Final URL stayed on `https://www.mercadolibre.com.mx/ayuda`.
- Page bootstrap markers contained `siteId=MLM`, `countryId=MX`, and `mercadolibre.com.mx`.
- Brazil markers such as `MLB` and `mercadolivre.com.br` were absent.
- With the logged-in cookie, the response was private/no-store and contained the account user id, so the cookie was participating in the request.

Conclusion: the page content is Mexico (`MLM/MX`). Use `auth_config.cookie` for crawls that must preserve the same account/site context.

## Task Service

The control service is on:

```bash
http://120.77.147.247:6000
```

Health check:

```bash
curl -sS http://120.77.147.247:6000/health
```

Submit an HTML crawl through:

```bash
POST /start_task
```

Use `task_type=html_qa_segment_mining`.

## Payload Shape

Keep secrets out of committed files. Put the cookie only in the live request payload.

```json
{
  "task_type": "html_qa_segment_mining",
  "task_info": {
    "url_infos": [
      {
        "url": "https://www.mercadolibre.com.mx/ayuda",
        "content_type": "normal",
        "crawler_degree": 2,
        "keywords": "ayuda",
        "keep_attr_name": "all",
        "limit_page_num": 500,
        "category_name": "运营问题类型-客服与系统"
      }
    ],
    "client": "mercado",
    "user": "test_mercado_stone",
    "index_name": "mercado_test_mercado_stone",
    "is_use_firecrawl": true,
    "is_need_translated": true,
    "auth_config": {
      "cookie": "<runtime cookie only>",
      "user_agent": "Mozilla/5.0 ..."
    }
  }
}
```

Important: `knowledge_crawler_tool/web_crawl/web_batch_crawler.py` reads `limit_page_num`, not the older `limit_page_numbs` spelling. If copying old payloads, include or replace with `limit_page_num`.

## Submitted Task

On 2026-07-15, the Mexico help-center crawl was submitted with the logged-in cookie.

- `task_id`: `7bf859ed93bae7c915dd41dd57265769`
- `client`: `mercado`
- `user`: `test_mercado_stone`
- `index_name`: `mercado_test_mercado_stone`
- root URL: `https://www.mercadolibre.com.mx/ayuda`
- task status after submission: `url_crawl`

Check status:

```bash
curl -sS -X POST http://120.77.147.247:6000/task_info \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"7bf859ed93bae7c915dd41dd57265769"}'
```

## Full-Site Retry

The first crawl completed with `qa_num=11`, which was too small for the target knowledge coverage.

On 2026-07-15, a broader Mercado Mexico crawl was submitted with:

- `task_id`: `7c3c46db0b5bd8ef94fb4b692bef97b4`
- `crawler_degree`: `3`
- `limit_page_num`: `1000`
- `keywords`: empty string, so the crawler does not filter child links by `ayuda`
- `client`: `mercado`
- `user`: `test_mercado_stone`
- `index_name`: `mercado_test_mercado_stone`
- root URL: `https://www.mercadolibre.com.mx/ayuda`
- `auth_config`: logged-in cookie passed only in the runtime request

Check status:

```bash
curl -sS -X POST http://120.77.147.247:6000/task_info \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"7c3c46db0b5bd8ef94fb4b692bef97b4"}'
```

## 2026-07-17 Status Check

The full-site retry task was checked on `main`.

- `/health`: service healthy, one active task.
- `/task_info`: task still reports `run_status=2`, `task_stage=multimodal_process`.
- URL crawl completed successfully at `2026-07-15 07:10:35`, with 604 crawled records.
- Content processing completed successfully at `2026-07-15 07:10:37`, with 604 processed records.
- Multimodal processing started at `2026-07-15 07:10:37`, but its last log line is `2026-07-15 08:42:36`.
- The multimodal process is still alive but sleeping with 0 CPU; no multimodal, translation, QA, reclear, or search-data output files were produced.

Conclusion: this task is not progressing normally. It appears stuck in multimodal image processing, likely waiting on a remote image/OCR/Dify request after broad crawling pulled in many marketplace/product pages and images.

## 2026-07-17 OCR Check

The OCR used by multimodal processing is the Dify workflow configured at `config/config_document_qasegment.json` under `image_ocr_config`, with `user=imageocr`.

Direct checks on `main` showed OCR itself is available:

- OCR on an already uploaded `file.marsmind.cc` image returned successfully in about 0.55s, with an empty OCR result for a low-text image.
- OCR on a known text-rich image returned successfully in about 0.62s with 118 characters.
- The exact mlstatic image URL shown at the last stuck log line was tested through the same `process_content` path: download, upload, and OCR completed in about 6.63s.

Conclusion: the Dify OCR workflow is currently reachable and working. The stuck full-site task is likely held by an old hung network request/subprocess state, not by OCR balance or a currently unavailable OCR service.

## 2026-07-17 Recovery

The stuck task was recovered without rerunning URL crawl or content processing.

Actions:

- Stopped the task through `/stop_task`; this released queue resources.
- Killed the orphaned `multimodal_process.py` child process left after stopping the parent.
- Backed up `control_service/html_kg_gen_task_control_tmp.py`.
- Changed the tmp controller's stage list to resume from `stage_3_multimodal_process`, then continue translation, QA, schema transform, index insertion, and segment insertion.
- Launched `/tmp/resume_html_kg_task.py`, which reads the original `task_info` from MySQL so the cookie is not passed in the process command line.
- Added runtime `PYTHONPATH=/root/knowledge_database_builder` and conda `PATH=/root/miniconda3/envs/py38/bin` in the resume wrapper so child stage commands use the same environment as the service.

Recovery process:

- parent PID: `2352217`
- child `multimodal_process.py` PID: `2352220`
- resume log: `log/off_task/7c3c46db0b5bd8ef94fb4b692bef97b4_resume_20260717-123628.log`
- current stage after restart: `multimodal_process`

Note: because this recovery was started manually rather than by the queue worker, `/health` does not count it in `active_tasks`. Use `/task_info`, the PIDs above, and the stage logs to monitor it.

Follow-up check:

- `/task_info` still reports `run_status=2`, `task_stage=multimodal_process`.
- Parent PID `2352217` and child PID `2352220` are alive.
- `log/off_task_log/7c3c46db0b5bd8ef94fb4b692bef97b4/multimodal_process.log` was still writing at `2026-07-17 12:40`.
- The log shows active image download, MinIO upload, and Dify `imageocr` calls, so the recovered run is progressing instead of immediately re-hanging.

## 2026-07-18 Status And Text-Only Recovery

The recovered full-site task stalled again in `multimodal_process`.

- `/task_info`: `run_status=2`, `task_stage=multimodal_process`.
- The old resumed parent/child processes were alive, but `multimodal_process.log` stopped at `2026-07-17 15:00:13`.
- Only 43 of 604 page-level `_multimodal.txt` outputs existed.
- The stuck page was a broad product/category page with many `mlstatic` product images; OCR and image-understanding calls were working, but the page-level multimodal pass was too expensive and could stall on the image loop.

Recovery action on `main`:

- Stopped the stuck multimodal process.
- Preserved the 43 existing multimodal outputs and rebuilt `crawler_and_process_results_multimodal_7c3c46db0b5bd8ef94fb4b692bef97b4.txt` with all 604 rows.
- Created text-only fallback `_multimodal.txt` outputs for the remaining 561 rows, setting `content_with_multimodal_unsderstanding` to the crawled text so downstream stages can continue.
- Rebuilt `multimodal_data_info_7c3c46db0b5bd8ef94fb4b692bef97b4.json` from the preserved multimodal outputs.
- Continued the task through `/tmp/finalize_mercado_text_only.py`; current next stage after the fix is `document_translate`.

This avoids rerunning URL crawl/content processing and avoids spending the task indefinitely on marketplace product images.

## 2026-07-18 Scope Correction

The broad task was stopped because the target is Melihelp/MercadoLibre Mexico help knowledge, not marketplace product/category pages.

Observed URL scope from task `7c3c46db0b5bd8ef94fb4b692bef97b4`:

- Total crawled URLs: 604
- `/ayuda` URLs: 21
- `listado.mercadolibre.com.mx` URLs: 331
- Marketplace/category/product-like URLs: about 418

The first page that stalled multimodal processing was:

```text
https://www.mercadolibre.com.mx/c/celulares-y-telefonia#menu=categories
```

It is a mobile-phone category page, not a help article. It had about 93k text characters and 251 `mlstatic` image links, which caused the OCR/image-understanding loop to spend excessive time.

Corrected crawl/recovery approach:

- Do not use empty `keywords` for this target. Empty keywords allow all child links into the queue.
- If using crawler expansion, use `keywords: "ayuda"` so only help URLs or help-labeled links are enqueued.
- Depth alone is not sufficient: depth 3 with empty keywords escaped into marketplace pages; depth 1 seed pages are safest once help URLs are known.
- The immediate recovery uses the 21 already-crawled `/ayuda` pages as seeds, with no expansion. Temporary runner on `main`:

```bash
/tmp/run_ayuda_seed_from_filtered.py 2b21991f684c299af9fd487c44a51d7c
```

This runner copies only the `/ayuda` HTML/JSON content from the broad crawl into task `2b21991f684c299af9fd487c44a51d7c`, creates a clean 21-line processed-result file, and continues from multimodal/translation/QA/index stages. The 21 help pages contain about 267k characters and no markdown images.

## 2026-07-18 Context-Enrichment Flags

For future Mercado Mexico HTML tasks, enable the Payoneer-style generic mining context only on corrected help-scope crawls. The HTML pipeline now reuses the document-side `business_context_builder` and `generic_knowledge_quality`; query mining is cached in `data/business_context_cache`, so the same `client + knowledge_objective + context sources` will not re-mine within TTL.

Recommended task fields:

```json
{
  "enable_context_enrichment": true,
  "enable_chat_query_context": true,
  "enable_web_context": false,
  "context_cache_ttl_days": 30,
  "quality_profile": "business_task_knowledge",
  "knowledge_objective": "只抽取 Mercado Libre 墨西哥帮助中心/Melihelp 中可用于客服、账号、安全、交易、售后、规则说明的知识；拒绝商品页、类目页、搜索结果页、登录注册页、cookie/隐私、广告推荐和页脚导航。",
  "business_context_text": "目标站点为 Mercado Libre Mexico 的帮助中心 https://www.mercadolibre.com.mx/ayuda；本任务只保留墨西哥站点的帮助/规则/操作说明知识。"
}
```

For Mercado URL scope, keep `keywords` constrained to `ayuda` or reuse verified `/ayuda` seeds; do not restart a broad empty-keywords depth-3 crawl.

## 2026-07-18 Context-Enrichment Smoke Test

Test task on `main`:

- `task_id`: `mxhtmlctx20260718171403`
- `client`: `test_melihelp_mx_context`
- `index_name`: `mercado_test_melihelp_mx_context`
- Source: reused the 21 verified `/ayuda` translated JSON files from task `2b21991f684c299af9fd487c44a51d7c`; no URL crawl was rerun.
- Context flags: `enable_context_enrichment=true`, `enable_chat_query_context=true`, `enable_web_context=false`.

Observed results:

- Business context stage succeeded and wrote `data/off_task_data/mxhtmlctx20260718171403/business_context.json`.
- Because the test client is not a real client, `chat_query_context` found 0 historical queries; context used only `business_context_text`.
- QA generated 21 page mappings.
- Generic quality repaired 55 rows and rejected 77 rows.
- QA schema produced 423 rows; all rows used platform `test_melihelp_mx_context`, not real `mercado`.
- No sampled QA/search/segment content leaked the context-control text (`抽取约束` / `测试任务`).
- Segment smoke sample on `Compras_638`, `Vendiendo_643`, `Seguridad_663` produced 3 rows, all with platform `test_melihelp_mx_context`.

## 2026-07-24 Full Fee Gap Fill

User query `墨西哥full尾程物流费用` did not retrieve Mexico-specific fee knowledge, although official MercadoLibre Mexico pages existed.

Official source pages used for the first补洞 batch included:

- `https://www.mercadolibre.com.mx/ayuda/costos-envios-gratis_3287`
- `https://www.mercadolibre.com.mx/ayuda/40538`
- `https://www.mercadolibre.com.mx/ayuda/40545`
- `https://www.mercadolibre.com.mx/ayuda/40547`
- `https://www.mercadolibre.com.mx/ayuda/4420`
- `https://www.mercadolibre.com.mx/ayuda/20522`
- `https://www.mercadolibre.com.mx/ayuda/21793`
- `https://www.mercadolibre.com.mx/ayuda/15731`
- `https://www.mercadolibre.com.mx/ayuda/41483`
- `https://www.mercadolibre.com.mx/ayuda/16645`

Production task:

- `task_id`: `abcd43a9eaa2ad7afde1043618da064c`
- `client`: `mercado_local`
- `user`: `mercado_local_admin`
- `index_name`: `mercado_local`
- `category`: `业务地区-墨西哥`
- `enable_context_enrichment=true`, `enable_chat_query_context=true`, `enable_web_context=false`

Operational notes:

- The URL crawl was stopped after the 20 intended URL records were available; the orphan child process was killed manually.
- The task was resumed from stage 2 with `/tmp/resume_abcd43_after_crawl.py` on `main`.
- Manual resume wrappers must set both `PATH=/root/miniconda3/envs/py38/bin:$PATH` and `PYTHONPATH=/root/knowledge_database_builder`; otherwise stage child commands can fail importing project packages.
- The completed task reported `qa_num=47`; ES validation found 51 QA docs and 13 segment docs for this `task_id`.
- 51 QA titles were prefixed with `墨西哥 `.
- Two fee QA docs were retitled/content-augmented with user wording `Full尾程物流费用/尾程配送费`, then rewritten through the search service `/insert` by original `_id` to regenerate embeddings. Direct ES updates change text but do not refresh vector embeddings.
- In `mercado_local`, `task_id` and `data_type` do not have `.keyword` fields; use normal `term` clauses for operational counts.
- `update_time` is mapped as date; do not bulk-update it with millisecond integers.

Validation:

```bash
curl -s -X POST http://127.0.0.1:8003/search \
  -H 'Content-Type: application/json' \
  -d '{"text":"墨西哥full尾程物流费用","index_names":"mercado_local","top_k":8,"score_threshold":-1}'
```

After embedding refresh, the top result was the Mexico QA `墨西哥 Full尾程配送费/运费如何按重量尺寸和价格计算？`, sourced from `https://www.mercadolibre.com.mx/ayuda/40538`.

Known remaining gap:

- Seller learning pages under `vendedores.mercadolibre.com.mx/nota` were crawled but not inserted in this task because `firecrawl_content` had text while `content_with_multimodal_unsderstanding` and `translated_text` were empty, so QA/segment stages skipped them.
- Linked official URLs still missing from `mercado_local` include `https://www.mercadolibre.com.mx/ayuda/51576`, `https://www.mercadolibre.com.mx/ayuda/Dimensiones-maximas-perm-tidas_3163`, `https://www.mercadolibre.com.mx/ayuda/38951`, `https://www.mercadolibre.com.mx/ayuda/41488`, and seller notes for Agencias, Colecta, Flex, reputation, and Full.
- For the next seller-page补爬, fix the HTML pipeline field mapping or create a text-only fallback that sets downstream process fields from `firecrawl_content`; otherwise simply restarting the same payload can repeat the skip.

## 2026-07-24 Remaining URL Supplement

Follow-up task for the missing official ayuda and seller-note URLs:

- `task_id`: `abae34fc466473f5673e9bd6d0972979`
- `client`: `mercado_local`
- `user`: `mercado_local_admin`
- `index_name`: `mercado_local`
- `category`: `业务地区-墨西哥`
- URL seeds: 22 official `.mx` ayuda/seller URLs, including `ayuda/51576`, `Dimensiones-maximas-perm-tidas_3163`, Agencias, Colecta, Flex, reputation, and Full seller notes.
- Crawl scope: `crawler_degree=1`, `limit_page_num=5` per seed, no cookie, user agent only.
- Context flags: `enable_context_enrichment=true`, `enable_chat_query_context=true`, `enable_web_context=false`, `quality_profile=business_task_knowledge`.

Cookie check:

- The old runtime cookie from task `7c3c46db0b5bd8ef94fb4b692bef97b4` had `nsa_rotok.exp=2026-02-20 18:18:37`.
- On 2026-07-24 this cookie was expired.
- The target public `.mx` ayuda/seller pages returned Mexico content without cookie, so the supplement did not include a cookie.

Recovery notes:

- Normal URL crawl stalled after partial output, but direct HTTP fetches for the remaining seller pages worked.
- The crawler result was completed to 22 rows using existing crawler outputs plus direct `requests + BeautifulSoup` fetches for the missing seller pages.
- Multimodal processing can stall on seller-page images or YouTube thumbnails. For text knowledge, preserve real multimodal outputs already generated and create text-only fallback rows from `firecrawl_content` for the missing pages.
- Resume from translation after rebuilding `crawler_and_process_results_multimodal_<task_id>.txt` and `multimodal_data_info_<task_id>.json`.

Final validation:

- `/task_info`: `run_status=3`, `task_stage=completed`, `task_result={"qa_num":73}`.
- ES `mercado_local`: 74 QA docs, 21 segment docs, 95 docs total for this task id.
- All 74 QA titles were prefixed with `墨西哥 `.
- Example inserted sources include `https://www.mercadolibre.com.mx/ayuda/51576`, `https://www.mercadolibre.com.mx/ayuda/Dimensiones-maximas-perm-tidas_3163`, `https://vendedores.mercadolibre.com.mx/nota/envios-full-seguridad-y-velocidad-en-tus-entregas`, `https://vendedores.mercadolibre.com.mx/nota/mercado-envios-flex-destacate-por-tus-entregas`, and `https://vendedores.mercadolibre.com.mx/nota/despachar-tus-ventas-a-tiempo-la-clave-de-una-buena-reputacion`.

Search validation:

- `mercado_local` query `墨西哥full尾程物流费用` returns `墨西哥 Full尾程配送费/运费如何按重量尺寸和价格计算？` from `https://www.mercadolibre.com.mx/ayuda/40538` as the top result.
- `mercado_local_mercado_local_admin` still returns Brazil results for the same query because Mexico supplement data was intentionally inserted into `mercado_local` only.

Caveat:

- Full QA ES insertion was stopped after staying in `index_insert` for about 13 minutes without new log output. Logs showed the pre-existing mapping warning on index `mix` plus duplicate-data skips. For future quick validation, use `review_only=true` or skip ES insertion first, then run insertion separately once the test index/mapping is confirmed clean.

## 2026-07-21 Vendedores Mexico Learning Crawl

Started a Mercado Libre Mexico sellers learning-center task on `main`.

- `task_id`: `714ce78ac2f5ce0ac24b46631ec5dfcb`
- `task_type`: `html_qa_segment_mining`
- `url`: `https://vendedores.mercadolibre.com.mx/aprender?utm_source=mercadolibre&utm_medium=referral&utm_campaign=Menu_MyML`
- `url_infos`: `limit_page_num=1000`, `content_type=normal`, `keywords=nota,guia`, `crawler_degree=2`
- `client`: `mercado`
- `user`: `test_mercado_stone`
- `index_name`: `mercado_test_mercado_stone`
- `category_name`: `默认分组`
- `category_id`: `1`
- `is_use_firecrawl`: `true`
- `is_need_translated`: `1`
- Context enrichment enabled with `enable_chat_query_context=true`, `enable_web_context=false`.

Initial status after launch:

- `/task_info`: `run_status=2`, `task_stage=url_crawl`
- parent and crawler subprocess were alive on `main`
- `crawler_result_714ce78ac2f5ce0ac24b46631ec5dfcb.json` existed but was still 0 lines during the first minute

Monitor:

```bash
curl -sS -X POST http://120.77.147.247:6000/task_info \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"714ce78ac2f5ce0ac24b46631ec5dfcb"}'
```

Update:

- Task `714ce78ac2f5ce0ac24b46631ec5dfcb` was stopped manually because its `crawler_degree` was 2 and the crawl should use depth 3.
- Orphan translation child process from the stopped task was killed.
- Restarted with the same payload except `crawler_degree=3`.
- New `task_id`: `9e127ab44ca7946e17835e7741e4c99d`
- Initial status: `run_status=2`, `task_stage=url_crawl`; parent and crawler subprocess alive.

Monitor the restarted depth-3 task:

```bash
curl -sS -X POST http://120.77.147.247:6000/task_info \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"9e127ab44ca7946e17835e7741e4c99d"}'
```

Quality check on 2026-07-23:

- Task finished successfully: `run_status=3`, `task_stage=运行完成`, `task_result={"qa_num":220}`.
- Crawled 39 URLs: 1 root `/aprender`, 13 `/aprender/guia`, 15 `/aprender/nota`, 9 relevant legacy `/nota` seller articles, and 1 login URL.
- QA output: 250 search rows, including 220 high quality rows. QA noise scan found no cookie/privacy/footer leakage, but the login URL produced 1 unwanted high QA about login options.
- Generic quality post-process repaired 24 rows and rejected 69 rows (`thin_no_concrete_value=66`, `needs_review_dangling_or_generic=1`, `boilerplate=2`).
- Segment output: 47 rows, all high, but most segment rows still include raw cookie/privacy boilerplate because segment content preserves page text. Noise hits: cookie/cookies in 39 rows, privacidad/隐私 in 40 rows, login in 1 row.
- Recommendation: before treating this as clean production data, delete/reinsert this `task_id` after filtering login URLs and applying boilerplate cleanup to segment content, or add segment generic-quality cleanup before segment schema/index insertion.

## 2026-07-23 Production Country Split Migration

Official Mercado local indexes were split by country on `main`.

Backup:

- Backup directory: `/root/knowledge_database_builder/data/es_backup/mercado_country_split_20260723_224738`
- Indexes: `mercado_local`, `mercado_local_mercado_local_admin`
- Vector policy: vectors excluded. The project shell backup wrapper could not run in the default Python because `elasticsearch` was missing, so an equivalent scroll export was used to save mapping/settings and `_source` with `embedding` / `*_embedding` fields recursively removed.
- Verified export counts: `mercado_local=5969`, `mercado_local_mercado_local_admin=305`.

Category mapping:

- Category names must use full paths for nested categories.
- Brazil: `category_id=2080246249920495618`, `category_name=业务地区-巴西`, `primary_category.category_path=业务地区-巴西`.
- Mexico: `category_id=2080246249727557634`, `category_name=业务地区-墨西哥`, `primary_category.category_path=业务地区-墨西哥`.

Actions:

- `mercado_local`: all existing default-category docs moved to Brazil; all existing QA titles were prefixed with `巴西 `.
- `mercado_local_mercado_local_admin`: all existing default-category docs moved to Brazil; all existing QA titles were prefixed with `巴西 `.
- Mexico data was inserted into `mercado_local` only. To avoid migrating old temporary-index data, docs were copied from `mercado_test_mercado_stone` by exact `task_id=9e127ab44ca7946e17835e7741e4c99d`, not by copying the whole test index.
- Login docs were skipped. Segment docs copied from the test task were cleaned for cookie/privacy/footer lines where possible.

Final validation:

- `mercado_local`: total `6174`; default category `0`; Brazil category `5726`; Mexico category `205`; task/migration docs `205`; login-like docs `0`.
- `mercado_local`: old QA count `5015`, all `5015` titles start with `巴西 `; Mexico QA count `169`.
- `mercado_local_mercado_local_admin`: total `305`; default category `0`; Brazil category `303`; Mexico category `0`; old QA count `220`, all `220` titles start with `巴西 `.

Follow-up on 2026-07-24:

- Mexico QA titles also need a country prefix.
- Before update, the 169 affected QA docs were backed up without vectors to `data/migration/mercado_local_mexico_9e127_20260723_225810/before_mexico_qa_title_prefix.no_vector.ndjson.gz` on `main`.
- Updated `mercado_local` docs with `ext_info.migration_id=mercado_local_mexico_9e127_20260723` and `data_type=qa`, adding `墨西哥 ` to `title` only when it was not already present.
- Validation: Mexico QA total `169`, prefixed `169`, bad sample `[]`; old Brazil QA total `5015`, prefixed `5015`, bad sample `[]`.
