# 深圳旧 ES 写来源与接入位置（只读盘点）

2026-10-04 04:01～04:04 UTC／北京时间 12:01～12:04，通过已有 SSH alias `shenzhen-120` 读取项目代码、进程和相关调度配置。未请求 ES、未修改旧机、未重启服务。本页只列脱敏路径、方法及运行事实；**尚未部署来源 producer，也不能证明所有真实写者已覆盖。**

## 已确认的运行边界

- **8003：** PID `307354`、PPID `1`，入口 `knowledge_database_search_service/src/knowledge_database_search_es.py config/config_for_search_index.json`，cwd `/root/knowledge_database_builder`，Python 3.9，启动于 `2026-09-21 17:31:06 UTC`。进程属于登录 session scope；本轮未发现该项目对应的 systemd service，按现有手动守护管理。
- **6000 离线控制：** PID `2269292`，入口 `control_service/off_task_control_service.py`，项目脚本目录为 `/root/knowledge_database_builder`，启动于 `2026-09-22 17:02:29 UTC`。`batch_run_chatqa_request.py` 在本次盘点时实际运行（PID `1492198`，`2026-10-04 04:00:01 UTC` 启动）。
- 8003 与控制进程的 `PYTHONPATH` 指向当前项目，8003 入口和 `SearchDataInterface` 文件没有再改 `sys.path`。当前所查服务／引擎代码修改时间均早于 8003 启动；这支持加载路径判断，但不是进程内已加载模块字节的独立证明。
- `config_for_search_index.json` 的引擎配置实际引用 `/root/dify/knowledge_database_builder/config/config_es_engine.json`。它与当前项目的同名文件**不是同一文件**，但本次只读比较确认端点与认证相同。接入应保留并绑定实际配置路径，不凭文件名猜测环境。
- 旧机当前时区偏移 `UTC+08:00`，上述进程未设置 `TZ`，root cron 无 `TZ/CRON_TZ` 覆盖。下面 cron 时间按该主机时区理解；这仍不能替所有历史写者的无时区字段确定可靠水位。

## 实际入口 → 最终写入

下表路径均相对 `/root/knowledge_database_builder`。

| 实际入口 | 链路与最终写入 | 是否必须经过 8003 |
| --- | --- | --- |
| 8003 `/insert`、`/delete`、`/delete_by_file`、`/update_by_condition`、两类 `/modify_knowledge*` | HTTP 文件 `:336,526,632,807,830,871,912` → `SearchDataInterface`／`ModifyKnowledge` → `EsSearchInterfaceOri` | 这些请求经过；`/preview_delete_by_file` 只预览，不计为写入口 |
| root cron `00 * * * *` | `control_script/timing_auto_audit_all_indexes.sh:22` → `timing_auto_audit_kg.py` → `AutoAuditProcessor._run_update_by_query:307` → 独立 `self.es.update_by_query` | **绕过**；审核脚本 `:459,505` 仅更新 `audit_result`，不推进 `update_time` |
| root cron `00 12,18 * * *`，第一阶段 | `timing_run_task_gen_knowledge_by_send_request.sh:54` 直接执行 `batch_run_chatqa_request.py`，其 `:251` 请求 6000 `/start_task` → 控制器子进程 → 本地导入 CLI → 引擎直接 ES 写入 | **绕过**；6000 的 HTTP 是任务提交入口，不能算已被 8003 捕获 |
| 同一 cron，第二阶段 | 上述 shell `:66` 再直接执行 `batch_gen_audit_data_and_send.py` → `:31,33` 执行 `gen_audit_data_to_customer.sh:18` → CLI `gen_audit_data:1648`／`engine.scroll_search:1688` 导出审核数据；随后生成报告 | 此阶段是直接读 ES／报告链，本次所查调用未发现 ES 写入；与每小时 `timing_auto_audit_kg.py` 的实际审核写入区分 |
| 常驻 6000，文档／分段／聊天／HTML／Excel 五类任务 | `off_task_control_service.py:430,496,554,622,694` 启动五类控制器；最终分别在 `document_qa_mining_task_control.py:375`、`document_qa_segment_mining.py:617,721`、`chat_qa_mining_task_control.py:669`、`html_kg_gen_task_control.py:658,768`、`excel_qa_segment_upload_control.py:401` 调用 `knowledge_interface_tools/search_index_data_interface.py` CLI | **绕过**；这些新 Python 子进程直接加载引擎 |
| 手动／维护代码（本轮未见正在运行） | `knowledge_interface_tools/supply_missing_field.py:355,449,708` 自建 client，执行 `update_by_query`／bulk；`data/payoneer_chat_rewrite_v20260613_final/apply_payoneer_chat_rewrite_to_es.py:172,176` 调用 `interface.engine.update`；`data_control_tools/data_transfer_tools.py:349,642` 调用 `target_search_interface.insert_data` | **绕过** |

已检查该项目 253 个 Python 文件的静态调用。本范围未找到 `delete_by_query` 调用；不能据此排除外部脚本、另一份项目或其他主机直接调用。root cron 的其他业务项未展开或输出。补充只读核对确认：12／18 点 shell 的两阶段均为活动代码，第一阶段失败会退出后续流程；`batch_run_chatqa_request.py` 并非 `batch_gen_audit_data_and_send.py` 的后续环节。本轮未执行任何上述脚本或其 scroll 调用。

## 最小补丁落点与部署边界（待评审，未执行）

1. **共同持久协调器：** 新增 `knowledge_interface_tools/source_change_capture.py`，兼容旧机 Python 3.9，提供写前 durable intent、同 ID 串行、来源 CAS／失败恢复、成功事件提交及本地封窗导出。完整 after-image 包含四类向量；物理删除产生 tombstone。不能在返回 HTTP 成功后才补记日志。
2. **主引擎六个出口：** 在 `EsSearchInterfaceOri.insert_with_vectors:582`、`insert:928`、`update:969`、`delete:993`、`update_by_query:464`、`update_value:542` 的实际 ES 调用处接入。可覆盖 8003、五类任务 CLI、数据搬运和已定位重写脚本。`insert` 实际是 `update(doc_as_upsert)`，普通 update 是局部字段；producer 必须在一致来源版本上补齐完整 after-image，不能把局部 `doc` 冒充全量文档。
3. **两个独立 client 旁路必须同时接入：** `AutoAuditProcessor` 的 client 初始化 `timing_auto_audit_kg.py:74,108`／写调用 `:307`；`FieldSupplier` 的初始化 `supply_missing_field.py:84,117`／写调用 `:355,449,708`。仅包装 `SearchDataInterface` 或主引擎会漏掉它们。
4. **批量操作须逐条可证明。** `update_by_query` 返回数量不足以生成每个 ID 的完整事件。受协调范围内需固定命中 ID／来源版本、记录 intent，再以有界 CAS 批次更新并逐项确认；软删为完整 upsert，硬删为 tombstone。仍保留直接 query 写入的路径，必须列为未解决覆盖缺口。此设计不授权现在执行旧 ES scroll／全量枚举；历史广泛对账仍按用户夜间明确命令约束。
5. **加载边界：** 修改磁盘模块不会替换已运行 8003 的引擎实例；该入口需要单独安排受控部署／重启并验收。本轮不会执行。cron 和 6000 启动的新子进程会在下一次启动加载磁盘代码；因此“未重启常驻服务”也不代表补丁尚未影响批处理，发布必须同时考虑两条加载路径。
6. **封窗与历史基线：** pending 来源结果必须先解决，再将封闭游标区间 gzip＋SHA＋manifest 落地；目标交给[现有消费合同](es8_change_log_contract.json)和[runner](es8_committed_runner.md)。捕获启动游标之外，仍需受控历史对账补齐已发生但无时间戳／无日志的修改和删除。已有全量 dump、迁移成功记录或进程列表都不能替代这一证明。

上线前仍须确认其他主机／副本项目／临时凭据写者，以及 OpenSearch 分支是否实际承载范围内数据；只完成以上本机适配不能自动签署全写者覆盖。当前 `freshness_proven=false`。
