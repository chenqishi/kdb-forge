# payoneer_olive 平台类目导入

日期：2026-08-05

## 背景

`payoneer_olive` 的知识跨几十个电商平台（Chewy / Bol / Trendyol / Cdiscount …），
但类目体系里只有 `默认分组` 和一个 `TikTok Shop`，没法按平台管理知识库。
本次把橄榄枝计划各责任人负责的平台**全部建成一级类目**。

## 方法（仓库已有工具，无需新代码）

`category_sys_manager/category_sys_manager.py`：

```bash
cd category_sys_manager
python category_sys_manager.py batch_insert_category_from_file \
    --category_file=data/payoneer_olive_categories.txt \
    --client=payoneer_olive --userId=2073772203129200642
```

依赖 `fire`（本机 `pip3 install --user fire`）。

后台接口（intranet，**不需要登录 token**）：

| 用途 | 方法 | URL |
|---|---|---|
| 查类目树 | GET | `https://admin.marsmind.cc/api/rufit-ai/intranet/knowledge/qaCategory/tree?client=<client>` |
| 建类目 | POST | `https://admin.marsmind.cc/api/rufit-ai/intranet/knowledge/qaCategory/saveByIntranet` |

建类目 body：`{"client", "userId", "categoryName", "parentId"?}`；
成功返回 `code == "00000"`，`data.categoryId` 是新 ID。

### client / userId 怎么拿（不用猜）

类目树响应里每个节点都带 `client` 和 `userId`/`createUserId`。
`payoneer_olive` 已有的 `TikTok Shop` 就是该账号自己建的，直接读出来：

```json
{"categoryId":"2084519180871708674","categoryName":"TikTok Shop",
 "client":"payoneer_olive","userId":"2073772203129200642","createTime":"2026-08-04 13:57:56"}
```

→ `client=payoneer_olive`，`userId=2073772203129200642`。

### 类目文件格式

每行一个类目路径，`-` 分隔层级。父类目会被 `expand_categories_with_parents` 自动补全，
`sort_categories_by_level` 保证父先于子插入，已存在的按**完整路径**跳过。
本次全是一级，所以每行就是平台名。

## 本次结果

`category_sys_manager/data/payoneer_olive_categories.txt`，41 个平台：

```
成功插入: 41   失败: 0   跳过: 0
```

线上类目共 43 个（41 新 + `TikTok Shop` + `默认分组`），全部一级，无重名：

About You / Allegro / Amazon / BackMarket / Best Buy / BliBli / Bol / Cdiscount / Chewy /
Coupang / Falabella(Linio) / Fnac/Darty / Fruugo / Fyndiq / Gmarket / Hepsiburada / Joom /
Jumia / Kaufland / Kogan / Lazada / Lowes / ManoMano / Mercado Libre / Newegg / Nocnoc /
Noon / OTTO / OnBuy / RakutenFrance / RueDu Commerce / SHEIN / Shopee / Temu / TiendaMia /
TikTok Shop / Tradeling / Trendyol / Walmart / Wayfair / eBay / eMAG

## 坑

1. **去重是按类目名精确比对的**，不认别名。责任人清单里写的是 `Tiktok`，
   线上已有的叫 `TikTok Shop`——照抄清单会建出同一平台的两个类目。
   本次把 `Tiktok` 从文件里去掉，复用已有的 `TikTok Shop`。
   以后追加平台时，**先拉一遍类目树比对别名/大小写/空格**（`Best Buy` vs `BestBuy`、
   `RakutenFrance` vs `Rakuten France` 这类都会重复建）。
2. `-` 是层级分隔符，平台名里不能带 `-`，否则会被当成两级。本次 41 个名字都不含 `-`，
   `Falabella(Linio)`、`Fnac/Darty`、`RueDu Commerce` 的括号/斜杠/空格都没问题。
3. 接口无鉴权且直接写生产，跑之前先用 `parse_category_file` + `build_category_path_map`
   预演一遍「将要新建哪些」，别直接跑。

## 待办

类目建好了但**存量知识还没挂到类目上**。`payoneer_olive` 的 QA `title` 普遍带平台前缀
（`chewy-`、`Bol-`、`Trendyol-`），可以按前缀批量回填 `category_infos` / `primary_category`，
是下一步该做的事。
