# run_local_mining.main

本机批量跑文档挖掘（不投递线上任务服务）。

## Inputs
- `--tasks-file` (必填): `build_doc_mining_tasks.py` 产出的 tasks.json
- `--out`: task_id 记录文件（撤回用），默认与 tasks-file 同目录
- `--workers` (默认 3) / `--limit` / `--log-level`
- `--skip`: 逗号分隔的文件名，跳过这些篇
- `--skip-from`: 已跑记录 json，自动跳过其中 `rc==0` 的篇目

## Outputs
- 每篇一条 `{name, task_id, rc, secs, log}`，写入 `--out`（**每篇都落盘**，中途被杀也能撤回）

## 注意
- `--limit 0` 是**假值**、会跑全量；限定篇目要用 `--skip` / `--skip-from`
- **`--skip-from` 必须在主批结束后读**：主批边跑边覆写记录文件，
  提前取快照会漏掉后完成的篇目 → 重复灌库
  （2026-08-29 实测：重试本应跑 1 篇，实际跑了 15 篇，14 篇重复灌入 160 条知识，已软删撤回）
- 三个前置条件见模块 docstring（python shim / PYTHONPATH / py38 解释器）

## SQL
不直接读写 MySQL；下游各阶段写 ES 索引 `payoneer_olive`（知识条目，`del_flag`/`task_id`/`audit_result`）。

## 已知卡死模式（2026-08-30 实测）
个别文档会在 `knowledge_clean` 阶段**无限期挂起**（无超时、无报错、日志停在
"执行命令: [...knowledge_clean...]" 不动），拖住整个批次。
实测案例：BestBuy 的 `Choose a country.` 页（国家选择器，无实质内容），卡 25 分钟。

**排查**：**光看运行时长会误杀**——实测 Joom 一篇 16.7K 字的文档正常跑了 20+ 分钟。
判据要看**日志是否还在推进**：
```
tail -1 mine_logs/<task_id前12位>.log      # 看停在哪个阶段
ls -la --time-style=+%H:%M:%S <同一文件>   # 看最后写入时间
```
- 日志**停在同一阶段 >10 分钟没有新行** → 卡死，可 kill
- 日志**还在往后走**（clean → segment_builder → search_index_data_interface）→ 正常，别动
`search_index_data_interface` 阶段天然慢：要逐条调阿里 embedding API 再写 1024 维向量。
**处理**：直接 `kill` 该子进程，批次会把它记为失败并继续下一篇。
这类卡死多发生在**无实质内容的导航/选择器页**上，损失可忽略。
