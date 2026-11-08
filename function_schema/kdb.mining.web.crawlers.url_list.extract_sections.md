# kdb.mining.web.crawlers.url_list.extract_sections

## Signature

`extract_sections(raw: str) -> List[Tuple[str, str]]`

## Description

按 `<h1>~<h4>` 把 HTML 切成 (小节标题, 小节正文) 列表。

## Inputs

- `raw` (str): 原始 HTML

## Outputs

- `List[Tuple[str, str]]`: (小节标题, 小节正文)，已剔除 cookie/隐私同意小节

## 说明

- 先用 `_strip()` 去掉 script/style/nav/footer/header
- **剔除 cookie/隐私同意小节**（`_CONSENT_RE`，覆盖 en/pl/de/fr）：
  不剔掉会让每篇文档的第一个块都是同意横幅，检索时大面积召回噪声
- 下游按 `## 小节` 切块，块向量才代表该小节主题

## SQL

无数据库读写。

## Source

`src/kdb/mining/web/crawlers/url_list.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
