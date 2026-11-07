# 本地 committed 增量消费 runner

实现：[run_committed_local_changes.py](../scripts/run_committed_local_changes.py)，底层复用 [apply_committed_local_changes.py](../scripts/apply_committed_local_changes.py) 与[日志合同](es8_change_log_contract.json)。**组件已实现，持续同步未启用；没有真实 producer、所有写者覆盖与历史补差证据时，不能据此声称数据已追平。**

## 输入与顺序

- 使用独立、不可变的 producer 目录，推荐 `<目录>/<窗口编号>/manifest.json`，对应 gzip 放同一子目录。默认扫描 `**/manifest.json`；其他命名可用 `--manifest-glob`。producer 必须先持久化 gzip，最后原子 rename 出 `status=committed` 的 manifest。
- 未 committed 和 `.tmp` 文件不消费；格式损坏的正式 manifest、混合 stream/version_base、重叠非空窗口、同一非空区间不同 SHA 均停止本轮。相邻非空批次 `(a,b]` 与空批次 `(b,b]` 合法；同一游标连续产生不同空文件也允许，因其没有冲突事件。空批次不推进游标，正常扫描无需写目标，已有 pending 空批次仍按原 SHA 完成恢复。完整 gzip SHA／事件／向量校验由底层 consumer 在请求目标之前执行。
- 先续跑 state 或 canonical registry 中的 pending SHA；若本地文件缺失则等待，若同窗口被换 SHA 则报错。之后只选择 `start_exclusive == applied_cursor` 的窗口；缺口等待，不跳到后续批次。
- 失败保留原窗口，按受控间隔重试本地文件。即使失败发生在创建 consumer state 前，health 也保留重试 SHA。所有 ACK、刷新和逐 ID 验证仍由 consumer 完成后才推进水位。
- state 已验证提交、registry 尚未提交的中断，优先续跑同一窗口补齐 registry，再处理下一窗口；不会重复写入该已验证窗口。原 state／registry／已封闭日志都必须保留。切换 state 或 stream 需要人工评审对账 handoff，没有绕过开关。

## 命令示例

以下目录须由真实 producer 交付；`BASELINE_CURSOR` 必须替换为协调确认的基线游标。

```bash
# 默认仅检查一次。校验队首批次并输出 JSON，不联网、不写 state/health。
.venv-es817/bin/python -P scripts/run_committed_local_changes.py \
  --manifest-dir migration_runs/committed_changes \
  --state artifacts/es8_change_consumer_state.json \
  --health artifacts/es8_committed_runner_health.json \
  --initial-cursor BASELINE_CURSOR
```

完成源交付与目标写入协调、涉及 Serverless 的恢复 lease 释放后：

```bash
# 先在同一命令追加 --apply，消费一个窗口。
# 确认后使用 --apply --watch，前台持续轮询；本工具不会自行安装/启动服务。
.venv-es817/bin/python -P scripts/run_committed_local_changes.py \
  --manifest-dir migration_runs/committed_changes \
  --state artifacts/es8_change_consumer_state.json \
  --health artifacts/es8_committed_runner_health.json \
  --initial-cursor BASELINE_CURSOR \
  --apply --watch --poll-seconds 15 --retry-seconds 30
```

后续继续使用同一 state，省略 `--initial-cursor`。没有 `--apply` 时禁止 `--watch`。失败重试间隔最低 5 秒；等待新窗口／缺口使用 polling 间隔。成功后可立即处理下一批。state 和 health 必须在 producer 目录之外，不能覆盖配置、lease 或 registry。

## 健康报告口径

只有 `--apply` 才原子保存 health；dry-run 仅输出 stdout。报告无文档正文、向量或凭据。

| 字段 | 含义 |
| --- | --- |
| `applied_cursor` | 从持久 consumer state 读取的已应用游标，不由 runner 自行增加 |
| `applied_windows` | 当前目录中结束游标不大于已应用游标的封闭窗口数；是覆盖范围计数，不是本进程累计写入次数 |
| `exportable_windows` | 当前目录中已 committed、结束游标高于已应用游标的候选窗口数；按 manifest 元数据统计，完整 gzip 在消费前验证，不表示可跨过缺口 |
| `status` | `applied`／`recovered`／`waiting_for_manifest`／`waiting_for_gap`／`waiting_for_pending_manifest`／`failed`；dry-run 成功为 `dry_run_validated` |
| `last_success_at`、`at` | 已成功提交时间、健康报告更新时间；监控应同时检查报告是否停止更新 |
| `failure_reason`、`retry_window` | 脱敏失败类别与固定重试窗口 SHA／游标 |
| `freshness_proven` | 始终 `false`；没有本地待消费窗口也不能证明源端没有漏捕获 |

runner 不查询旧 ES，不触发历史扫描，不生成来源变更，也不删除批次或失败记录。真实捕获接入范围见[来源盘点](es8_source_capture_inventory_20261004.md)。
