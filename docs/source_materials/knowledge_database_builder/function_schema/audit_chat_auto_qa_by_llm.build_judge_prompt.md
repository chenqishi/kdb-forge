# build_judge_prompt

## 所属文件
`data_control_tools/audit_chat_auto_qa_by_llm.py`

## 功能描述
拼一条 QA 的审核 prompt（单条判定，不分块——上下文平均 1.3k 字符、最长 3.6k，
不能像 `relabel_qa_quality_by_llm` 那样 20 条一批塞进去）。

## Inputs
- `doc` (Dict) — 含 `title` / `content` / `chat_history`
- `annotation` (Dict) — `annotate_chat_history` 的产物
- `max_history_chars` (int, 默认 4000) — 上下文截断上限，从**尾部**保留（答案在结尾）

## Outputs
`str` — 用户消息全文。要求模型输出**单个 JSON 对象**：

```json
{"business_related": true, "generic": true, "answer_source": "colleague|customer|official|unknown",
 "verdict": "keep|downgrade", "tags": ["不通用"], "reason": "≤50字"}
```

## 三个判定维度（用户本轮明确要求）
1. **业务相关**：橄榄枝计划 = 帮卖家入驻/运营海外电商平台，问的得是平台规则、资质材料、
   费用时效、操作步骤这类；闲聊、内部事务、其它业务无关内容 → 不相关。
2. **通用**：换个卖家换个店铺依然成立；问卖家自己的经营数据/私事 → 不通用。
   反例（用户点名的）：`Bol-你能告诉我过去一年我们所有店铺的GMV和单店铺销售额吗？`
   → 答案是卖家自报的 GMV，纯个案私有数据。
3. **答案来源**：答案是同事/平台官方经理说的才可信；**答案是卖家自己说的 → 不可信**，
   即使内容看着像知识（卖家可能说错、也可能只是在描述自己的情况）。

## SQL
无。

## 2026-08-28：从人工审核日志学到的两条补充判据

`t_sys_oper_log` 里能精确还原每个人点过哪些知识
（`username` + `request_url=/rufit-ai/knowledge/maintenance/audit`（通过）
或 `/batchDelete`（删除），`request_params` 里是完整的 `documentId` 列表）。
Chewy 那轮是 **helen 逐条审 high**（通过 359 / 删除 825）、
**stacy 清理低质量**（删 2755 条里 99.2% 是 low/mid）——两人混在一起会把信号稀释掉
（配对判别 55%，只用 helen 的数据是 65%）。

盲标 300 条（各 150）看 helen 的取舍特点：

| 特征 | 她通过 | 她删掉 |
|---|---|---|
| scope=平台通用规则 | 38.7% | 30.0% |
| scope=操作细节 | 60.7% | 68.7% |
| 口语化追问（是吧/对吧/还是说）| 29.3% | 38.0% |
| 答案含不确定措辞 | 16.0% | 22.7% |
| 需要上一句才看得懂 | 6.0% | 10.7% |

据此 prompt 加了：
1. **新维度 `is_rule`**——脱离那次对话还算不算一条规则。不是规则（当次的临场操作指引）降 mid。
2. `generic` 补「口语化追问」「依赖上一句」两类。
3. `substantive` 补「含糊措辞不是定论」（应该/大概/可能/建议你再确认）。
