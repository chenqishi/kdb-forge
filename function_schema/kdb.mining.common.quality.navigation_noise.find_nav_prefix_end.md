# kdb.mining.common.quality.navigation_noise.find_nav_prefix_end

## Signature

`find_nav_prefix_end(content, tail_markers=None, max_prefix_ratio=0.5, max_prefix_chars=3000)`

## 功能

定位段落正文开头那段**站点导航样板**的结束位置。

firecrawl 抓 markdown 时会把站点的 cookie 横幅 + 左侧导航一并放在每页正文开头，
段落切分时正好切到页首的那一块就会带上这段样板。

结构固定为 `cookie 横幅 → 关闭 → 入门 → 各导航链接 → 资源 → 常见问题解答 → 词汇表 → 正文`。

## Inputs

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| content | str | 是 | - | 段落正文 |
| tail_markers | list[str] | 否 | `['posts/glossary)']` | 能唯一命中导航块**最后一行**的串，正文从下一行开始 |
| max_prefix_ratio | float | 否 | `0.5` | 安全阀：定位到的前缀超过全文该比例则判定不可信，返回 `None` |
| max_prefix_chars | int | 否 | `3000` | 安全阀：前缀绝对长度上限 |

## Outputs

| 类型 | 说明 |
|------|------|
| int / None | 正文起始偏移；无法可靠定位时返回 `None`（调用方必须跳过该条，不得瞎切） |

## 逻辑说明

1. 取 `tail_markers` 中**最后一次**出现位置最大的那个（导航块在开头，正文里也可能再提到"词汇表"，
   所以用 `rfind` 后还要过安全阀）
2. 找不到任何 marker → 返回 `None`
3. 正文起点 = 该行行尾 + 1
4. 触发任一安全阀（超过 `max_prefix_ratio` 或 `max_prefix_chars`）→ 返回 `None`
5. 剩余正文为空或过短（< 50 字符）→ 返回 `None`

## 为什么用 URL 而不是链接文字定位（实际踩到）

一开始用链接文字 `词汇表` 定位，结果**词汇表页面**的正文标题本身就是 `**词汇表**`，
`rfind` 落到正文标题上，把正文首行 `**词汇表**\n* * *` 一起切掉了。
改用导航链接的 URL `posts/glossary)` 后，27 条里 26 条前缀统一为 764（原先该条是 778），
正文标题完整保留。

**教训：定位样板边界要用只可能出现在样板里的特征（URL、结构标记），不要用正文也会出现的词。**

## 为什么要安全阀

这些段落**不是纯样板**，剥离后仍有 1038~2777 字符实质内容（例如完整的沙盒测试操作指南）。
一旦定位错误就会切掉真知识，所以宁可返回 `None` 让人工处理，也不做没把握的切割。

## 依赖的外部接口

无。纯函数。

## SQL

无。

## Source

`src/kdb/mining/common/quality/navigation_noise.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
