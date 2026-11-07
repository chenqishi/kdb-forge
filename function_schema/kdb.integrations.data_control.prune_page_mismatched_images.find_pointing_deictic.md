# kdb.integrations.data_control.prune_page_mismatched_images.find_pointing_deictic

## Signature

`find_pointing_deictic(content: str, marker_start: int, window: int=DEFAULT_WINDOW) -> Optional[str]`

## Description

判断某个图片标记前面有没有话术指着它（「如下图所示」这类）。

## Inputs

- `content` (str)
- `marker_start` (int) — `[multimodal_prefix]` 标记在 content 里的起始下标
- `window` (int, 默认 60) — 话术结束位置到标记起点的最大字符距离

## Outputs

`Optional[str]` — 指着它的话术原文，没有返回 None。

## 判据为什么是三条联合

单靠正则会误删正文，单靠距离会误判，必须一起用：

1. **词边界**：`图中` 会撞上 `主视图中` / `屏幕截图中` / `产品白底图中`，
   这三个都不是指图话术。用 `_BAD_PREFIX_CHARS` 看前一个字排除。
   `如下图所示` / `见下图` / `下方海报` 这类本身就是完整话术，不需要边界判断。
2. **邻近有图片标记**：正文里 `[multimodal_prefix]<path>` 就嵌在图片出现的位置，
   误报（`在一个视图中查看` / `本文着陆页面部分截图中的编号 6`）距离 d=+272 ~ +582。
3. **中间不夹别的标记**：否则一串图里最前面那句话术会被算成指着每一张图。

由 `orphan_deictic` 单独报出来交人工，不自动改。

## SQL

无。

## 测试

`tests/test_prune_page_mismatched_images.py`

## Source

`src/kdb/integrations/data_control/prune_page_mismatched_images.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
