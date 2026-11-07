# process_normal_group_data

## 所属文件
`chatknowledge/gen_knowledge_from_chat.py`

## 功能描述
把一个普通群（`group_type='normal'`）在整个任务时间窗内的聊天记录拼成**一次** Dify 请求，解析返回的问答对。

## Inputs
- `group_name` (str) — 群名/群 ID，来自 `original_info.other_user_nickname`，取不到时回落 `other_user_id`
- `platform` (str) — 平台名，等于任务的 `index`；`'mix'` 时走带属性解析
- `group_chat_list` (list[dict]) — 该群的消息，每条含 `send_user` / `content` / `message_time`
- `group_white_list` (list) — 白名单（当前拼 prompt 时未使用）
- `dify_model` (`DifyWorkFlowRequest`) — 已注入 `system_prompt` 的 Dify 客户端

## Outputs
- `list[dict]` — 问答对，每条含 `q` / `a` / `source` / `from_file_name` / `group_name` / `platform`
- **Dify 返回空（None 或空串）时返回 `[]`**

## 关键行为

### prompt 拼装
```
在群[{group_name}]中，有以下聊天记录：
{send_user}: {content}
------
{send_user}: {content}
```
分隔符 `'\n------\n'`（8 字符）。所以单群 prompt 长度 ≈
`Σ(len(send_user) + 2 + len(content) + 8) + len(group_name) + 20`。

**没有任何分块**：一个群整个时间窗就是一次调用，时间窗越长 prompt 越大。发起大窗口任务前
必须先按这个公式估算最大群的 prompt 长度，超过 Dify 输入上限会请求失败。

### 空返回保护
`request_dify` 在超时 / 重试耗尽 / workflow `status == failed` 时返回 `None`。
本函数在解析前短路返回 `[]`，与 `process_forward_group_data` 的 `if not result: continue` 一致。
若不短路，`qa_text_tools.parse_qa_answer(None)` 会在 `answer.replace('：', ':')` 处抛
`AttributeError`，并沿 `process_one_group_data` 向上冒泡。

## SQL
无直接 SQL 读写。消息来源见 `data_control_tools/get_data_from_sql.py` 产出的 `chat_data.txt`。
