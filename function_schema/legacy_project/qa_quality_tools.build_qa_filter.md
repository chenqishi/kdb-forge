# build_qa_filter / run_batch_add_dify_quality_and_resplit

## 所属文件
`quality_tools/qa_quality_tools.py`

## build_qa_filter

### 功能描述
构造 QA 质检客户端，优先用本地 `chat_qa_extract`，凭证缺失时回落原 Dify 流。

### Inputs
- `dify_qa_filter_name` (str) — 回落 Dify 时用的 key 名，默认 `'dify_qa_filter'`；
  聊天挖掘链路传 `'chatknowledge_qa_filter_for_chathistory'`
- `client` (str) — 客户名，命中 `chat_qa_extract/prompts/quality.<client>.md`

### Outputs
- 具备 `.request_dify(paragraph)` 接口的对象：`QaQualityFilter` 或 `DifyWorkFlowRequest`

## run_batch_add_dify_quality_and_resplit

### Inputs（新增 client 参数）
- `input_file` / `output_file` / `process_field_num` / `dify_qa_filter_name` / `flag`：原有语义不变
- `client` (str, 新增) — 透传给 `build_qa_filter`，由
  `control_service/chat_qa_mining_task_control.py` 的 stage 3 以 `--client={self.client}` 传入

### Outputs
- 逐行写出 `原字段 + \t + <qa_info_file>_dify_quality_and_resplit.<suffix>`

## 质量分级常量

```python
HIGH_QUALITY_TAG = {'优质', '高质量'}
MID_QUALITY_TAG  = {'无法判断'}
LOW_QUALITY_TAG  = {'不相关', '无实质答案', '不通用'}   # '不通用' 为本次新增
```

`'不通用'` 表示只对某一个具体店铺/客户/单据成立的个案问答。这类内容进库只会污染检索，
所以与 `'不相关'` 同级直接降 low，而不是留在 mid。

判 high 的条件（`add_quality_info_to_qa_json_by_dify`）不变：
`'优质' in quality_info and group_qa_count == 1`。

## SQL
无 SQL 读写。
