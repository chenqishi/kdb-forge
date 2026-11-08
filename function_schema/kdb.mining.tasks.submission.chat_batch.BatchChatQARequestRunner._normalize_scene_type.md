# kdb.mining.tasks.submission.chat_batch.BatchChatQARequestRunner._normalize_scene_type

## Signature

`_normalize_scene_type(self, scene_type, app_id)`

## Description

校验并规范化从 `rf_ai_role_config.chat_mining_scene_type` 读到的挖掘场景配置值。缺失或非法时退回 `'group'`，保持"只挖群聊"的历史默认行为。

## Inputs

- `self` — `BatchChatQARequestRunner` 实例
- `scene_type` (str | None) — 数据库里的原始配置值，可能为 `None`、空串、大小写混杂、带空格、顺序颠倒
- `app_id` (int | str) — 仅用于日志定位

保留参数签名 `self, scene_type, app_id`。输入结构、CLI位置参数与原实现一致。

## Outputs

- `str` — 规范化后的场景，取值只会是 `'group'` / `'single'` / `'group,single'`

保持当前同名函数的返回类型、异常、轮询超时、HTTP请求体、成功水位推进与报告格式。正式入口为 `python -m kdb.mining.tasks.submission.chat_batch`；全部依赖来自当前 kdb 包。

## 规范化规则

1. 空值（`None` / `''`）→ `'group'`
2. 按 `,` 切分、去空格、转小写
3. 按固定顺序 `group` → `single` 重新拼接，所以 `'single,group'`、`'Group, Single'` 都归一成 `'group,single'`
4. 结果不在白名单 `VALID_SCENE_TYPES` 内 → 记 `warning` 日志并返回 `'group'`

## SQL

无直接 SQL 读写。输入来源见 `batch_run_chatqa_request.get_enabled_appids.md`。

## 为什么需要白名单

下游 `src/kdb/mining/chat/sources/sql.py:106-116` 的判定是：
```python
has_group = 'group' in scene_types
has_single = 'single' in scene_types
if has_group and not has_single:   sql += " AND is_group = 1"
elif has_single and not has_group: sql += " AND (is_group = 0 OR is_group IS NULL)"
# 两者都为 False 时不追加任何条件
```
即写错一个词（比如 `'groups'`）不会报错，而是**静默取消群聊/单聊过滤**，把两类数据全挖进来。白名单把这种静默扩大化挡在下发之前。

## SQL / ES

本函数无直接 SQL；应用数据由 get_enabled_appids 读取 rufitai.rf_ai_role_config： id/app_id/config_key/config_value/is_enabled/del_flag；rf_app_info: id/customer/application_name/is_enabled/del_flag。来源为当前同名函数中原SQL；不新增SQL表/字段/写入。任务状态API/挖掘索引操作仍由原服务执行。

## 原业务契约

# _normalize_scene_type

## Source

`src/kdb/mining/tasks/submission/chat_batch.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
