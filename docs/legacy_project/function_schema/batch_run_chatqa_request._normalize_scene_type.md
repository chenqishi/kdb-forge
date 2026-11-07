# _normalize_scene_type

## 所属文件
`control_script/batch_run_chatqa_request.py`

## 功能描述
校验并规范化从 `rf_ai_role_config.chat_mining_scene_type` 读到的挖掘场景配置值。缺失或非法时退回 `'group'`，保持"只挖群聊"的历史默认行为。

## Inputs
- `self` — `BatchChatQARequestRunner` 实例
- `scene_type` (str | None) — 数据库里的原始配置值，可能为 `None`、空串、大小写混杂、带空格、顺序颠倒
- `app_id` (int | str) — 仅用于日志定位

## Outputs
- `str` — 规范化后的场景，取值只会是 `'group'` / `'single'` / `'group,single'`

## 规范化规则
1. 空值（`None` / `''`）→ `'group'`
2. 按 `,` 切分、去空格、转小写
3. 按固定顺序 `group` → `single` 重新拼接，所以 `'single,group'`、`'Group, Single'` 都归一成 `'group,single'`
4. 结果不在白名单 `VALID_SCENE_TYPES` 内 → 记 `warning` 日志并返回 `'group'`

## SQL
无直接 SQL 读写。输入来源见 `batch_run_chatqa_request.get_enabled_appids.md`。

## 为什么需要白名单
下游 `data_control_tools/get_data_from_sql.py:106-116` 的判定是：
```python
has_group = 'group' in scene_types
has_single = 'single' in scene_types
if has_group and not has_single:   sql += " AND is_group = 1"
elif has_single and not has_group: sql += " AND (is_group = 0 OR is_group IS NULL)"
# 两者都为 False 时不追加任何条件
```
即写错一个词（比如 `'groups'`）不会报错，而是**静默取消群聊/单聊过滤**，把两类数据全挖进来。白名单把这种静默扩大化挡在下发之前。
