# payoneer_olive 子链接抓取（到「入驻」为止）

日期：2026-08-09

## 背景与业务边界

11 篇平台官方攻略（见 `docs/payoneer_olive_doc_crawl.md`）正文里引用了大量子链接：
卖家大学文章、帮助中心政策页、其它飞书文档。

业务口径是**把卖家送到「成功入驻平台」为止，入驻之后怎么运营暂时不管**。所以：

| 要 | 不要 |
|---|---|
| 平台与模式介绍、入驻资质与主体要求、材料与证件、注册与认证流程、店铺开通与基础设置、审核与驳回、保证金、类目资质与禁限售、收款账户绑定、入驻相关费用 | 选品、爆款、广告投放、达人合作、直播玩法、大促、营销日历、经营方法论、数据洞察/榜单 |

## 筛选：用 LLM 判，不要用关键词

先试过正则关键词，**判不准**：`禁售商品政策`、`新店设置全流程`、`商标系统填写规范` 都属于入驻范畴
但不含「入驻/注册」字样；而 `statista.com`、`tabcut.com` 这类数据站明显无关却混在里面。

改成让 LLM 按上面的业务边界逐条判（锚文本 + URL），并顺带给出 `page_type`
（guide / policy / form / app / other）。315 条判出 109 条相关，去掉 `app`（登录后台、
注册页，本身没有可抽取内容）和 `form` 后剩 100 条。

## 可达性：必须**全量探**，不能抽样

这一步我踩了坑：抽了 `seller-id.tokopedia.com` 和 `seller.tiktokglobalshop.com`
各一条 URL，都返回「内容不存在」，据此判定**整个域名失效**，差点砍掉 31 条有效链接。

全量探测后真实情况是 **57/61 可读**，只有 1 条真死链、3 条内容过短——
我抽到的那两条恰好是失效的个例。

> 结论：域名级的可达性判断必须逐条探，样本量 1 不足以下结论。

## 抓取方式分流

按宿主分成三类：

| 走哪条链路 | 条数 | 说明 |
|---|---:|---|
| `login_doc_crawler` 的新 `web` 类型 | 57 | 卖家大学、帮助中心、公众号文章 |
| `login_doc_crawler` 已有的 lark/wecom/tencent | 29 | 飞书文档 17、企微文档 8、腾讯文档 4 |
| 跳过 | 10 | 字节内网 `olympus.bytedance.net`、墨西哥税务局官网、企微网盘等 |

### 为什么没用已有的 `html_qa_segment_mining`

先试了（这是仓库里现成的网页爬取链路，`docs/mercado_mx_help_crawl_task.md` 有用法），
投了最小的 2 条：**失败**。main 上的无头 Chrome 渲染 TikTok 卖家大学页面
`Timed out receiving message from renderer: 300.000`，重试 3 次全崩，
`crawler_result` 0 行；后面几个阶段空跑，一路「成功」到 segment 才因空文件报错——
**又是一个静默失效**：任务前 8 个阶段全绿，实际一个字都没抓到。

本地带登录态的 Chrome 渲染同样的页面完全正常（28255 字），所以改走本地爬取器。

## 新增的 `web` 类型

普通网页不是虚拟滚动的富文本应用，渲染完一次取全即可，难点在**框定正文容器**——
不框定就会把导航栏、侧边目录、页脚一起抓进来。

候选选择器都是实测出来的：

| 域名族 | 正文容器 | 条数 |
|---|---|---:|
| TikTok 卖家大学（seller-us / tokopedia / seller-mx / eu 四个域名同一套模板） | `article.article-main` / `.content-inner` | 25 |
| `seller.tiktokglobalshop.com` | `[class*=articleDetailLayout]` | 11 |
| `global-selling.mercadolibre.com` | `main` / `.page-content` | 22 |
| `mp.weixin.qq.com` | `.rich_media_area_primary` | 1 |

都没命中时退回「页面上文本最长的容器」。提取按 DOM 顺序走
`h1~h6 / p / li / pre / blockquote / table / img`，表格单元格里的图片沿用主链路的
`⟦IMG:src⟧` 占位符方案（见 `docs/payoneer_olive_doc_crawl.md` 坑 9）。

## 类目继承

子链接的类目**继承自引用它的父文档**：

- TikTok Shop 各站点已有二级类目，直接继承（`TikTok Shop-印尼` 等）
- Mercado Libre 只有一级类目，40 条子链接和主文档混在一起不好管，
  新建二级类目 `Mercado Libre-入驻指引`（id `2086354244463038466`）

## 本次结果

网页类 57 篇全部抓取成功：

| 类目 | 篇数 | 正文 | 图片 |
|---|---:|---:|---:|
| TikTok Shop-印尼 | 20 | 94159 | 131 |
| Mercado Libre-入驻指引 | 23 | 47972 | 59 |
| TikTok Shop-美国CCCU | 2 | 11840 | 2 |
| TikTok Shop-美国ACCU | 2 | 9308 | 2 |
| TikTok Shop-墨西哥 | 3 | 7913 | 18 |
| TikTok Shop-东南亚 | 7 | 3708 | 0 |
| **合计** | **57** | **174900** | **212** |

## 飞书表格（`lark_sheet`）：能抓的抓了，剩下的是权限问题

4 篇 `/sheets/` 链接一开始走 `lark` 的 DOM 提取，只拿到几十字——表格是 **canvas 画的**，
DOM 里 0 个 `<table>`。改走「点进网格 → 全选 → 复制 → 读剪贴板」拿 TSV。

### 坑：复制失败时读到的是**上一张表的残留**

第一版没清剪贴板，4 张不同的表**全部返回同一份内容**（320375 字，md5 一致），
而且四条日志都是 `status=ok`。这比抓不到危险得多：**内容看着有，实际张冠李戴**，
一路灌进库里没人会发现。

修法：复制前先写一个哨兵串进剪贴板，读回来还是哨兵就判失败（`copy_sheet_via_clipboard`）。
加了之后 4 篇里 3 篇如实转为 `failed`。

### 3 篇失败的真正原因：文档主人禁了复制

排查顺序（每一步都排除了一类猜测）：

| 试的 | 结果 |
|---|---|
| 等「加载中」消失再复制 | 60s 后仍显示加载中，复制照样失败 |
| 点网格本体而非视口中心 | 无改善 |
| `osascript` 激活 Chrome 拿 OS 焦点 | `document.hasFocus()` 为 true，复制照样失败 |
| 截页面自己的数据请求（仿 `capture_pdf_bytes`） | 表格数据走 **WebSocket**，HTTP 响应里没有 |
| 读 Cmd+C 后的 toast | **命中**：「由于文档权限设置，如需复制请联系 @欧向容 开通可编辑权限。」 |

所以 `copy_sheet_via_clipboard` 里加了 `_detect_copy_forbidden`，把权限问题
抛成 `CopyForbidden`，不再和技术故障混在一起重试三次。

| 表格 | 结果 |
|---|---|
| 印尼行业资质对照表（对外） | ✅ 320375 字（「对外」版没设限制） |
| TikTokShop 跨境卖家保证金 Policy | ❌ 禁止复制 |
| 新入驻商家-如何获取各种 ID | ❌ 禁止复制 |
| 印尼-成本核算表 | ❌ 禁止复制 |

> 要拿这 3 篇，只能找 @欧向容 开可编辑权限，代码层面无解。
> 截图 + OCR 能绕过，但那是在规避文档所有者明确设置的管控，需要业务方先拍板。

## 坑

1. **别抽样判可达性**（见上文），差点误杀 31 条。
2. **调试 Chrome 被关会中断整批**：爬到第 27 条时实例被关闭，报
   `TargetClosedError: Target page, context or browser has been closed`。
   `--skip-existing` 救回来了——已落盘的 30 条完好，重启实例续跑即可。长批次要留意这一点。
3. **剪贴板类抓取必须带哨兵**：复制没生效时读到的是上一次的残留，
   会造成「每篇内容都一样却全报成功」的静默污染。
4. **`html_qa_segment_mining` 在重 SPA 上会静默空跑**：渲染超时后 `crawler_result` 是空的，
   但阶段照报成功，直到 segment 阶段才因空文件失败。用它抓这类页面前先确认
   `crawler_result_<task_id>.json` 的行数。

## 知识生成（2026-08-09）

67 篇走 `data_control_tools/build_doc_mining_tasks.py`，一篇一个
`document_qa_segment_mining` 任务，投到 main（`120.77.147.247:6000`）。
类目已在爬取时挂好，投递时 `resolve_category` 直接用 `platform`
（子链接的 `platform` 存的就是完整类目路径 `TikTok Shop-印尼`）命中类目树，不用改代码。

| 类目 | 篇数 |
|---|---:|
| Mercado Libre-入驻指引 | 34 |
| TikTok Shop-印尼 | 21 |
| TikTok Shop-东南亚 | 4 |
| TikTok Shop-墨西哥 / 美国CCCU | 各 2 |
| TikTok Shop-全托管 / 美国ACCU / 欧盟(西德意法) / TikTok Shop | 各 1 |

### 投递前修掉的两个静默问题

**1. `crawl_manifest.json` 被覆盖，67 篇只投出 22 篇**

子链接分两批爬（`payoneer_olive_sublink_urls.json` 57 条网页 +
`payoneer_olive_sublink_doc_urls.json` 29 条文档），两批都往同一个 root 写
`crawl_manifest.json`，后一批把前一批**整个覆盖**。盘上 67 篇文件都在，
投递脚本按清单只看到 29 条（其中 22 条可用），**全程没有任何报错**。

`run_crawl` 现在调 `write_crawl_manifest`，按 `(platform, site)` 合并进已有清单。

> 通用教训：多份清单共用一个输出 root 时，清单文件必须**合并**写。

**2. 目录名撞车，8 篇被静默覆盖**

`(platform, site)` 决定落盘目录，而子链接的 `site` 是从 URL 截出来的 slug。
几条只有 query 尾巴不同的链接会截成同一个：

```
.../essay?identity=1&role=1&knowledge_id=741456…  ┐
.../essay?identity=1&role=1&knowledge_id=635812…  ├─ 全部截成
.../essay?identity=1&role=1&knowledge_id=100295…  │  seller_tiktokglobalshop_com_university_essay_identity_1_role
.../essay?identity=1&role=1&knowledge_id=871034…  ┘
```

57 条网页里 **6 组撞名、8 篇被后来者覆盖**。日志条条 `status=ok`，
盘上却少 8 篇——只有把清单和盘上文件逐条对账才会发现。丢的还不是边角料：
其中两篇分别 22705 字和 20373 字。

`load_url_manifest` 现在调 `disambiguate_sites`，撞名的补一段 URL 短哈希
（哈希只由 URL 决定，重跑稳定，`--skip-existing` 不会失效）。

> 对账时注意：**别用去掉 query 的 URL 做去重键**，
> 这批链接的 ID 恰恰就在 query 里，会把不同文章合成一条，
> 让"缺 12 条"看起来像"缺 0 条"。

**3. URL slug 被当成"站点名"喂给了 LLM**

主文档的 `site` 是 `美国ACCU` 这种人话，子链接的 `site` 是 URL 派生的
`bytedance_sg_larkoffice_com_docx_PmmFdbhwOog32nx07K5lqamaguc`。
这串东西原样进了 `files[].name`（会落到 `ext_info.from_file_name`，对账靠它）
和 `business_context_text`（"…欧盟(西德意法) bytedance_sg_larkoffice_com_docx_Pmm… 站点"）。

加 `is_display_site()` 区分两者；同时把 `meta.note` 里的**锚文本**接进业务背景——
锚文本说明了这篇子链接在父文档里承担什么角色，比 slug 有信息量得多。

### 类目继承的一个例外

欧盟站点攻略里链了一篇**日本**入驻攻略。按"继承父文档"会挂到
`TikTok Shop-欧盟(西德意法)`，等于把日本规则塞进欧盟类目，检索时会误导。
线上没有 `TikTok Shop-日本` 类目，改挂一级类目 `TikTok Shop`；
源清单 `payoneer_olive_sublink_doc_urls.json` 里也改了，重爬不会退回去。

> 继承类目时值得扫一遍标题里的站点词，跟类目对不上的单独处理。

## 相关文件

| 文件 | 说明 |
|---|---|
| `knowledge_crawler_tool/data/payoneer_olive_sublink_urls.json` | 网页类子链接清单（57） |
| `knowledge_crawler_tool/data/payoneer_olive_sublink_doc_urls.json` | 文档类子链接清单（29） |
| `category_sys_manager/data/payoneer_olive_sublink_categories.txt` | `Mercado Libre-入驻指引` |
| `data/payoneer_olive_sublinks/` | 抓取产物 |
