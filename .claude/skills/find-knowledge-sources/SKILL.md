---
name: find-knowledge-sources
version: 1.0.0
description: "给知识库缺口找资料源：先用未覆盖的 query 本身去检索（补上平台名），再定位官网入口、爬取、验质。凡是要给某平台补知识库、找官网资料、判断某平台有没有公开资料时使用。"
---

# find-knowledge-sources

## 何时使用

- 要给某个平台补知识库、找官网/帮助中心资料
- 要判断"这个平台的官网到底有没有这些答案"
- 缺口 query 检索不到，需要找新的资料来源

## 核心原则：**用未覆盖的 query 去检索，不要猜 URL**

这是本 skill 存在的唯一原因。**别凭记忆拼域名**。

❌ **错误做法**（2026-08-29 实测，代价惨重）：
在代码里写死候选域名逐个试 —— `sellers.lowes.com`、`partners.wayfair.com`、
`manomano.fr/vendre`、`supplier.lowes.com`、`lowesmarketplace.mirakl.net`……
ManoMano / Lowes / Wayfair 各试 5–10 个入口全部 404 或登录页，
于是我判定「这三个平台官网没有资料，只能靠群聊沉淀」——**结论是错的**，
白白放弃 59 条缺口。

✅ **正确做法**：拿**没被覆盖的 query 本身**去 WebSearch，**补上平台名**。
一搜就出真实入口：

| 平台 | 我猜的（全失败） | 搜出来的真实地址 |
|---|---|---|
| Wayfair | partners.wayfair.com（登录页） | **sell.wayfair.com** + /onboarding-checklist |
| Lowes | seller.lowes.com（空壳） | **seller.lowes.com/mirakl-seller-documentation/** |
| ManoMano | manomano.fr/vendre（404） | **about.manomano.com/en/become-a-seller/** |

差的往往只是**路径或子域**：`seller.lowes.com` 确实存在，但内容在
`/mirakl-seller-documentation/` 下；Wayfair 正确的是 `sell.` 而不是 `partners.`。

## 步骤

### 1. 取未覆盖的 query
从覆盖率报告里挑 `verdict=missing` 且**非渠道内部**的 query
（渠道内部的官网天然没有，搜也白搜，见 [[channel-internal-share-predicts-source]]）。

### 2. 用 query 本身检索（关键步骤）
```
WebSearch("<平台名> <缺口query的核心词>")
WebSearch("<平台名> seller onboarding requirements official documentation")
```
- **补平台名**，否则搜到的是别家的
- 一次搜 2–3 条不同角度的 query，交叉印证入口
- 搜索结果里的**正文摘要本身就能验证"官网有没有这个答案"**——
  比先爬回来再判快得多

### 3. 从搜索结果提取真实入口
优先 `sell.*` / `seller.*` / `about.*/become-a-seller` / `*/mirakl-seller-documentation`
这类**文档路径**，而不是裸域名（裸域名常是营销页或登录墙）。

### 4. 爬取
- 有 sitemap → `prep_platform_sources.py` 盘点后 `crawl_url_list.py`
- 无 sitemap → `discover_links.py` 做链接发现
- 403/SPA/登录墙 → `commons/firecrawl_tools.py`（key 在 global_config.json）
  - firecrawl 明确拒绝某站会报 "we do not support this site"，换子域再试
  - 实测 `seller-us.tiktok.com` 被拒，`seller.tiktokglobalshop.com` 通

### 5. 验质（**每次必做**，别跳）
落盘后先打开看一眼首篇正文，再报"爬到 N 篇"：

| 检查 | 阈值 | 踩过的坑 |
|---|---|---|
| 平均每篇字数 | 卖家帮助页 1K–8K 字 | Chewy 平均 9.3 万字 = 抓到商品分类页，187 万字噪声 |
| 首个小节 | 不能是 cookie/隐私 | Allegro 30/30 篇首节是同意横幅，正文一半是样板 |
| 是否 404 页 | 正文前 600 字无 "404/not found" | ManoMano 1703 字的法语 404 页被当成有效语料 |
| 是否登录壳 | 多篇字数完全相同 = 同一个壳 | Chewy 4 篇均 1073 字的 "please sign in" |
| 空标题 / 无 `##` 小节 | 应为 0 | export.ebay.com 无静态 `<title>`，要回退取 `<h1>` |

对应工具已内置这些过滤：`crawl_url_list.py` 的
`looks_like_error_page()` / `_CONSENT_RE` / `_KEEP` 词边界。

## 陷阱：**招商页 ≠ 卖家文档站**（实测栽了三次）

平台首页/招商落地页容易找，但它**不是**卖家要查的文档。三次实测：

| 平台 | 我爬到的（覆盖率低） | 真正的文档站 |
|---|---|---|
| Walmart | `marketplace.walmart.com` 营销页「Seller Success Formula」「Pricing」→ **40%** | **`marketplacelearn.walmart.com`**（sitemap 1237 页） |
| Allegro | `allegro.pl/pomoc` 波兰语买家帮助 → **78%** | **`help.allegro.com/en/sell/`**（149 页英文卖家帮助） |
| Kaufland | `sellerportal.kaufland.de` 登录墙 → 1 篇 | **`kauflandglobalmarketplace.com/en/seller-university/`**（59 页） |

**识别信号**：爬到的标题若是「Discover how…」「Success Formula」「Pricing」「Why sell with us」，
就是营销页；卖家文档的标题长这样：「WFS inbound orders: Send inventory」
「Registration for non-Polish companies」「General EPR information」。

**同一平台常有多个站，要按缺口性质选**（eBay 那次的教训）：
eBay 有 `export.ebay.com`（中国出口计划：政策/招商）和 `ebay.com/sellercenter`（后台运营帮助）。
我爬了前者 152 篇，覆盖率仍只有 **53%** —— 因为缺口问的是
「店铺余额在哪看」「其他站点月租统一吗」「开通的站点能关闭吗」这类**后台操作**，
只有 sellercenter 才写。补爬 66 篇运营帮助后才对上。

→ 先看未覆盖 query 属于哪类，再决定爬哪个站：
  - 问**资质/费率/政策** → 招商站、policy 站
  - 问**后台怎么操作/在哪看** → seller center、help center、marketplace learn

**做法**：别停在首页。拿**未覆盖的实操 query**（"从台湾发货进 WFS 后台填不了海外地址"）
去搜，搜索结果会直接指向文档站的具体页面，顺着它的域名再取 sitemap。

## 检索融合：**必须用 RRF，不能按分数加权**

量覆盖率时把关键词路和向量路合并，**不能直接 `score * 权重` 相加**：
BM25 分数量级 ~29，`cosineSimilarity+1` 只有 ~1.7，乘任何权重都压不过。
实测正确条目在向量路排第 2，分数加权合并后被 BM25 结果挤出 top5，
判定器看不到它 → 判 missing → **覆盖率被系统性低估**（我因此连报 26/29/36/50 四个错数）。

用 RRF（倒数排名融合），只看各路排名、免疫量级差异：
```python
ranks[doc_id] += 1.0 / (60 + rank)   # 每一路各自的 rank，k=60 通用取值
```

## 复合平台 / 第三方广告页：**灌库前必须剔掉**

爬到的页面里有两类会污染类目，务必在建 manifest 前删：

**1. 第三方服务商广告页**（最常见，占比可能过半）
Walmart 73 篇里有 **41 篇**是 `Partner with Sellbrite / ShipBob / TaxJar…
- Walmart.com solution provider page`，每篇约 800 字模板文案，讲的是第三方 ERP/物流商，
**不是 Walmart 自己的规则**。灌进去 278 条噪声，且是 Walmart 覆盖率只有 40% 的主因之一。
识别：标题以 `Partner with ` / `Solution provider` 开头，正文短且高度雷同（字数几乎相同）。

**2. 正文提到多个平台的文档**
先看**主语是谁**再决定要不要删：
- ✅ 保留：Walmart 的 WFS 页顺带列了"可履约 Amazon/eBay 订单"、Amazon 的 Veeqo 页列了支持渠道
  —— 主体仍是本平台规则，别的平台只是被提及
- ❌ 删掉：横向对比文（"Amazon vs Walmart 哪个好"）、第三方聚合站的多平台指南

检查方法：
```python
others=[p for p in PLATFORMS if p!=self and re.search(p, text, re.I)]
# 命中后**打开看主语**，不要只看命中就删 —— 实测跨平台提及率 0~5%，绝大多数是正常提及
```

**3. 提示词泄漏**（挖掘阶段产生，灌库后才能查）
实测出现过「答案输出的格式要求是什么？」→「答案必须先给出完整文字说明，不能只给 [图N] 标记」
这类把**挖掘提示词本身**变成知识的条目。量很小（11000 条里约 4 条），但检索到会误导。
灌库后按 `图N` / `不能只给` / `答案必须先给出` 这类特征词查一遍软删。

## 停止条件

两个，满足其一即停：
1. 覆盖率达到目标（**排除渠道内部后**的口径，见
   [[payoneer-olive-internal-vs-public-coverage]]）
2. **再也搜不到新的知识源** —— 注意"搜不到"要以**检索过**为准，
   不是"我猜的几个 URL 都 404"

## 相关

- [[crawl-url-filter-needs-word-boundary]] —— URL 白名单要加词边界
- [[verify-measurement-before-reporting-number]] —— 报覆盖率前先冒烟测试
- `docs/Architecture_Overview_Diagram.md` —— 爬取→挖掘→灌库链路
