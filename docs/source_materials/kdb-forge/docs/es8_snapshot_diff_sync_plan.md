# 旧 ES 快照差异同步：可行性与执行条件

2026-10-04；仅核查本地文件和官方版本文档。**未扫描旧 ES，未启用同步；本方案不构成夜间整体扫描授权。**

## 结论：能做，但现有 dump 不能直接当版本基线

- 已检查批准范围内 **86 份 gzip 的首条记录**；全部只有 `_id`、`_source`。[原导出代码](../scripts/export_es7_to_local.py)也固定仅保存这两项，未请求或保存 `_version`、`_seq_no`、`_primary_term`、`_routing`。
- checkpoint 的 `source_version=7.10.0` 是集群版本；`source_watermark` 是最大业务 `update_time`，没有逐条版本或来源 index UUID。**不能给旧正文配上今天读到的版本，便声称已建立一致基线。**
- 因此，首次需取得新的完整正文快照并对账，记录可靠的逐条元数据；以后才可全扫 ID／版本，只读取、落盘和导入变化正文。未变化数据不重复导入，已完成的 `payoneer_olive` 也不盲目重迁。

## 最小执行流程

1. **先验证分页能力，再等待夜间命令。** 固定使用[批准的 86 原名及 provider](../migration_runs/local_dump_20261001/data/shard_plan_1g.json)。官方 ES 7.10 已有 PIT，但阿里 Serverless 的兼容性及唯一、稳定排序须在获准的小批测试中验证，不能直接照搬 ES8 的分页写法。用户已取消 scroll，本方案不自行恢复 scroll；若没有可证明完整的分页方法，就不启动全扫。[ES 7.10 PIT 文档](https://raw.githubusercontent.com/elastic/elasticsearch/v7.10.0/docs/reference/search/point-in-time-api.asciidoc)
2. **首次建立基线。** 在每个索引的一致快照中读取完整 after-image，以及 index UUID、ID、routing、seq_no／primary_term、version；落成本地目录和逐条内容 hash。对照实际已验收的目标数据及增量记录补差，不能凭数量或抽样相同认定整个旧 dump 等于当前目标。86 个索引分别记录快照建立时间，不声称跨索引事务快照。
3. **后续只取变化正文。** 同一来源 UUID 下，扫描所有 ID／routing／逐条版本，与上次已应用基线比较；有变化的正文必须从**同一个快照**取回，不能用实时 `_mget` 混入另一版本。seq_no 是分片内序号，不取其最大值当全局游标；version 单独使用可能漏掉删除后重建。UUID 变化须重建该索引基线。若发现自定义 routing，现有消费合同须先扩展验收，不可丢掉 routing。
4. **完整成功才认定删除。** 所有批准索引、所有页及分片成功，逐页无超时／失败，精确总数、去重结果及索引身份校验均通过，才能把“上次有、本次无”的 ID 记为 tombstone。上下文失效、漏页、分片失败或并发重建则整窗不提交，不发删除，也不推进基线。历史导出只校验数量，没有逐页检查 `timed_out`／分片失败，不能替代此验收。
5. **先完整落地，再写新 ES。** 完整元数据目录、变化 gzip、SHA 和 manifest 冻结提交后，才交给[现有消费工具](es8_committed_runner.md)。记录来源为 `snapshot_diff`；本地单调 event cursor 不冒充 ES CDC 水位。`exported` 与 `applied` 基线分开；失败只重试已落盘窗口，不越过它。目标独占写入，稳定 stream／version_base、外部版本和持久 registry 共同防止旧窗口复活删除记录；全部 ACK、刷新、逐最终 ID 校验后才原子推进已应用基线。

## 成本与边界

现有 86 份基线共 **202,732 条，gzip 5.68 GiB，解压正文 17.38 GiB**。各索引记录的导出耗时合计 **82.2 分钟**；最早开始至最后完成跨 **3 小时 8 分钟**，含分段运行间隔。这是历史量级，不是新任务耗时保证。按每页 500 条，即便只扫元数据也至少 **465 页**，还需快照管理、变更正文读取和校验；传输会减少，但旧 ES 仍扫描全部文档，不能称为零负载或默认白天高频执行。

若授权每晚执行一次，变更等待下一次快照的时间可接近 24 小时，再加扫描、导入及验收耗时；需要分钟级追平时，这种频率不足。PIT 元数据与变化正文读取必须先小批验证，当前没有实际的新完整快照、快照导出器或定时同步任务，因此这里的成本和正确性条件不代表同步已经闭环。

**初次及每次周期全扫仍等用户夜间明确命令。** PIT 会保留旧段并占用额外磁盘／句柄／堆内存，逐索引有界运行并及时关闭。此方案得到“各索引在某次快照时可见的最终状态”，不能保留两次扫描间短暂新增又删除的事件；完整事件历史仍需所有写来源的持久 CDC。未执行、未对账或未验收时，始终 `freshness_proven=false`。[PIT 资源成本](https://raw.githubusercontent.com/elastic/elasticsearch/v7.10.0/docs/reference/search/point-in-time-api.asciidoc)
