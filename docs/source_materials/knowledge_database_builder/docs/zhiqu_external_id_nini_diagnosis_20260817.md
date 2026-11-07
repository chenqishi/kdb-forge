# 致趣 external_id 关联排查：「美客多跨境小助手妮妮的好友都没关联到 external_id」（2026-08-17）

## 结论速览

| # | 判断 | 结论 |
|---|---|---|
| 1 | 是不是妮妮的机器人配置丢了？ | **不是**。16 个助手一个不少，妮妮在配置里，uid/昵称都对，也没有新增助手漏配 |
| 2 | 致趣映射 cron 是否正常？ | **已挂 17 天**。`/mochat/open-api/contact/list` 被取消授权，2026-08-01 起每天失败 |
| 3 | 妮妮特有问题 | 致趣侧 owner=妮妮 的 contact 只有 27 个（rfwkt 好友 351 个，覆盖 7.7%，16 助手最低） |
| 4 | 附带问题 | 配置里 `1688857857859744` 昵称过期：`Janice AI` → 库里已改名 `美客多跨境小助手娜娜` |

排查所在机器：**vocn2**（cron + `/inner_external_user_id_map` 服务都在这台，不是 main）。
`main` 上没有 `config/zhiqu_*`，别去 main 找。

## 1. 妮妮的配置在，没丢

`/root/knowledge_database_builder/config/zhiqu_assistant_id_map.json`（mtime 2026-06-30）：

```json
{"nick_name": "美客多跨境小助手妮妮",
 "rfwkt_we_com_user_id": "1688856365770381",
 "zhiqu_employee_user_id": "woswaxEAAAY4Oqmg6yvA8bgq43kosggw"}
```

16 个 uid 与 `rf_wkt_we_com_account` 逐条比对：只有 `1688857857859744` 昵称不一致（见第 4 节），
其余 15 个昵称、`del_flag=0` 全一致。corp `1970325020467087` 下含「助手/助理/AI」的账号共 14 个，
**全部在配置里**，没有新助手被漏掉。

致趣侧还有 3 个助手不在配置（`美客多跨境小助手小魏` 1136、`美客多跨境小助手小扬` 185、
`Casey (智利MLC 官方小助理)` 91，数据来自 2026-06-18 dump），但它们在 `rf_wkt_we_com_account`
里**根本不存在**（不同 corp / 未同步），属于文档里既有的 scope 限制，不是配置遗漏。

## 2. 主因：致趣 contact/list 接口被取消授权，cron 从 2026-08-01 起天天失败

```text
RuntimeError: [zhiqu][mercado] contact/list 失败 page=1:
{'code': 10004, 'msg': '此接口暂未授权，请联系客服进行开通后使用。', 'data': []}
```

- access_token 刷新是成功的 → 凭据没问题，是**这个接口的授权被取消**（2026-08-17 实测仍然如此）
- 日志：`logs/zhiqu_external_id_map_mercado_2026*.log`，08-01 起全 FAIL（08-10 那次是 0 字节空日志，也没成功）
- 最后一次成功：**2026-07-31 02:12**，当天 `inserted 5 条`
- `data_scrm_id_map` type=`zhiqu_external_id`：共 **35732** 条，`MAX(create_time)=2026-07-31 02:12:13`
- `config/zhiqu_sid_to_robots_mercado.json` mtime 也停在 07-31 02:12

按 `data_scrm.create_time` 分月看 mercado+mercado_local 的 cid 关联率，掉得很明显：

| 月份 | data_scrm cid 数 | 有 zhiqu external_id | 关联率 |
|---|---:|---:|---:|
| 2026-05 | 10685 | 9015 | 84.4% |
| 2026-06 | 4050 | 2835 | 70.0% |
| 2026-07 | 5369 | 1718 | 32.0% |
| 2026-08（cron 挂掉后） | 3222 | 418 | **13.0%** |

**所以「最近加的好友没有 external_id」对所有机器人都成立，不是妮妮独有。** 这是阻塞项：
必须先让致趣客服重新开通 `/mochat/open-api/contact/list`，否则任何补跑都拉不到数据。

## 3. 妮妮特有：致趣侧 owner 归属几乎是空的，但 cid 级其实关联上了

各助手「rfwkt 好友数」vs「致趣 contact 数」（致趣数据为 07-31 那次成功跑的产物）：

| robot | rfwkt 好友 | 致趣 contact | 覆盖率 |
|---|---:|---:|---:|
| 美客多跨境小助手小文 | 11314 | 10936 | 96.7% |
| 美客多跨境小助手萝拉 | 9201 | 9130 | 99.2% |
| 美客多跨境小助手小拉 | 7572 | 7494 | 99.0% |
| 美客多跨境小助手小唐 | 6561 | 6472 | 98.6% |
| 娜娜（配置名 Janice AI） | 5671 | 5615 | 99.0% |
| 美客多跨境小助手小贝 | 1170 | 191 | 16.3% |
| **美客多跨境小助手妮妮** | **351** | **27** | **7.7%** |

妮妮的 362 条好友关系（DISTINCT cid 351）里：

- **341 条在 `data_scrm_id_map` 里有 zhiqu sid** —— cid 层面 94% 是关联上的
- 但这些 sid 在致趣里的 owner 分布是：`Janice AI`(=娜娜) **306**、萝拉 34、小文 33、黛西 29、
  **妮妮只有 27**、莉娅 21、小唐 17……
- 后果：`/inner_external_user_id_map` 的 `robot_name` 来自 `zhiqu_sid_to_robots_*.json`，
  **按 `robot_name=妮妮` 过滤只剩 18~27 行**，看上去就是「妮妮的好友都没关联」

实测 API（`user_id=1688856365770381`，2026-01-01~2026-08-17）：262 行 / 188 个 cid，
其中 113 个 cid 有 `external_id`，`robot_name` 分布 `None` 90、`Janice AI` 89、`妮妮` 18、小文 17……

## 4. 配置里娜娜的昵称过期（Janice AI → 美客多跨境小助手娜娜）

`rf_wkt_we_com_account.1688857857859744.nick_name` 现在是 `美客多跨境小助手娜娜`，
配置里还写 `Janice AI`。影响：

- cron 写 `sid_to_robots` 用的是**配置里的昵称**，所以 API 返回的 `robot_name` 仍是 `Janice AI`
  → 业务方按「娜娜」找，一条也找不到
- email 不受影响（`nick_name → rfwkt uid` 是配置内部自洽的）

## 踩坑记录（下次排查直接照做）

1. **别去 main 找**：这套东西在 vocn2。`crontab -l | grep zhiqu` → `0 2 * * * .../zhiqu_external_id_map_cron.sh mercado`；
   API 由 vocn2 上 `single_service/csat_report_service.py --port 7100` 提供（路由 `/inner_external_user_id_map`）。
2. **API 的 `user_id` 参数是「助手 uid」不是客户 cid**（`user_id_map_query.py:153` 过滤 `data_scrm.user_id`）。
   拿客户 cid 去传会 0 行返回，容易误判成「全都没关联」。文档示例里的 `1688856365770381` 就是妮妮的助手 uid。
3. **`mysql.connector` 只有 vocn2 装了**，本机 `/usr/bin/python3` 没有 mysql/pymysql，脚本要 scp 到 vocn2 跑。
4. **mysql-connector 的 C 扩展 cursor 不吃 `%%`**：带参数的 SQL 里写 `DATE_FORMAT(x,'%Y-%m')` 或 `'%%Y-%%m'` 都报 1064，
   改用 `SUBSTRING(CAST(x AS CHAR),1,7)`，或把常量直接内联进 SQL。
5. **ssh 里用 `ssh host '...'` 包 heredoc 时，脚本内不能出现单引号**（SQL 字符串字面量会被外层单引号吃掉，
   报 `Unknown column 'xxx' in on clause`）。稳妥做法：本地写文件 → `scp` → `ssh host python3 /tmp/x.py`。
6. **cron 静默失败**：脚本只把异常写进 `logs/zhiqu_external_id_map_*.log`，没有告警，
   挂 17 天没人发现。数据是「每天全量重算 + 差集插入」，所以失败不会报错、只会停止增长。

## 待办（按优先级）

1. **[阻塞·需人工]** 联系致趣客服重新开通 `/mochat/open-api/contact/list`；开通后手动补跑一次
   `control_script/zhiqu_external_id_map_cron.sh mercado`，把 8 月积压的新客户补上。
2. 更新配置里娜娜的昵称（或把 `sid_to_robots` 的 robot_name 改成实时从 `rf_wkt_we_com_account` 取，
   彻底免疫改名）。
3. 给 cron 加失败告警（非 0 退出 / 日志 0 字节 / `MAX(create_time)` 超过 2 天没动都该报）。
4. 若业务方要按「哪个助手的好友」统计，`robot_name` 不能只依赖致趣 owner
   （妮妮 7.7%、小贝 16.3% 会严重漏），应改用 rfwkt 好友关系（`rf_wkt_we_com_contact.we_com_user_id`）标注。

---

# 补跑记录（2026-08-18）

## 授权已恢复 + 补跑结果

致趣重新开通 `contact/list` 后实测 `code:0`，全量 106845 条 contact。

**重跑方式：不需要按日期补，脚本本身是「全量重算 + 差集插入」，跑一次就把积压全部补回。**

```bash
ssh vocn2
cd /root/knowledge_database_builder
# 先看会插多少（不写库）
python3 data_control_tools/build_zhiqu_external_id_map.py --client mercado --dry-run
# 正式跑（走 cron 标准路径，日志落 logs/zhiqu_external_id_map_mercado_<ts>.log）
control_script/zhiqu_external_id_map_cron.sh mercado
```

全量拉取约 11 分钟（1069 页 × page_size=100）。dry-run 和正式跑的数字一致：**inserted 2716 条**。

| 指标 | 补跑前 | 补跑后 |
|---|---:|---:|
| `data_scrm_id_map` type=zhiqu_external_id | 35732 | **38448** |
| 最新写入时间 | 2026-07-31 02:12 | **2026-08-18 10:19** |
| 7 月 cid 关联率 | 32.0% | **67.6%** |
| 8 月 cid 关联率 | 13.0% | 14.1% |
| 妮妮好友关联 | 330/351 | 331/351 |

## 8 月只涨到 14.1% —— 关联不上的两种情形要分清

**先明确口径**：名称关联的右表是 `rf_wkt_we_com_contact`（企微好友表，`we_com_contact_user_id` 是数字 id，
等于 `data_scrm.cid`；全表 0 行含 `wm` 开头的致趣 id）。关联方向是
「致趣 contact 的 name」→ `(添加人账号 uid, 名称)` → `we_com_contact_user_id(=cid)`。

关联不上分两种，性质完全不同：

1. **右表里有这条好友、但名字对不上** → 落 `unmatched`(3365) / `ambiguous`(5923)。
   **这是正常损耗**：客户改了昵称、或同账号内同名重复导致歧义（脚本对歧义保守不写库）。
   每次跑都会有，不需要处理。
2. **右表里压根没有这个 cid 的行** → 无论名字怎样都不可能关联上。8 月那 2678 个属于这种。

8 月 3249 个 data_scrm cid 里 2790 个没有 external_id，拆解：

| 类别 | 数量 |
|---|---:|
| **在 `rf_wkt_we_com_contact` 里根本不存在**（不加任何过滤也查不到，只有 23 个有行） | **2678** |
| 是 scope 内 16 助手的好友但名称匹配失败 | 92 |
| 好友但添加人在 scope 外 | 20 |

这 2678 个 cid 的 `data_scrm.user_id` 恰恰就是 16 个助手（小文 538、小唐 483、萝拉 434、小拉 385、
娜娜 354、妮妮 89…），**说明它们确实是这些助手的客户，只是企微好友表还没同步过来**。

`rf_wkt_we_com_contact` 8 月按天新增是**断续批量**的，不是每天：
`08-01 3287、08-10 388、08-12 1084`，其余天个位数（整表 70766 行，最新 create_time 2026-08-18 00:41，同步没停）。

**结论**：致趣链路已完全恢复，能补的都补了，7 月从 32%→67.6% 就是这次补跑的直接效果。
8 月剩下的缺口里，92 个是「名字对不上」的正常损耗；2678 个是右表无行——这批只要 rfwkt 后续补上记录，
每天 02:00 的 cron 会自动关联，不需要人工干预。**右表为什么缺这些行没有验证过**（推测是同步节奏问题：
rfwkt 8 月按天新增是断续批量的，08-01 3287、08-10 388、08-12 1084，其余天个位数，整表同步没停），
要坐实得看 rfwkt 这张表由谁、按什么频率写。

## 顺带发现

- **Gold Huang 从致趣 owner 列表里消失了**：7-31 那次还有 4152 个 contact，本次 0 个。
  它的客户似乎被转移到别人名下（娜娜 5615→5923、黛西 890→1127、莉娅 652→877）。若业务上确认该助手已停用/转移，
  scope 里可以保留（不影响正确性），但按 robot 统计时要知道这件事。
- sid_to_robots 从 43463 降到 41970 个 sid；旧文件备份在 `vocn2:/root/zhiqu_sid_to_robots_mercado.json.bak-20260818`。
- 娜娜的昵称在配置里仍是 `Janice AI`（第 4 节），本次没有改动，API 返回的 `robot_name` 还是旧名。
