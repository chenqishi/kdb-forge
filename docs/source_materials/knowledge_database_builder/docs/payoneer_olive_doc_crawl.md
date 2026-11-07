# payoneer_olive 平台官方文档爬取（腾讯文档 / 企微文档 / 飞书）

日期：2026-08-06

## 背景

`payoneer_olive` 的知识几乎全来自群聊自动学习，缺少平台方给的权威入驻/运营文档。
业务方给了 10 条外部文档链接，覆盖 Mercado Libre / Noon / TikTok Shop 三个平台。
本轮**只做爬取归档**，按 `<平台>/<站点>` 落到 `data/payoneer_olive/`，不做 QA 挖掘、不写 ES。

平台目录名和**线上一级类目名严格一致**（见 `docs/payoneer_olive_platform_categories.md`），
后续灌库时 `category_name` 直接用目录名，不需要再维护一张映射表。

## 三类宿主的可达性（实测结论）

| 宿主 | 匿名可读 | 正文怎么拿 |
|---|---|---|
| `bytedance.sg.larkoffice.com`（飞书 SG） | **可以** | 浏览器 DOM + 虚拟滚动采集 |
| `bytedance.larkoffice.com`（飞书 CN） | 否 | 需登录**且需授权**（欧洲12国那篇 2026-08-08 才拿到权限） |
| `doc.weixin.qq.com`（企微文档） | 否 | 需企微登录；正文 canvas 渲染，走 `dop-api/opendoc`（明文 JSON） |
| `docs.qq.com`（腾讯文档） | **可以** | 只能走 `dop-api/opendoc`（base64+protobuf），正文是 canvas 渲染 |

两条容易踩空的结论：

1. **飞书 SG 的这批 TikTok Shop 攻略是公开的**，不需要登录，也不需要 lark-cli。
   （反过来说，本项目的 lark-cli 授权在自己租户，**读不了 ByteDance 租户的文档**，别往那条路上试。）
2. **腾讯系文档（腾讯文档 / 企微文档）不能用 DOM 抓**。正文画在 `<canvas class="surface">` 上，
   DOM 里只有一句无障碍占位文本「用户可以通过 control 加 ~ 打开或关闭无障碍功能」。
   滚动采集会返回一篇空文档，而且**不会报错**。
   两者都走各自域名下的 `dop-api/opendoc`，但**返回体的形态完全不同**：
   腾讯文档是 base64+protobuf（只能启发式提取文字），企微文档是**明文 JSON**（好解得多）。

## 方法

### 1. 起一个独立的 Chrome 调试实例

```bash
mkdir -p "$HOME/.cache/chrome-doc-crawl"
open -na "Google Chrome" --args \
  --user-data-dir="$HOME/.cache/chrome-doc-crawl" \
  --remote-debugging-port=9222 --no-first-run --no-default-browser-check
curl -s http://127.0.0.1:9222/json/version     # 验证
```

**Chrome 136+ 起，`--remote-debugging-port` 在默认 user-data-dir 上会被忽略**，
必须显式给一个独立目录。所以「给现有 Chrome 加个调试端口」这条路走不通。

用独立 profile 还有个好处：不用动用户现有的 Chrome。需要登录的站点在这个窗口里手工登录一次，
登录态就持久存在 `~/.cache/chrome-doc-crawl`，以后重跑不用再登。

> 试过「复制现有 Chrome profile 继承登录态」，被 Claude Code 的安全策略拦了
> （复制 Cookies/Login Data 会被判定成窃取凭证）。这个拦截是合理的，别绕，手工登录就行。

### 2. 跑爬取器

```bash
pip3 install --user playwright          # connect_over_cdp 不需要 playwright install

# 探测新宿主的 DOM 结构（定滚动容器和块选择器用）
python3 knowledge_crawler_tool/web_crawl/login_doc_crawler.py --probe-dom "<url>"

# 只采集不落盘，看字数和首尾片段
python3 knowledge_crawler_tool/web_crawl/login_doc_crawler.py \
  --manifest knowledge_crawler_tool/data/payoneer_olive_doc_urls.json \
  --probe-only --only "英国"

# 正式爬
python3 knowledge_crawler_tool/web_crawl/login_doc_crawler.py \
  --manifest knowledge_crawler_tool/data/payoneer_olive_doc_urls.json \
  --download-images
```

用 playwright `connect_over_cdp` 而不是 selenium：本机 chromedriver 是 144、Chrome 是 150，
版本对不上；`connect_over_cdp` 连已有实例，不依赖 driver 版本。

### 3. 产物结构

```
data/payoneer_olive/
├── crawl_manifest.json           # 每篇的状态/字数/图片数/耗时
├── Noon/通用/
├── Mercado Libre/通用/
└── TikTok Shop/{美国ACCU,美国CCCU,英国,东南亚,印尼,墨西哥,全托管,欧盟(西德意法),欧洲12国}/
```

每篇目录内：`content.md`（正文，图片写成 `images/xxx.png`）、`content.txt`（纯文本）、
`blocks.json`（块原始结构，可重解析）、`page.html`（渲染快照，**虚拟滚动下必然是局部的**）、
`images/`、`meta.json`。

## 本次结果

| 平台 | 站点 | 字数 | 图片 | 状态 |
|---|---|---:|---:|---|
| Mercado Libre | 通用 | 22840 | 22 | ok |
| Noon | 通用 | 17059 | 87 | ok |
| TikTok Shop | 美国ACCU | 4234 | 30 | ok |
| TikTok Shop | 美国CCCU | 6260 | 52 | ok |
| TikTok Shop | 欧洲12国 | 13810 | 52 | ok |
| TikTok Shop | 欧盟(西德意法) | 7776 | 37 | ok |
| TikTok Shop | 英国 | 5726 | 40 | ok |
| TikTok Shop | 东南亚 | 10134 | 21 | ok |
| TikTok Shop | 印尼 | 64265 | 127 | ok |
| TikTok Shop | 墨西哥 | 15545 | 53 | ok |
| TikTok Shop | 全托管 | 5646 | 43 | ok |

合计正文 173295 字、图片 564 张（全部非空、非登录页 HTML）。

### 美客多（企微文档）的提取路径

登录后页面自己会调
`https://doc.weixin.qq.com/dop-api/opendoc?scode=<share_code>&&u=null&doc_chunk_flag=0&id=<w3_docId>&normal=1&noEscape=1&outformat=1&preview_token=`
（从页面的网络请求里观察到的，不是猜的），返回**明文 JSON**：
正文全部在 `clientVars.collab_client_vars.initialAttributedText.text[0].commands[0].mutations`
里那唯一一条 `ty=="is"` 的 `s` 字段。控制符含义（实测）：

| 控制符 | 含义 |
|---|---|
| `\r` | 段落分隔 |
| `\x13 指令 \x14 标签 \x15` | 超链接 / 文档引用 / @提及，指令里第一个 http URL 就是目标 |
| `\x08` | 图片占位（本篇 23 处） |
| `\x0f`、`\x1e` | **之后是评论区**，全是 `@某某 这里要补充` 之类的协作留言，必须截掉 |

这个接口要登录态，所以在**已登录的页面上下文里 `fetch`**，脚本侧另起会话拿不到。

### 欧洲12国：2026-08-08 已开通权限并爬取完成

原先无权限（页面提示「当前登录账号为 素见MarsMind 的 石，你可以向 夏春雨 申请权限」），
2026-08-08 权限开通后已爬到：标题《[官方社群］TikTok Shop欧盟跨境POP(EU12)官方保姆级入驻攻略》，
13810 字 / 52 张图。内容是原欧盟 4 国（德法意西）+ 新增波兰、荷兰、比利时、匈牙利、葡萄牙、
奥地利、捷克、希腊，一个店铺管 12 国。

> 下面是当时无权限的记录，保留备查。

#### （历史）无权限，不是技术问题

`https://bytedance.larkoffice.com/wiki/Y0W0woF9Xi9Qglks3lwcLAYKnCe` 是飞书 CN 域的 wiki 节点。
登录后页面提示：

```
没有权限访问
当前登录账号为 素见MarsMind 的 石，你可以向 夏春雨 申请权限
```

要么找 `夏春雨` 授权，要么让对方把内容导出发过来。

替代来源：英国那篇正文里链到了 **SG 域的欧盟攻略**（西班牙/德国/意大利/法国），公开可读，
已作为 `TikTok Shop/欧盟(西德意法)` 补爬。它只覆盖 4 国，**不等于**原来那篇「欧洲12国」。

### 顺带发现的可爬清单

这批攻略互相引用得很密，`content.md` 里已经解析出几十条其它飞书文档链接
（印尼经营一本通、各类目选品报告、直播/广告投放手册、TTS 卖家 ID 查找方式…）：

```bash
grep -rhoE '\[[^]]+\]\(https://[a-z.]*larkoffice\.com/(docx|wiki)/[A-Za-z0-9]+\)' \
  "data/payoneer_olive/TikTok Shop" | sort -u
```

其中 `bytedance.sg.larkoffice.com` 的大概率也公开可读，是下一批扩爬的现成种子。

## 坑

1. **虚拟滚动**（最容易出的错）。飞书 docx 只渲染视口内的块：一篇文档首屏 47 个块，滚完 165 个。
   一次性 `innerText` 会漏掉绝大部分正文，而且**看起来是成功的**。
   必须逐屏采集 + 按块 id 去重 + 按绝对偏移排序。
2. **容器块会把后代块的图片再输出一遍**。`el.querySelectorAll('img')` 要过滤成
   `img.closest('[data-block-id]') === el`，否则正文里同一张图重复十几次。
3. **图片直链 401**。飞书图床要求 `<img>` 请求自带的 cookie/referer，脚本里再 `fetch` 一次会 401
   （某篇 23 张图失败 15 张）。改成**截获浏览器自己加载图片的响应体**后，失败降到 1 张。
   `blob:` URL 没有网络请求可截，只能在当前这一屏立刻取，滚过去就被 revoke。
4. **腾讯文档的 blob 里正文只占一小段**。这篇是从 Word 导入的，正文之后紧跟着整张 Word 样式表
   （`微软雅黑*`、`p.144115420359515000@eJ`、`schemas.openxmlformats.org`…），
   8398 行里真正的正文只有前 471 行。要在第一条样式表特征行处截断；
   但图片直链在截断点**之后**的资源区，所以要先捞图片再截断。
5. **「没有权限访问」页会正常渲染**，能爬出一堆界面文案（目录、申请权限、联系客服）。
   不做识别就会被当成爬成功——`is_login_page` 必须同时认登录页和无权限页。
6. 飞书正文塞了大量零宽字符，标题里还有 `U+202A~U+202E`、`U+2060~U+2064`。
   不清掉的话字数统计、目录名、检索全被污染。
7. **企微文档会恢复上次的阅读位置**。一进页面 `#scrollable.scrollTop` 就是 16917/17561（接近底部），
   滚动循环第一轮就判定「到底了」直接退出，22 张图只截到 2~3 张，而且 `status` 还是 `ok`。
   canvas 文档开滚前必须先 `scrollTop = 0`。
   同类问题：滚动容器是页面外壳的一部分，正文渲染完之前 `scrollHeight == clientHeight`，
   也会被判成一进来就到底——要先 `wait_for_function` 等它撑开。
8. 企微文档正文末尾的**评论区**（`\x0f` / `\x1e` 之后）也会被 opendoc 一起返回。
   不截掉就会把「@某某 这部分我们有卖家文档可以贴进去嘛？」这种协作留言当成知识抽出来。

9. **表格单元格里的图片会被整片丢掉**（影响面最大的一个，2026-08-08 才发现）。
   `tableToMd` 原来只取单元格 `innerText`，而表格的后代块又被标记成"已消费"，
   于是单元格里的操作截图两头都不出：表格里是空的、也不会作为独立图片块补上。
   欧洲12国那篇是表格化文档（11 个 table 块），第一次只抓到 **3 张图，实际有 88 张**。
   修法是把单元格里的图写成占位符 `⟦IMG:src⟧`，落盘时换成相对引用，位置不丢。
   修完重爬 9 篇共补回 **146 张图**（印尼 78→127、欧洲12国 3→52、墨西哥 36→53…）。
   教训：**图片数明显偏少但任务 `status=ok`** 是这类问题的唯一信号，
   验收时要拿"页面上肉眼可见的图片数"对一遍，不能只看有没有报错。

## 已知损失

- 腾讯文档 / 企微文档：标题层级和表格结构被拍平（canvas 渲染，拿不到结构）。
  图片和正文位置对不上，**统一附在文末**，不代表它在原文中的位置
  （`meta.structure_note` 里有记录；企微那篇另有 `meta.image_placeholder_count=23`，
  正文里的 `\x08` 占位数可供以后做对齐用，本轮没做对齐——宁可位置未知，也不要错配到别的章节）。
- `page.html` 在虚拟滚动下只是局部快照（`meta.html_snapshot_is_partial=true`），
  要重解析请用 `blocks.json`。

## 下一步

爬下来的只是原文，还没进知识库。后续走文档挖掘链路（参考 `docs/mercado_mx_help_crawl_task.md`），
`category_name` 直接用目录里的平台名。图片较多的几篇建议开多模态 OCR，
因为这批攻略的关键信息（后台路径、字段名）大量在截图里。

## 相关文件

| 文件 | 说明 |
|---|---|
| `knowledge_crawler_tool/web_crawl/login_doc_crawler.py` | 爬取器 |
| `knowledge_crawler_tool/data/payoneer_olive_doc_urls.json` | 文档清单 |
| `tests/test_login_doc_crawler.py` | 离线单测（33 个） |
| `function_schema/login_doc_crawler.*.md` | 函数 schema |
