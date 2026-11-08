# kdb.mining.web.crawlers.discover_links.discover

## Signature

`discover(entry: str, max_pages: int=300, depth: int=2) -> List[str]`

## Description

从入口页 BFS 发现同站链接，供没有 sitemap 的平台使用。

## Inputs

- `entry` (str): 入口 URL，如 `https://seller.onbuy.com`
- `max_pages` (int, 默认 300): 最多保留的候选页数
- `depth` (int, 默认 2): BFS 层数

## Outputs

- `List[str]`: 同域、路径命中 `_KEEP` 关键词、且未被 `_DROP` 排除的 URL，已排序去重

## 说明

- 只收同域链接；`_KEEP` 覆盖中/英/波兰/德/法/土耳其语的"帮助/卖家/入驻"路径词
- `_DROP` 排除商品页、登录、法务、静态资源
- 产出喂给 `crawl_url_list.py --url-file`

## SQL

无数据库读写。

## Source

`src/kdb/mining/web/crawlers/discover_links.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
