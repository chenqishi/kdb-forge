# payoneer_olive 知识库补全报告

2026-08-29 ~ 08-31 · 口径：生产 dual 召回 + 类目过滤 + 固化内部/公开标签

## 一、结果

### 应答口径覆盖率（排除渠道内部）

| 平台 | 缺口 | 公开分母 | 初始 | 优化后 |
|---|---|---|---|---|
| Bol | 51 | 39 | 24% | **82%** ✅ |
| Allegro | 38 | 30 | 22% | **76%** |
| Amazon | 22 | 14 | 21% | **71%** |
| Wayfair | 20 | 14 | 33% | **71%** |
| Walmart | 25 | 16 | 29% | **67%** |
| eBay | 18 | 15 | 12% | **67%** |
| OnBuy | 10 | 8 | 25% | **67%** |
| **合计** | | **134** | **27%** | **74%** |

小平台（分母<10，报条数）：Joom 8/9、Chewy 5/5、Kaufland 4/4、OTTO 3/4、Cdiscount 3/4。

### 产出规模
- **1,332 篇文档 → 31,471 条知识**，占全库 active（49,008）的 **64%**
- 爬取平台 5 → 20 个
- **审核状态（2026-08-31 实测）**：31,471 条中
  `audit_result=2` **20,832 条**、`=1` 2 条 → **线上可召回 20,834 条（66%）**；
  `=0` 4,302 条、`=-1` 6,335 条仍待审。
  仓库的 auto_audit（commit `ee488ae`，high 置信度写 audit_result=2）已自动过审大部分。
  实测线上口径可召回：查「Bol 佣金要交多少增值税」返回 3 条 audit=2 的对口答案。
  全库 active 48,969，线上可召回 28,604 —— 本轮贡献 20,834 条（73%）。

## 二、关键发现

### 1. 爬对站 >> 爬得多
四个平台一开始都爬错了站，换对之后效果显著：

| 平台 | 原来爬的 | 正确的文档站 |
|---|---|---|
| Walmart | marketplace.walmart.com（营销页） | marketplacelearn.walmart.com |
| Allegro | allegro.pl/pomoc（波兰语买家帮助） | help.allegro.com/en/sell |
| eBay | export.ebay.com（出口计划政策站） | ebay.com/sellercenter |
| Kaufland | sellerportal.kaufland.de（登录墙） | kauflandglobalmarketplace.com/seller-university |

对照：Wayfair 只用 7 篇达到 69%，而 Walmart 最初 73 篇营销页只有 40%。

### 2. 33% 的缺口是渠道内部知识，官网永远补不上
固化标签后：309 条缺口中 **208 公开 / 101 内部（33%）**。
内部占比高的平台：Lowes 58%、BestBuy 51%、通用 46%。
**实证**：BestBuy 38 篇官方文档全文检索，"GMV" 和 "Payoneer" 命中均为 **0**，
而缺口问的正是「单店年 GMV 500 万美元」「问卷最后写 Payoneer」——只存在于群聊。

### 3. 无官网可爬的平台
- **ManoMano**（20 条缺口）：试过 6 个入口全部 404/DNS 不存在；`faq.manomano.com` 是买家 FAQ
  （8379 字里 "vendeur/seller/commission" 词频 0）。入驻走分国家邮箱，不公开文档。
- **通用**（24 条）：按定义就没有对应官网。

## 三、可复用产出
- `.claude/skills/find-knowledge-sources/SKILL.md` —— 找资料源的方法
- `data/payoneer_olive/缺口_内部公开标签_固化.csv` —— 340 条内部/公开标签（3次投票）
- `data/payoneer_olive/群聊知识_待审阅.csv` —— 40 条群聊知识（未灌库，待决策）
- memory 中 8 条测量踩坑记录

## 四、待办
1. **审核放行** 31,471 条待审知识（归知识审核平台）
2. **群聊知识 40 条**是否灌库——含 BestBuy 招商标准等官网补不上的内容
3. **eBay 仍有空间**：内部占比仅 17%，67% 里剩下的多是真缺口
