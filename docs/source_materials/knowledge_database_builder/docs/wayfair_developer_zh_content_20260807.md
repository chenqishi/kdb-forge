# Wayfair 开发者门户中文内容抓取（2026-08-07）

## 结论先说

`https://developer.wayfair.io` **没有中文 URL**，但**中文正文可以直接抓**，而且是官方译文，不需要机器翻译。

这条结论修正了 `docs/wayfair_developer_url_recrawl_20260806.md` 里「找不到中文，只能 `is_need_translated=true`」的判断。

## 一、为什么找不到中文 URL

语言由 **cookie** 决定，不是路径也不是 query。前端 bundle
`_next/static/chunks/pages/_app-*.js` 模块 `70505`：

```js
i = "DEV-PORTAL-LANGUAGE",  a = "partner_home_language",
s = {"en-US": "eng_US", "zh-CN": "zh_CN"},
u = function(e){ r(e); Cookies.set(i, e); Cookies.set(a, s[e]); window.location.reload(); }
```

语言开关只有两项（同 bundle `n4 = {"en-US":"English","zh-CN":"中文"}`）。切换后 `location.reload()`，**URL 完全不变**。

所以 `/zh-cn/posts/...`、`?locale=zh-CN`、`?lang=zh-CN` 这些尝试必然失败 —— 它们从一开始就不是这个站的机制。

## 二、正文从哪来

页面是 Next.js 静态导出，`__NEXT_DATA__.pageProps` 为空，HTML 只有 5.5KB 的骨架，正文全部由前端向**内容 BFF** 拉：

```
POST https://api.wayfair.io/content/v1/developer-portal-bff/graphql
```

**无需鉴权**。同域另外两个 BFF 都不能用（实测）：

| 端点 | 结果 |
|---|---|
| `/content/v1/developer-portal-bff/graphql` | 200 ✅ |
| `/public/v1/developer-portal-bff/graphql` | 403 `graphql operation not permitted` |
| `/v1/developer-portal-bff/graphql` | 401 `Unauthorized` |

请求头只需 `content-type: application/json` + `origin: https://developer.wayfair.io`。

## 三、两类页面，两种取法

### 1) Post 类（17 个）：`/posts/<slug>`

query 来自 chunk `759-*.js` 模块 `50839`，字段集合**不能改**（加 schema 里没有的字段会整条请求报错）：

```graphql
query Post($slug: String!, $locale: String) {
  postCollection(where: {slug: $slug}, locale: $locale, limit: 1) {
    items { title body { json links { assets { block { sys { id } contentType url } } } } sys { id } }
  }
}
```

`locale` 传 `zh-CN` 即得官方中文。返回的是 **Contentful Rich Text JSON**，不是 HTML，需要本地渲染
（`richtext_to_html`）。slug 大小写敏感（`FAQs`、`Cg-Orders-Guide`）。

### 2) Reference 类（9 个）：`/posts/docs/<apiId>/reference/GraphQL/v1.0.0`

```graphql
query ReferenceHtml($where: ReferenceFilter!) { referenceHtml(where: $where) }
```

```json
{"where": {"bucketName": "wf-developer-portal-prod",
           "apiProtocol": "GraphQL", "apiId": "...", "version": "v1.0.0"}}
```

**中文版靠 apiId 后缀**，前端源码（chunk `pages/posts/[...slug]-*.js`）：

```js
apiId: "en-US" === (a = a || "en-US") ? e : e + "-" + a
```

即 `inventory-api` → `inventory-api-zh-CN`。返回的是渲染好的 HTML（SpectaQL 产物）。

## 四、两个必须知道的坑

### 坑 1：reference 返回值不一定是完整 HTML 文档

9 个里只有 1 个（`inventory-api`）返回 `<!DOCTYPE html>` 完整文档，
其余 8 个返回的是**以 `<style>` 开头的片段**，没有 `<html>`/`<body>`。

缺 `<body>` 会让下游 `WebBatchCrawler.extract_formatted_text_by_flat` 直接返回 `""`，
然后在 `knowledge_html_clear_by_dify.py:146` 被静默 `continue`，整页内容无声消失。所以片段必须补包装。

### 坑 2：不能用 `'<body' in html` 判断是不是完整文档

SpectaQL 会在**每个代码示例里内嵌** `<html><head></head><body><pre><code>…`
（实测 `orders-api` 有 52 处）。子串判断会把片段误判成完整文档 → 不加包装 →
`html.parser` 遇到第一个内嵌 `<body>` 就把它之前的正文全归到 head 下 →
330KB 的页面只能抽出 3965 字符、0 个中文字。

正确判断：**去掉前导空白/注释后，是否以 `<!doctype` 或 `<html` 开头**（见 `_is_full_html_document`）。

## 五、复跑

```bash
export PYTHONPATH=$PWD
PY=/opt/anaconda3/envs/py39/bin/python

$PY -m pytest tests/test_wayfair_richtext_to_html.py -q

$PY knowledge_crawler_tool/web_crawl/wayfair_developer_portal_fetch.py run_fetch \
  --excel_path='/Users/chenqishi/Documents/笔记本地/大模型项目鱼爷/wayfair/官方资料/待爬取知识/开发者门户上传260805.xlsx' \
  --output_dir=data/wayfair/html --locale=zh-CN --flag=20260807
```

`--locale=en-US` 可取英文版对照。`--overwrite=False` 跳过已存在文件。
并发默认 4：实测 8 并发会触发偶发 `504 Gateway Timeout`（代码内已有重试，不会因此失败）。

产物：

- `data/wayfair/html/<slug>.html`，`<slug>` = `WebBatchCrawler.get_filename_from_url(url)`，
  与既有爬虫产物、ES `ext_info.from_file_name` 命名一致
- `data/wayfair/html/manifest_wayfair_dev_zhcn_20260807.json`

manifest 里 `cjk_char_count` 是核对指标：`zh-CN` 下若为 0，说明该页没拿到中文，必须查。

## 六、本次结果（2026-08-07）

- URL 总数 **26**（Excel 中以单元格超链接形式存储，`cell.value` 是标签，URL 在 `cell.hyperlink.target`）
- 类型分布：Post **17** + Reference **9**
- **26/26 全部有官方中文版**，无失败、无空中文
- 每个文件都通过 `extract_formatted_text_by_flat` 验证可抽取出中文正文

### 内容质量观察

- Reference 类：**描述文案是中文，GraphQL schema 字段名保持英文** —— 这是 API 文档的正常形态，不是漏翻。
  所以 reference 文件的中文字符占比天然偏低（如 `inventory-visibility-onhand-api` 仅 263 个中文字），
  不能拿它当"没翻译"的判据。
- 部分 reference（如 `orders-api`）的 Wayfair 官方译文**简繁混用**
  （"訂單管理API允許供應商從Wayfair檢索直銷採購訂單，併發送…可以根据日期…"），
  这是 Wayfair 自己的翻译质量问题，不是抓取问题。若入库需要统一简体，要单独做繁转简。
- 有 8 篇 Post 的官方 `title` 都是泛化的「指南」（对应 Excel 里 `- CastleGate Inventory On Hand API`
  这类具体名字）。溯源 URL 已写进每个文件的 `<link rel="canonical">` 和头部注释；
  若后续 QA 挖掘需要更强的业务上下文，可考虑把 Excel 标签补进正文。

## 七、能不能让线上流水线（web_batch_crawler + firecrawl）直接抓中文？

结论：**"把 cookie 换成中文的"这一步本身有效，但线上那套即使换了也拿不到中文**，两个各自独立、都致命的原因。

### 验证：cookie 确实能让浏览器渲染中文

playwright + Chrome 实测同一个 `/posts/FAQs`：

| 条件 | 35s 后正文 |
|---|---|
| 无 cookie | 0 个中文，`Developer Portal…`（英文） |
| `DEV-PORTAL-LANGUAGE=zh-CN` | 中文，`常见问题解答 (FAQ)`、`Wayfair 开发者门户是一个自助服务平台…` |

前端是**直接读 cookie** 决定 locale 的（不只是语言开关按钮在用）：
`[...slug]` chunk 里 post 走 `["en-US","zh-CN"].includes(Cookies.get("DEV-PORTAL-LANGUAGE")) && {locale: …}`，
reference 走 `v(..., Cookies.get("DEV-PORTAL-LANGUAGE")||"")`。
所以只要在页面加载前把 cookie 塞进去就生效，值必须**精确等于 `zh-CN`**（不是 `zh_CN`）。

### 阻塞一：firecrawl 收不到 cookie，而下游吃的正是它

```python
# web_batch_crawler.py:342-345 —— 只传了 url，硬编码
other_inputs = {"url": current_url}
firecrawl_content = self.firecrawl.request_dify("", other_inputs=other_inputs)
```

`auth_config.cookie` 只作用于 Selenium（`set_cookies_for_domain`）。firecrawl 是 Dify 服务端另起一次抓取，
拿不到任何本地 cookie → **必然英文**。

而 `html_kg_gen_task_control.py:362` 决定下游吃哪个字段：

```python
process_key = 'firecrawl_content' if self.is_use_firecrawl else 'formatted_text'
```

`is_use_firecrawl=true` 时，多模态 → 翻译 → QA 全程用的是 firecrawl 的英文结果，
Selenium 存下来的那份 HTML 从头到尾没人读。

### 阻塞二：Selenium 等待时间差一个数量级（**只影响 Selenium，不影响 firecrawl**）

`safe_get` 是 `sleep(5)` + 滚动 + `sleep(2)` ≈ 7 秒。实测渲染进度（FAQs，完整正文 2163 个中文字）：

| 等待 | HTML 大小 | 中文字数 |
|---|---|---|
| 5s | 8147 | **0**（空骨架） |
| 10s | 7608 | **0** |
| 20s | 25569 | 73 |
| 35s | 28896 | 112 |

**35 秒都没渲染完**，线上的 7 秒只能抓到空骨架。这个站的内容 BFF 本身就慢（直连 API 也反复吃 504）。

> 由此可推断（**未验证**，需要在任务机上看文件大小确认）：20260806 那次任务
> `data/off_task_data/1f47a2e7cff6defe869fe1280ec7a8b1/` 下的 `.html` 很可能全是 5~8KB 的空骨架，
> 因为 `is_use_firecrawl=true` 时下游不读它，所以一直没暴露。

### firecrawl 传 cookie：workflow 有这个参数，但**功能是坏的**（已实测）

Firecrawl 官方 scrape 接口本身**支持** `headers`（object，文档原话 "Can be used to send cookies, user-agent, etc."）。
仓库不直连 firecrawl，走的是 Dify workflow（`GLOBAL_CONFIG['dify_api_key_firecrawl']`，
workflow_id `30e0b3c3-e548-4c44-8bc5-5b84bcd11f54`），该 workflow **确实声明了 `cookies` 输入变量**，
接到 firecrawl 节点的 `headers` 上。

但实测下来这个参数**不能用**（`POST {dify_api_base}/workflows/run`，取 `data.outputs.Final`）：

| `cookies` 传值 | 结果 |
|---|---|
| 不传 | ✅ succeeded 1.9s，9555 字符英文正文 |
| `"DEV-PORTAL-LANGUAGE=zh-CN"`（裸串） | ❌ **failed** — `Invalid headers format`（说明它要的是 JSON headers 对象） |
| `{}`（空对象） | ✅ succeeded 1.1s，9555 字符，正常 |
| `{"Cookie": "DEV-PORTAL-LANGUAGE=zh-CN"}` | ⚠️ succeeded 0.9s，**输出空字符串** |
| `{"User-Agent": "Mozilla/5.0"}`（无害头） | ⚠️ succeeded 0.9s，**输出空字符串** |
| `{"headers": {"Cookie": …}}`（嵌套） | ⚠️ succeeded 0.9s，**输出空字符串** |

即：格式判断是对的（裸串报错、空对象正常），但**只要 headers 非空——哪怕只是 `User-Agent`——firecrawl 就返回空**。
用 `https://httpbin.org/cookies` 交叉验证同样如此（不带 header 返回 `{"cookies": {}}`，带 header 返回空）。
这是 Dify 插件 `langgenius/firecrawl/firecrawl` 的问题，不是格式没试对。

**这个坏法特别危险**：它是 `status=succeeded`、不报错、0.9 秒返回空串。
`web_batch_crawler.py:346` 会把空串直接写进 `.firecrawl.txt`，下游 `process_key='firecrawl_content'`
拿到空内容后整页静默跳过 —— 真在线上任务里配了 cookies，会得到一批空文件而任务显示成功。

### 已解决（2026-08-08）：改为直连 Firecrawl 官方 API

新增 `commons/firecrawl_tools.py`，`web_batch_crawler.py` 与 `single_page_local_crawl.py`
的 firecrawl 调用全部改走它，**不再经 Dify workflow**。默认参数逐项抄自
`data/网页爬取url.yml`（`formats=markdown` / `onlyMainContent=1` / `timeout=30000` / `waitFor=0`），
换实现后产物形态不变。token 在 `config/global_config.json` 的 `firecrawl_api_key`（已 gitignore）。

实测（同一个 `/posts/FAQs`）：

| 调用 | 结果 |
|---|---|
| 直连 v1 / v2，不带 cookie | 9555 字符，0 个中文 |
| 直连 v2 + `headers={"Cookie": "DEV-PORTAL-LANGUAGE=zh-CN"}` | **4264 字符，2252 个中文字** ✅ |

跑通 `single_page_local_crawl.crawl_single_page --cookie='DEV-PORTAL-LANGUAGE=zh-CN'`，
产出 JSON 里 `firecrawl_content` 4264 字符 / 2252 中文
（`formatted_text` 仍是 251 字符的 SPA 骨架 —— requests 不执行 JS，属预期，
`is_use_firecrawl=true` 时下游用的是 `firecrawl_content`）。

顺带修掉一个隐患：原来 `web_batch_crawler.py:346` **无条件**把 firecrawl 返回值写进
`.firecrawl.txt`，空串也写。写了就会被当成"已抓过"缓存住，下游拿到空内容整页静默跳过。
现在空正文不写盘并告警。

**所以本次选择直接调内容 API**：拿到的是结构化正文（不含导航/页脚样板），不用赌渲染时机，也不动任何公共配置。

## 八、与 20260806 机翻数据的关系

20260806 那次任务（`task_id=1f47a2e7cff6defe869fe1280ec7a8b1`）对这 26 个 URL 走了
`is_need_translated=true` 的机器翻译并已入库（`wayfair` 与 `wayfair_wayfair_test2` 两个索引）。

**本次只产出 HTML 文件，没有动 ES。** 用官方译文替换机翻结果需要单独做：
按 `ext_info.from_file_name.keyword` 软删除旧数据 + 重新入库，流程参考
`docs/wayfair_developer_url_recrawl_20260806.md`。
