# knowledge_clear_by_dify_model_longcontent.parse_answer

## 描述
解析 Dify QA 抽取模型返回文本，转换为 QA JSON 列表。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| answer | str\|None | 是 | Dify 返回文本；为空或非字符串时返回空列表 |
| from_file_name | str | 是 | 来源文件名 |
| pages | list[int] | 是 | 当前 QA 抽取段落页码范围 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 每项包含 `q`、`a`、`from_file_name`、`from_page` |

## 行为
- 支持 `问题:...答案:...` 格式，**半角 `:` 与全角 `：` 都接受**。
- 支持大小写不敏感的 `q:...a:...` 格式（同样兼容全角冒号）。
- 支持用 `###` 分隔多个 QA 块。
- `answer` 为空或非字符串时仅记录 warning，不抛异常。

### 为什么必须兼容全角冒号（2026-08-08 实际踩到）

模型输出的冒号形态**不稳定**：同一批 26 个页面里，25 个用半角 `问题:`，FAQs 那页用了全角 `问题：`。
原正则只写了半角，导致该页解析出空列表，进而 `add_quality_info_to_qa_json` 拿到空文本调 Dify
抛 `ValueError: inputs is empt`，**整页 QA 静默丢失而任务仍报成功**
（task `9e92dc27cd9efc6185ce3b06bb529c99`，26 页只产出 25 页）。

判断依据：该页日志里「问题：」全角出现 24 次、半角 0 次，且「无法解析问答对」恰好 1 次。

## SQL
不读写数据库。
