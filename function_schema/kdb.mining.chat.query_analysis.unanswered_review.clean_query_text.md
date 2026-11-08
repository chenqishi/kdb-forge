# kdb.mining.chat.query_analysis.unanswered_review.clean_query_text

## Signature

`clean_query_text(text: str) -> str`

## Description

剥掉群聊 @机器人 消息的格式噪声，取出真正的问题文本。

典型形态：真实问题包在 `「」` 里 + 尾部 ` - - - - - @Wayfair AI助理(运营指导)(🤖)`。
不清洗会污染检索词并白烧 LLM token。

清洗顺序（**顺序不能反**）：
1. 砍尾部 `- - - -` 分隔线及其后内容（后面挂的是被 @ 的机器人名）
2. 剥 `@昵称(角色)(🤖)` 形态的提及
3. 脱 `「」`/引号包裹

已知坑：`@` 出现在收尾 `」` 之前时，第 2 步会连带弄丢 `」`，只剩前引号，
故补「孤立前引号」规则；但引号内仍有引号时不脱，避免吃掉正文。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 原始消息文本 |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 清洗后的问题文本；整条只有一个 @机器人 时返回空串（调用方应跳过） |

## SQL

无。

## Source

`src/kdb/mining/chat/query_analysis/unanswered_review.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
