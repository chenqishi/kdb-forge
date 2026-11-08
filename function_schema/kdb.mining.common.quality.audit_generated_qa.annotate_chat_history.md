# kdb.mining.common.quality.audit_generated_qa.annotate_chat_history

## Signature

`annotate_chat_history(chat_history: str, answer: str, colleague_names: Sequence[str]) -> Dict[str, Any]`

## Description

在群聊上下文里识别说话人，标出哪些是同事（peer 名单），并猜测**答案出自谁**——
给 LLM 提供「答案是不是客户自己说的」这个判定的事实依据。

## Inputs

- `chat_history` (str) — `ext_info.from_chat_history` 原文
- `answer` (str) — 知识的 `content`
- `colleague_names` (List[str]) — `extract_colleague_names` 的产物

## Outputs

`Dict`：

| 字段 | 说明 |
|---|---|
| `speakers` | `[{'name', 'is_colleague', 'lines'}]`，按发言行数降序 |
| `colleagues_in_chat` | 本段对话里命中名单的昵称，喂给 prompt（**不注入全量名单**，省 token）|
| `answer_speaker` | 猜到的答案说话人昵称，猜不到为 `''` |
| `answer_speaker_is_colleague` | `True` / `False` / `None`（猜不到）|
| `match_score` | 答案与该发言行的 dice 相似度，`< 0.6` 视为没猜到 |

## 匹配口径

- 说话人行：正则 `^(名字) : ` / `^(名字): `（群聊导出格式，见样例
  `Rodman LUO(橄榄枝计划小助手 Rodman Luo) : "..."`、`赵samsam: ...`）；
  跳过 `<sysmsg>` 这类系统 XML 块。
- 是否同事：昵称和 peer 名单都归一化（去标点空格、转小写）后做**子串包含**——
  群昵称普遍是 `Stacy Yao@橄榄枝计划 出差中回复慢` 这种带后缀的，精确相等匹配不上。
- 答案说话人：答案文本经过抽取时的改写，不能指望原样出现，用
  `common_utils.context_dice` 取最相似的发言行，`>= 0.6` 才算数。

## 已知边界

名单只覆盖 Payoneer 同事。群里还有**平台官方招商经理**（`allegro招商经理小南`、
`沃尔玛官方经理Catherine`）——他们不在 peer 名单里但答案同样权威，
所以 `answer_speaker_is_colleague=False` **不能直接判死**，只作为线索交给 LLM，
prompt 里明确写了这一条。

## SQL

无。

## Source

`src/kdb/mining/common/quality/audit_generated_qa.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
