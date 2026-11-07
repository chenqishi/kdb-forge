# joint_login（用户口述 "joint_client"）有大量对话但没学到知识 — 排查结论

日期：2026-07-30
排查方式：生产机 `main` 只读（SELECT + 日志 + ES count），未做任何写入。

## 结论一句话

**是原因①：`chat_qa_mining` 从来没有为这个客户跑过**，因为 `rufitai.rf_ai_role_config` 里压根没有这个客户的 `timing_run_chat_mining` 开关行，定时任务的候选 SQL 自然选不到它。
**不是原因②**：数据侧非常健康，7 月共 24596 条对话、群聊 23249 条，全局昵称黑名单只杀掉 53 条，同事（peer）发言量充足，完全具备可挖掘的素材。

## 名称更正（重要）

系统里**没有** `joint_client` 这个 client。实际客户名是 **`joint_login`**，`rf_app_info` 下有 7 个 app：

| app_id | application_name |
|---|---|
| 2074737571209482242 | joint_login_joint_login_0_we_com |
| 2074754245782474753 | joint_login_joint_login_demo_cm |
| 2074770753334087681 | joint_login_joint_login_Clara_1_we_com |
| 2074771379111661570 | joint_login_joint_login_2_we_com |
| 2074771724231577602 | joint_login_joint_login_3_we_com |
| 2074771967962583042 | joint_login_joint_login_4_we_com |
| 2075038472591708162 | joint_login_joint_login_5_we_com |

ES 里 `joint_login` 索引**存在但是 0 条文档**；`joint_client` 索引不存在。

## 证据链

### 1. 定时任务本身是正常的（排除"服务/cron 挂了"）

```
crontab: 00 12,18 * * * .../control_script/timing_run_task_gen_knowledge_by_send_request.sh
data/chatknowledge/run_timing_record.txt 末行: 20260730122312   # 今天 12:23 刚跑过
localhost:6000 有响应
最近一次运行处理了 23 个 app_id，全部跑完
```

今天实际被挖掘的 client：`mercado`、`mercado_local`、`mars_mind`、`wayfair`、`individual_20`、`payoneer`、`qooten`。**没有 `joint_login`。**

### 2. 开关行根本不存在

`joint_login` 的 7 个 app 在 `rf_ai_role_config` 里只有 `peer` 和 `hosting_status` 两种 config_key，**没有任何 `timing_run_chat_mining` 行**。

而 `control_script/batch_run_chatqa_request.py:86-100` 的候选 SQL 是：

```sql
SELECT DISTINCT rc.app_id, ai.customer AS client, ai.application_name AS user
FROM rufitai.rf_ai_role_config rc
LEFT JOIN rufitai.rf_app_info ai ON rc.app_id = ai.id
WHERE rc.config_key = 'timing_run_chat_mining'
  AND rc.config_value = '1'
  AND IFNULL(rc.is_enabled,1) = 1
  AND IFNULL(rc.del_flag,0) != 1
  AND rc.app_id IS NOT NULL
  AND IFNULL(ai.is_enabled,1) = 1
  AND IFNULL(ai.del_flag,0) != 1
```

没有这行 → 永远不进候选集 → 永远不发任务。

### 3. 历史上一次任务都没起过

```sql
SELECT ... FROM rufitai.dops_task_kggen_info WHERE client='joint_login';
-- rowcount: 0
```

### 4. 数据侧是健康的（排除原因②）

`data_chat_history` 中 `customer='joint_login'`，按 stage1 实际会施加的过滤逐层数（窗口 2026-07-01 ~ 2026-07-30）：

| 层 | 条件 | 条数 |
|---|---|---|
| L1 | `customer='joint_login' AND del_flag!=1` | **24596** |
| L2 | `+ is_group = 1`（`scene_type` 默认 group） | **23249** |
| L3 | `+ 全局昵称黑名单 15 个 NOT LIKE` | **23196** |

黑名单只有 `石` 这一个 token 命中，杀掉 53 条，可以忽略。

各 app 的分布（全时间，2026-07-13 起有数据）：

| app_id | 群聊 | 单聊 | 最后一条 |
|---|---|---|---|
| 2074770753334087681 | 7126 | 420 | 2026-07-30 16:31 |
| 2074771379111661570 | 8534 | 249 | 2026-07-30 16:32 |
| 2074771724231577602 | 7589 | 676 | 2026-07-28 08:53 |
| 2074754245782474753 | 0 | 2 | 2026-07-08 |
| 其余 3 个 app | 0 | 0 | — |

发言量 top 的发送人（`王思摇`、`Clara`、`朱柏豪`、`揭素蓉`、`曾俊琳`、`林晓丹`、`袁范庆` 等）**正是 `peer` 配置里的同事名单**，所以 prompt 里"只有同事的回答可以作为答案"这条规则有充足素材，不会出现历史上 `746a5a7d…` 那种"同事发言被黑名单删光 → 每个群返回 all null"的情况。

群聊房间数量多且集中（top 房间 1977 / 1545 / 1433 条），`other_user_nickname` 是企业微信群 ID（纯数字），不会误撞黑名单的群名精确匹配。

## 已执行的修复（2026-07-30）

### 1. 代码：定时任务支持按 app 配置挖掘场景

commit `d1b7233`，已 `git pull` 到 main。

改动前 `control_script/batch_run_chatqa_request.py:154-166` 的 payload 写死不带 `scene_type`，
控制器就一律用默认 `'group'`，纯单聊或群单聊混合的客户永远挖不到单聊。

改动后 `get_enabled_appids()` 用子查询按 app 读 `rf_ai_role_config.chat_mining_scene_type`，
经 `_normalize_scene_type()` 白名单校验后写进 payload。**未配置该 key 时返回 `'group'`，
所有既有客户行为不变**（上线后实测：候选 23 → 26 个 app，只有新增的 3 个是 `group,single`，
其余 23 个仍是 `group`）。

白名单校验是必需的：下游 `get_data_from_sql.py:106-116` 只识别 `group`/`single` 两个词，
两个都不命中时**不追加任何过滤条件**，即写错一个字母会静默把群聊单聊全挖进来。

配套：`function_schema/batch_run_chatqa_request.{get_enabled_appids,_normalize_scene_type,create_task_request}.md`，
单元测试 `tests/test_chat_mining_scene_type.py`（14 个用例通过）。

### 2. 数据库：给 3 个有数据的 app 加开关

```
id 1022/1024/1026  timing_run_chat_mining = '1'            BOOLEAN
id 1023/1025/1027  chat_mining_scene_type = 'group,single' TEXT
app_id: 2074770753334087681 / 2074771379111661570 / 2074771724231577602
client: joint_login
```

另外 4 个 app 没有聊天数据，未开启。

### 3. 首跑：手动发 3 个任务（最近 7 天窗口）

```
517c14ac49bdc8a26861fc19126ac00b  app 2074770753334087681
14457e6cd000a5fd493028a95a17dcf1  app 2074771379111661570
224b5f62b11899baf00ed9f5ec4939a9  app 2074771724231577602
窗口 2026-07-24 00:00:00 ~ 2026-07-30 23:59:59
scene_type=group,single  mining_type=normal  index_name=joint_login
```

**为什么不跑全量窗口**：挖掘是"一个房间的整个时间窗 = 一次 Dify 调用"，不分块
（`gen_knowledge_from_chat.py:119-139`）。全量 7/13-7/30 窗口下最大房间已达 **114904 字符**，
贴着 Dify 128k 分段上限——MEMORY 记过这个坑会返回 400 然后 `parse_dify_segment(None)` 抛
`TypeError` 把整个任务带挂。7 天窗口最大 41k，安全。

**7/13 ~ 7/23 的存量需要另外按周切片补跑**：定时任务不会自动覆盖它，因为 `appid_record.txt`
里没有这 3 个 app 的水位线，cron 首跑会用全局 `run_timing_record.txt` 的水位（已经是 7/30 12:23）。

首跑实测（任务 `517c14ac`）：

| 环节 | 结果 |
|---|---|
| chat_data.txt | 3436 行（**群聊 3176 + 单聊 261**，单聊按旧默认会被全丢） |
| robot_room_type_config 第 4 列 | `normal`，未踩 `norm` 的 `ValueError` |
| 抽取 QA | 1182 条 |
| `all null` 房间 | 49（约 120 个房间中，寒暄/事务性房间抽不出 QA 属正常） |
| 入库前 search_data | 427 行 = high 419 / mid 3 / low 5 |

抽出的是真业务知识，例如"请提供收款账号"对应企业公户 + PingPong 服务商付款两种路径。

## 原始修复建议（保留备查）

给有数据的 3 个 app 加开关行即可，参照现有 `mercado` 的行结构：

```sql
-- 参考行：id=910, config_key='timing_run_chat_mining', config_value='1',
--        config_type='BOOLEAN', client='mercado', permission=1, version=1,
--        is_enabled=1, del_flag=0,
--        description='是否开启定时chatqa挖掘1/开启0关闭'
INSERT INTO rufitai.rf_ai_role_config
  (config_key, config_value, config_type, app_id, client, permission, version,
   create_user_id, create_time, is_enabled, del_flag, description)
VALUES
  ('timing_run_chat_mining','1','BOOLEAN', 2074770753334087681,'joint_login',1,1,1,NOW(),1,0,'是否开启定时chatqa挖掘1/开启0关闭'),
  ('timing_run_chat_mining','1','BOOLEAN', 2074771379111661570,'joint_login',1,1,1,NOW(),1,0,'是否开启定时chatqa挖掘1/开启0关闭'),
  ('timing_run_chat_mining','1','BOOLEAN', 2074771724231577602,'joint_login',1,1,1,NOW(),1,0,'是否开启定时chatqa挖掘1/开启0关闭');
```

注意：这张表通常由前端配置页维护，**优先走前端开关**，直接写库是兜底手段。

开启前的注意事项：

1. **首次窗口会很大**。`appid_record.txt` 里没有这 3 个 app 的水位线，首跑会用全局 `run_timing_record.txt` 的起点，一次性吃掉 2 万多条。建议先手动发一次带明确 `start_time/end_time` 的任务（比如只跑最近 3 天）验证产出，再打开定时。
2. **单聊会被丢掉**。定时 payload 不传 `scene_type`，控制器默认 `'group'` → SQL 加 `AND is_group = 1`，这 3 个 app 的 1345 条单聊会被忽略。如果这个客户的单聊也有价值，需要在 `batch_run_chatqa_request.py` 的 payload 里补 `scene_type`。
3. **手动发任务必须传 `mining_type='normal'`**。控制器默认值是 `'norm'`（`chat_qa_mining_task_control.py:61`），而下游 `gen_knowledge_from_chat.py:195-201` 只认 `'normal'`/`'forward'`，传错直接 `ValueError: 群类型错误`。定时脚本已经传 `'normal'`，手动调用容易踩。
4. **建议同时传 `index_name`**。payload 不传时索引名会回退到数据里的 `platform`，再空就落到 `config_es_engine.json` 的默认索引 `open_shop`——数据入了别的索引会看起来像"没学到"（`search_index_data_interface.py:1071-1076`）。

## 验证方法（开启后）

```sql
-- 任务是否起来了
SELECT task_id, task_stage, run_status, task_result, create_time
FROM rufitai.dops_task_kggen_info WHERE client='joint_login' ORDER BY create_time DESC LIMIT 5;
```

```bash
T=<task_id>
wc -l data/off_task_data/$T/chat_data.txt \
      data/off_task_data/$T/chatknowledege_extract_qa_quality_batch_search_data.txt
grep -c "all null" log/off_task_log/$T/qa_generation.log        # >0 说明 prompt/同事名单有问题
grep -nE "无法解析问答对|群类型错误|Traceback" log/off_task_log/$T/*.log
```

ES 侧要单独确认，**不能只看任务结果里的 `qa_num`**——`count_qa_results`（`chat_qa_mining_task_control.py:601-641`）只统计入库前文件里的 high 条数，完全不反映入库阶段按 `重复` 标签和 title 相似度 >0.95 的丢弃，所以 `qa_num` 大于 0 而 ES 是 0 是可能的。直接 count `joint_login` 索引里 `from_type=chat_auto` 的文档数。

## 2026-08-01 自动学习 QA 审核记录

`from_type=chat_auto` 入库时会归一为 `from_type_norm=auto_learning`。本次在生产 ES `joint_login` 上先 dry-run，确认自动学习 QA 共 2810 条，全部 `audit_result=-1`，质量分布为 high 1001 / mid 1676 / low 133，且全部 `data_type=qa`。

按当前自动审核脚本约定，`quality_level=high` 的自动通过状态写为 `audit_result=2`；注意旧管理 API 文档里仍有 `1=通过/2=不通过` 的历史口径。本次只更新 high QA，不处理 mid/low：

```text
query: index=joint_login AND from_type_norm=auto_learning AND from_type=chat_auto
       AND data_type=qa AND quality_level=high AND audit_result=-1
updated: 1001
failures: 0
after: audit_result=2 为 1001，audit_result=-1 剩余 1809
```

## 2026-08-01 二次自动学习 QA 审核记录

用户更新 `joint_login` 知识库后，用同一条件重新执行自动审核。执行前自动学习 QA 总量为 3284，质量分布 high 1347 / mid 1762 / low 175；其中历史 high 已通过 1001 条，本次新增 high 待审 346 条。

```text
query: index=joint_login AND from_type_norm=auto_learning AND from_type=chat_auto
       AND data_type=qa AND quality_level=high AND audit_result=-1
updated: 346
failures: 0
update_time: 2026-08-01 14:24:22
after: high audit_result=2 为 1347，high audit_result=-1 为 0；
       mid/low audit_result=-1 剩余 1937
```
