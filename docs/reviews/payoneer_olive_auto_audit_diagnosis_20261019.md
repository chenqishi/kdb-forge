# main：payoneer_olive 24 小时机器自动审核失效排查

排查时间：2026-10-19 11:21–11:24，北京时间。此次范围为只读诊断，未执行审核、修改生产配置或重启服务。

## 已确认的原因

ES8 上线只切换了检索和挖掘服务的引擎配置、解释器，独立 cron 自动审核入口遗漏了切换。cron 仍每小时正常运行，但它检查和更新的对象仍是旧 ES7.10，而 payoneer_olive 现在由新 PaaS ES8.17 提供服务。旧库符合条件的待审数为 0，所以任务正常结束，新库的待审知识未被处理。

这不是从客户端版本推测出来的：本次核对了实际 cron、最近三次 stdout、最近一次 stderr 中的目标地址，以及新旧两端同一条件的只读统计。

## main 实际现场

- 工作目录：`/root/knowledge_database_builder`。
- HEAD：`9f02bffda2d736d19b3dde0e8266282096afe248`。原有四处业务脏改动保持不变。
- crond 为 active；审核定时表达式 `00 * * * *`，表示每小时运行，`--hours 24` 表示知识入库等待阈值。
- cron 调用 `control_script/timing_auto_audit_all_indexes.sh config/python_env_config.sh`。
- wrapper 第 14 行固定 `CONFIG_PATH=config/config_es_engine.json`；第 21 行使用裸 `python`；环境脚本激活 `py38`。
- 实测该环境 Python 3.9.0、elasticsearch 7.10.0，配置仍指向旧 Serverless。
- 当前检索配置的 `search_engine_config_path` 则为 `config/config_es_engine_es817.online.json`，声明 ES8.17、默认 Serverless、`payoneer*`/`*payoneer*` 路由到 PaaS。
- 检索与挖掘进程使用旧项目 `.venv-es817/bin/python`；实测客户端 8.17.2。没有运行或修改新重构项目。

2026-10-19 11:00 最近一轮日志：

```text
log/auto_audit_all.log.20261019100001:2427 处理索引: payoneer_olive
log/auto_audit_all.log.20261019100001:2430 ES版本: Elasticsearch 7.10.0
log/auto_audit_all.log.20261019100001:2432 时间阈值(具体时间): 2026-10-18 11:00:09
log/auto_audit_all.log.20261019100001:2433 待审核文档数: 0
```

文件名取“一小时前”，所以文件名 10 点对应实际 11 点运行，并非 cron 延迟。前两次日志同样是 ES7.10 和 0 条待审。最新整轮汇总为 346 索引、成功 17、失败 0、跳过 329、实际更新 0 条；“成功 17”不代表 Olive 有 17 次更新。

另一个日志问题：wrapper 末尾写的是 `2>1`，stderr 实际落在项目根目录的文件 `1`，没有合并进审核 stdout。该文件本轮 152,655 字节，其中 11:00:09 的 Olive `_count` 请求明确指向旧库，HTTP 200。此次未修改重定向或该文件。

## 只读统计：旧库为空，新库有积压

统一阈值：`insert_time <= 2026-10-18 11:21:53`；同时 `from_type_norm in [document, html]`、`audit_result=-1`。严格使用原脚本筛选口径，没有自行增加删除标记过滤。

| 指标 | 旧 Serverless ES7.10 | 当前 PaaS ES8.17 |
|---|---:|---:|
| 索引根文档总数 | 60,539 | 61,894 |
| 满足原 24 小时审核条件 | 0 | 965 |
| high，按既有规则应写 audit_result=2 | 0 | 827 |
| 非 high 且非 segment，按既有规则应写 audit_result=0 | 0 | 138 |
| 非 high segment，按既有规则不改 | 0 | 0 |

新库这 965 条包含 QA 857、segment 108；`del_flag=0` 944 条、`del_flag=1` 21 条。原审核脚本没有排除软删除文档，后续修复不能悄悄改变这一规则，也不能将 965 称为全部可见知识。最早待审 `insert_time=2026-10-13 11:03:43`，最晚为 `2026-10-16 12:23:41`。

其中一条只读样本：`3545ce6c406e5ea364922eebb55924e8`，`from_type_norm=document`、`data_type=qa`、`quality_level=high`、`audit_result=-1`、`del_flag=0`，入库时间为上述最早时间。证据文件只保存 ID 与审核相关元数据，不保存正文或向量。

当前全部来源的待审总数为 12,175，不能将它们全部计入本轮应自动审核数量。既有 cron 只覆盖 document/html；auto_learning、自动学习、other、teacher_training 等仍在原范围之外。本次不扩展审核来源。

两端统计均为 exact total，分片失败均为 0。这里只读读取了集群版本、聚合和最多 3 条元数据样本，未遍历向量或执行更新。

## 为什么不能只把文件名换成 ES8 配置

`AutoAuditProcessor._init_es_client`（`control_script/timing_auto_audit_kg.py:85` 附近）直接读取顶层 `hosts/username/password`，把 `extra_params` 全量传给 `Elasticsearch`。它没有使用项目 `IndexClientRouter`，不能理解当前配置的 `providers/index_routes`；`get_all_indexes` 也只从单个 client 枚举索引。

在 main 现有 `.venv-es817` 中进行离线验证：仅调用真实 `_init_es_client`，禁止 socket connect，不调用构造后的 info/count/update 等网络方法。

- 原单集群配置：client 构造成功；这只是离线构造成功，不是 ES8 网络或写入验收。
- 当前 ES8 路由配置：立即失败，`TypeError: __init__() got an unexpected keyword argument 'recall_mode'`。

原因是检索引擎选项 `recall_mode` 被当成客户端连接参数透传；同时该配置没有顶层 hosts，真实地址在 providers 内。因此只改 Python 路径或只换 config 文件都不构成完整修复。

## 建议的最小修复边界（此次未实施）

1. 审核入口使用现有 ES8 独立环境，并从线上活动引擎配置按索引获取正确 client；复用项目 Router 的路由规则，避免为 Olive 再维护一套独立地址。
2. `--index all` 需要明确枚举当前有效路由下的索引，再逐索引审核；防止全局任务仅连默认 Serverless 而继续漏掉 PaaS，或对迁移临时索引重复处理。
3. 保持原审核语义：24 小时、document/html、high→2、非 high 且非 segment→0，原 segment 和删除标记行为不擅改。先 dry-run 核对范围，再在当次明确授权下补审积压、调整生产定时入口。
4. 审核程序绕过检索引擎直接调用 `_update_by_query`。若恢复全索引任务，Serverless 写路径也须沿用已验证的兼容实现或单独验证；本次未尝试真实写操作，不能声称其已经通过。
5. 修正 stderr 重定向与任务失败可观测性；此类改动不需要重启检索或挖掘服务，但仍属于生产定时任务变更，应与代码发布一并显式交付。

## 验证和边界

- 已读规则、相关 MEMORY、审核 function_schema、部署报告及生产发布授权反馈。
- 远端只读命令：`crontab -l`、`systemctl is-active`、git HEAD/status、限定 `/proc` 命令行、配置字段提取、先 stat 再 bounded tail/streaming 日志定位。
- ES 请求：两端各一次 GET 版本、两次 POST search（size=0 聚合与最多 3 条元数据）。不是业务服务 /search，无自动建索引副作用。
- 离线检查：真实客户端初始化 2 例，成功 1、失败 1；后者保留了配置直换的确定反例。没有运行 pytest；没有真实审核写验收。
- 生产无代码、配置、cron、审核状态、索引或服务变更；没有执行原审核脚本主入口、commit/push、部署或重启。
- 本机只新增本报告/脱敏 JSON，并追加 MEMORY 指针；保留所有既有脏改动。

完整统计、元数据样本、远端脚本 SHA256 与离线反例见 [脱敏证据](payoneer_olive_auto_audit_diagnosis_20261019.json)。本机审核 Python 与 shell 文件 SHA256 和 main 相同，可按本地源码阅读定位。
