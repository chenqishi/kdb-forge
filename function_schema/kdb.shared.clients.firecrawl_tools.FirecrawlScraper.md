# kdb.shared.clients.firecrawl_tools.FirecrawlScraper

## Signature

`FirecrawlScraper(self, api_key=None, api_base=None, api_version=DEFAULT_API_VERSION, max_retries=3, timeout=180)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## 功能

直连 Firecrawl 官方 API 抓取单页正文，**替代原来的 Dify firecrawl workflow**。

## 为什么不再走 Dify workflow

原链路：`DifyWorkFlowRequest(api_key=GLOBAL_CONFIG['dify_api_key_firecrawl'])`
→ workflow `30e0b3c3-e548-4c44-8bc5-5b84bcd11f54` → 插件 `langgenius/firecrawl:0.0.3` 的 `scrape` 工具。

| `cookies` 输入 | 结果 |
|---|---|
| 不传 / `{}` | ✅ succeeded，9555 字符 |
| `"K=V"` 裸串 | ❌ failed `Invalid headers format` |
| `{"Cookie": "..."}` | ⚠️ **succeeded 但输出空串**（0.9s） |
| `{"User-Agent": "..."}` | ⚠️ **succeeded 但输出空串** |

即任何非空 header 都让它静默返回空（`status=succeeded`、无 error），
而调用方会把空串写进 `.firecrawl.txt`，下游 `process_key='firecrawl_content'` 整页静默跳过。

直连官方 API **v2** 同样参数则正常：Wayfair 开发者门户带
`headers={"Cookie": "DEV-PORTAL-LANGUAGE=zh-CN"}` 抓到 4264 字符、2252 个中文字。

## 与原 workflow 的参数对齐

默认值逐项抄自 `data/网页爬取url.yml` 的 `tool_configurations`，保证换实现后产物不变：

| 参数 | workflow 值 | 本类默认 |
|---|---|---|
| `formats` | `markdown` | `['markdown']` |
| `onlyMainContent` | `1` | `True` |
| `timeout` | `30000` | `30000` |
| `waitFor` | `0` | `0` |
| `includeTags` / `excludeTags` | `null` | `None`（不传） |
| `headers` | 绑定 workflow 入参 `cookies` | `headers` 参数 |

## 构造函数 Inputs

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| api_key | str | 否 | `GLOBAL_CONFIG['firecrawl_api_key']` | Firecrawl token（`fc-` 开头）。**只从 gitignore 的 `config/global_config.json` 读，不写进代码** |
| api_base | str | 否 | `GLOBAL_CONFIG['firecrawl_api_base']` → `https://api.firecrawl.dev` | 自部署时改这里 |
| api_version | str | 否 | `'v2'` | 拼成 `{api_base}/{api_version}/scrape` |
| max_retries | int | 否 | `3` | 总尝试次数 |
| timeout | int | 否 | `180` | HTTP 请求超时秒数（区别于 firecrawl 自己的 `timeout` 毫秒参数） |

`api_key` 缺失时构造抛 `ValueError`，不静默降级 —— 静默降级正是上面那个坑的成因。

## scrape() Inputs

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| url | str | 是 | - | 目标页面 |
| headers | dict/str | 否 | `None` | HTTP 头；传 str 时按 Cookie 处理，见 `build_cookie_headers` |
| formats | list | 否 | `['markdown']` | firecrawl 输出格式 |
| only_main_content | bool | 否 | `True` | 去掉导航/页脚 |
| wait_for | int | 否 | `0` | 渲染等待毫秒 |
| page_timeout | int | 否 | `30000` | firecrawl 侧抓取超时毫秒 |
| include_tags / exclude_tags | list | 否 | `None` | 为 `None` 时不放进请求体 |
| min_content_length | int | 否 | `0`（`fetch_firecrawl_content` 默认 `400`） | 正文短于该值当失败**重试**；`0` 关闭 |

firecrawl 会**间歇性**返回只剩 cookie 横幅/路径的近乎空内容，却 `success=true`：

- 26 个 URL 并发跑一遍，其中 2 个返回 26 字符 / 136 字符（正常应为 12518 / 10628）
- 同样 URL、同样参数**单独重试立即正常**，与 `waitFor` 无关（0/3000/8000/15000 结果一致）
- 返回的内容长这样：`/posts/dropship-orders-asn`，或 cookie 横幅 + 路径

这是"成功但内容为空"的静默失败，和被替换掉的 Dify 插件是同一类坑。加了长度校验后重跑
26/26 全部拿到完整中文。阈值 `400` 足以放过合法短页，又能挡住只剩样板的返回。

## Outputs

| 类型 | 说明 |
|------|------|
| str | markdown 正文；抓不到返回 `''` |

## 异常

- 构造时 `api_key` 为空 → `ValueError`
- 重试耗尽（网络异常 / 非 200 / `success=false`）→ `RuntimeError`

## 依赖的外部接口

`POST {api_base}/{api_version}/scrape`，`Authorization: Bearer <token>`

请求体（省略值为 `None` 的字段）：

```json
{"url": "...", "formats": ["markdown"], "onlyMainContent": true,
 "timeout": 30000, "waitFor": 0, "headers": {"Cookie": "..."}}
```

响应：`{"success": true, "data": {"markdown": "...", "metadata": {...}}}`，取 `data.markdown`。

## SQL

无。

## Source

`src/kdb/shared/clients/firecrawl_tools.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
