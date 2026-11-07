# main 自动审核发布与其他 ES 入口检查

日期：2026-10-19。此报告覆盖本次明确上线授权和随后“检查其他类似问题”的要求，更新早先仅隔离实现的状态。

## 已发布并恢复原全量范围

- 实现提交：`13b552c42a50be199ce09a016dd4aa3db326d3f5`，已 push 到 origin/main。
- main 目标：`/root/knowledge_database_builder`，从 `9f02bffd` 通过 **git pull --ff-only** 更新。没有直接覆盖生产源码、reset、stash 或 clean。
- main 原四处业务脏改动逐文件 SHA 验证保留；87 个候选代码/schema/测试文件 SHA 与验收 manifest 一致。
- 复用旧项目已有 `.venv-es817/bin/python` 和当前业务配置的引擎指针，无需安装客户端或修改 ES 连接配置。
- 检索 PID47173、挖掘 PID1533339 未重启，两个进程 PATH 首项均为旧项目 `.venv-es817/bin`，8003/openapi 和6000/health均HTTP200。
- 本次只读验收，没有手动执行真实补审或其他业务数据写入；审核将按 cron 正常触发。

当前生产审核 cron：

```cron
00 * * * * sh /root/knowledge_database_builder/control_script/timing_auto_audit_all_indexes.sh /root/knowledge_database_builder/config/python_env_config.sh >>/root/knowledge_database_builder/log/run_timing_auto_audit.log 2>&1
```

新入口保留接收旧 env 文件参数的兼容形式，但不再 source 激活 ES7，而是使用同目录 ES8 独立环境。cron 不需要重启 daemon。业务配置已正确指向 ES8，因此本次主要是更新入口代码；生产仍是每小时、全量 client、document/html、满24h、原质量分支。

**范围纠正：**14:30 曾错误加入 `AUTO_AUDIT_INDEX=payoneer_olive`，把验收样本变成了生产白名单。用户指出后，14:35:13 已撤销，恢复 wrapper 原 `all` 默认。下一轮为 **2026-10-19 15:00（北京时间）**，此前没有发生受限 cron 执行，也没有漏掉这5分钟内应触发的小时任务。该限制不属于用户要求，后续不能再以“先验收一个客户”为由改变生产范围。

备份位于 main 私有目录：`/root/knowledge_database_builder/backup/auto_audit_unified_20261019_143009`。保留原 cron、原审核源码、配置与变更状态；早期受限配置另存，当前 activation.json 已明确 `scope_after=all`。异常时可先停用该审核 cron；不能自动回切继续审核旧库，也不能无条件撤销审核结果。代码回退继续走提交/revert 后 git pull 的项目流程。

## 已部署代码的真实 dry-run

直接使用已 pull 的生产文件、既有 ES8 环境和活动配置运行，无进程内替换源码：

```bash
cd /root/knowledge_database_builder
PYTHONDONTWRITEBYTECODE=1 .venv-es817/bin/python control_script/timing_auto_audit_kg.py \
  --search-config config/config_for_search_index.json --index all \
  --from-type-norm document,html --hours 24 --dry-run
```

14:35:30 的全量读取：**109 索引，dry-run109，失败0，更新0**；Serverless93、PaaS16。满足原来源/待审/时间条件共4,983条，其中 high4,050、可处理的其他质量646，合计4,696条；其余287条为按原规则保留的非high segment。全量盘点没有按client名称或白名单排除目标。

Olive952条（814 high、138其他），Mercado Local0；其他待处理包括payoneer、mars_mind_to_c_sales_marsmind_toc_sales、wayfair_wayfair_test2及test_case，均是原all枚举语义。没有凭名称自动清除测试库或改审核范围。

原始 dry-run JSON 与stdout保存在上述main备份目录。脱敏汇总见 [deployment.json](auto_audit_unified_20261019/deployment.json)。先前337项离线回归结果保持；dry-run不能代替真实写入完成验收，此报告不声称积压已经处理完。

## 其他类似问题：已确认与潜在项

检查 main 本项目237个实际 Python/shell文件（含未跟踪工具），root cron、/etc/crontab及/etc/cron.d、当前Python进程、相关启动脚本和两套配置。没有执行其他任务或维护写入，没有修改下述入口。systemd timer列表未发现知识库相关项。

### P1：机器重启入口仍使用 ES7 环境

当前 root `@reboot` 调用 `/opt/startup/restart_rufitai_all.sh`。该文件：

- 第34–40行：进入旧项目，`conda activate py38`，裸python启动检索并读取 `config/config_for_search_index.json`。
- 第68–72行：同样以py38裸python启动 `off_task_control_service.py`。

py38实测ES客户端7.10.0；活动配置为ES8。禁止socket连接的离线探针直接调用当前真实工厂，确定得到：`ES8 路由拒绝非 8.17.x Python 客户端：当前为 '7.10.0'`。

**影响：**现有运行进程使用独立8.17环境，因此当下正常；但下次整机启动或有人运行这个总启动脚本，检索会因版本检查无法正常初始化，挖掘进程/子任务也面临旧解释器问题。应单独将这两个知识库段落统一为旧项目ES8环境与PATH，不改变同脚本中的其他应用环境。此次只检查，未改总启动脚本，更没有执行它。

### 潜在问题：聊天挖掘报表分支仍使用旧环境

root cron每天12:00、18:00运行 `control_script/timing_run_task_gen_knowledge_by_send_request.sh`。第17行source旧环境，第48行裸python；请求任务阶段只走HTTP，任务接收服务当前为正确的ES8进程。

但第66行的报表分支调用 `batch_gen_audit_data_and_send.py`，随后 `gen_audit_data_to_customer.sh:17–19` 又以裸python使用活动ES8配置导出数据，启用该分支时会产生同样客户端版本拒绝。`batch_gen_audit_data_and_send.py:33/48` 还没有检查子进程返回码，失败可能被上层误认为成功。

**当前没有此分支正在失败的证据：**`config/chatkonwledge_report_platform_map.txt` 实际0字节/0个平台，今天12:11的报表日志0字节，最新全局水位已推进到 `20261019121120`。所以这是配置报表平台后会暴露的潜在缺陷，不能把当前聊天挖掘主体误报为已失效。没有为了验证它开启报表、调用外发或重复投递任务。

### 手工工具：旧默认配置与单地址client仍有残留

未在cron或进程列表中看到以下维护工具运行；风险在于后续手工执行仍可能访问旧库，并非已确认本轮发生误写：

| 入口 | 现场证据 |
|---|---|
| `control_script/update_del_flag_batch.sh:12` | 默认旧 `config/config_es_engine.json`；Python底层虽经统一工厂，仍会被旧配置选回ES7。 |
| `control_script/backup_es_data.sh:13`、`control_script/supply_missing_field.sh:12` | 同样默认旧配置；对应Python工具自行构造ES客户端。 |
| `data_control_tools/audit_chat_auto_qa_by_llm.py:64/590`、`export_qa_to_excel.py:64/406` | 默认旧配置，经单地址 `EsHttpClient.from_config`。 |
| `retire_superseded_knowledge.py`、`rollback_mining_tasks.py`、`prune_page_mismatched_images.py`、`prune_dead_raw_urls.py` | 同类默认旧配置/裸HTTP维护入口。 |
| `strip_nav_boilerplate.py:90/222`、`augment_segment_topics.py:292/381`、`skip_deleted_sources.py:28/65` | 默认参数仍是旧配置文件，手工调用时需明确目标。 |
| `control_script/timing_auto_audit_all_indexes_tmp.sh:14/22` | 遗留临时入口仍是旧配置+裸python，当前不在cron中；不能与已修好的正式入口混用。 |

`commons/es_http_client.py:69–90` 只读取顶层hosts并选择第一个地址，不支持当前providers/index_routes。因此六个使用该helper的维护工具不能简单把配置路径换成ES8路由JSON。建议后续通过统一维护接口整改，保留显式维护旧库的用途；不能全局替换共享旧配置来掩盖入口差异。

`/root/dify/knowledge_database_builder/config/config_es_engine.json` 及其业务配置仍指旧库，和本次活动配置不是同一个文件。当前已核实的检索/挖掘进程不使用该旧引擎指针；是否有其他仓库/外部应用还依赖它不在此次完整覆盖范围，不能直接删除或覆盖。

## 状态边界

本次已完成自动审核代码发布、原all范围恢复、真实全量dry-run及类似入口检查。尚未观察15:00后的真实审核结果，其他启动/报表/手工工具尚未修复。此次明确授权的上线不应自动扩展为重启机器、执行总启动脚本、发送报表、运行清理工具或修改其他应用环境。

当前进程/配置/cron清单见 [入口盘点证据](auto_audit_unified_20261019/other_entries_inventory.json)。该快照采集于scope纠正前，其cron命令hash代表14:31状态；当前all状态以deployment.json和main备份activation.json为准。
