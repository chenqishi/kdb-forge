# QaQualityFilter.request_dify

## 所属文件
`chat_qa_extract/quality_filter.py`

## 功能描述
Dify workflow「qa选择过滤」（`data/qa选择过滤.yml`）的本地实现，给编号后的 QA 清单逐条打质量标签。

## 与原 Dify 流的差异（都是为了修实际踩到的坑）

| 维度 | 原 Dify 流 | 本地实现 |
|---|---|---|
| 分块 | 无，整份清单一次调用 | 按 `batch_size`（默认 40）分批 |
| 条数校验 | 无 | 每批产出条数必须等于投入条数，不等先重试 |
| 对齐失败兜底 | 无，整批错位 | 该批退化为「原文无标签」，损失限制在本批 |
| 模型 | google/gemini-2.5-flash-lite | 配置 `models.quality`，默认 google/gemini-2.5-flash |
| 客户定制 | 无 | `prompts/quality.<client>.md` 追加规则 |

**为什么必须做条数对齐**：下游 `commons.qa_text_tools.parse_qa_quality_result`
**忽略模型打印的序号**，按出现顺序重新编号；
`quality_tools.qa_quality_tools.add_quality_info_to_qa_json_by_dify` 里
`if i + 1 in quality_info` 取不到就把 `quality_info` 置空 → 强制降级 mid。
所以模型少回一条，其后全部错位降级。实测同批任务打标率 0.4%~99% 不等。

## Inputs
构造函数：
- `client` (str|None) — 命中 `prompts/quality.<client>.md`
- `model` (str|None) — 默认取配置 `models.quality`
- `batch_size` (int) — 每批 QA 条数，默认 40
- `max_retries` (int) — 单批条数对不上时的重试次数，默认 2
- `max_tokens` / `temperature` / `timeout` / `usage_out`

`request_dify(paragraph, other_inputs=None)`：
- `paragraph` (str) — `commons.schema_trans.qajson_to_line_text(qa_list, add_index=True)`
  生成的编号清单，格式 `1.问题:xxx\n答案:yyy\n###\n2.问题:...`

## Outputs
- `str` — 条数与输入一致、可被 `parse_qa_quality_result` 顺序解析的带标签文本
- `None` — 输入解析不出任何 QA

## 标签体系
沿用原流的 `#优质` / `#不清晰` / `#无实质答案` / `#不可信` / `#需要修改` / `#不相关` / `#重复-{index}`，
joint_login 增强规则新增 `#不通用`（只对某个具体店铺/客户/单据成立的个案问答）。

`#不通用` 已加入 `quality_tools.qa_quality_tools.LOW_QUALITY_TAG`，会直接降到 low 而不是留在 mid。

## SQL
无 SQL 读写。

## 注意
- 分块后跨批的重复检测失效（`#重复-{index}` 只在批内有效）。这是可接受的取舍：
  上游 `deduplicate_qa_list` 和下游 `re_group_qa_list` 已经在做字符级去重。
- 块内保留**全局**序号，所以 `#重复-{index}` 引用的就是全局序号，无需再映射。
