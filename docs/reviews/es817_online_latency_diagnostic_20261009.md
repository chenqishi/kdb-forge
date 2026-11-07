# 120 ES8 检索耗时排查与迁移收尾核对，2026-10-09

**已确认新 ES8 引擎把旧版单请求内的原生 msearch 批量执行改成了逐索引、逐路串行 search。这是适配遗漏，ES8.17 并不要求这样实现。** 同时 PaaS 首轮向量查询存在服务端数秒波动，Serverless 现场返回预算为40且有四条应用请求重叠，不能把所有慢查询归因于这一处遗漏。本轮只测试/报告，没有修改引擎、业务、运行配置或重启服务。

线上目录 `/root/knowledge_database_builder`，复核时文档HEAD c84b6120，业务实现基线3ee7f931；引擎SHA `d9a30277f6464d639a9255800506f8bc9fffeff062834e10cd1839d1df4cd9fc`。现有旧项目 .venv-es817：Python3.9.0 / elasticsearch8.17.2 / elastic-transport8.19.0。开发与诊断目录 `/root/knowledge_database_builder-es817-release-20261009`，保留所有既有未提交/未跟踪文件。

## 数据完整性结论

迁移补差已于北京时间01:28:23完成：固定86原名，旧/新各202,962根，完整ID/routing集合相同，逐身份del_flag/audit_result/quality_level的索引值差异0；新增213、更新17，230个真实ACK全部独立完整source读回。更新包含三条del_flag修正，既存17条四类向量/nested内容未改。固定时间窗口340个不同文档完整字段相等；历史17项排除和范围外replay/临时索引未擅自纳入。本轮不是新一轮数据同步或知识审核。

这证明固定范围记录齐全及三个标记在逐库快照时一致；不把统计相等冒充逐条验证，也不把未推进时间的其它任意字段或永久CDC说成已完成。完整材料见 [执行报告](es817_incremental_sync_execution_20261009.md)、[逐库表](es817_incremental_sync_execution_20261009/final_indexes.csv) 和 [身份/标记证据](es817_incremental_sync_execution_20261009/metadata_final.json)。维护源码与私有before/after继续保留在原隔离开发现场，未作为生产应用实现发布。

## 新旧调用差异与现场日志

旧 `EsSearchInterfaceOri.search_multi` 于es_search_interface.py:1382附近构造每索引每路独立body，调用真实 `_msearch_with_shard_check`（:1464）一次msearch。与升级前f873a593的两个方法AST hash完全相同，不是用改造后的新测试期望替代旧契约。

当前ES8 `_search_multi_group` :883 / :898用两层for循环，每次同步 `_search_request`。`_msearch_with_shard_check` :680名称保留，但同样把原body逐项拆成search。两个provider组也按顺序执行。因此请求内部通常累加各路时间；另一worker/请求的并行不代表内部已经并行。跨provider仍必须独立client，不能把其请求交给同一个集群。

旧ES7 dual已有请求级 `_source.excludes=[indexes.embedding,image_indexes.embedding]` 和正确完整路径inner_hits回填；当前ES8没有裁剪外层source，因此全部向量仍能重排，但相对text/embedding的inner_hits过滤仍产生空source。本轮完整外层source提供全部向量，没有以错误裁剪换速度。不能不修过滤/验证回填就照抄旧裁剪，更不能把请求过滤与存储裁剪混为一谈。

用户PaaS00:56日志：BM25约64ms、第二路约2194ms，总接口2542ms。原日志只有客户端duration，不能直接把它当ES took。本轮独立真实请求取得相近首轮耗时，并实测took，见下表。

Serverless01:57实际四条请求在4ms内到达，参数尾部分别40/qa/text/True两条、10/segment/text/True两条。贴出的日志跨worker交错且未带请求ID，不能把全部行串成单请求。QA公私两库每索引两路各取40，每请求4个ES子查询；业务size*2只保持候选预算，不是迁移临时把2改为40。此前main基准多为每路5条，且排除了现场embedding/完整服务流程；两类耗时不可直接比较。

`async query_remote_service`仍同步调用业务逻辑，单worker检索期间会阻塞其事件循环；当前4workers只能按worker并发处理。它和/search方法与f873a593 AST完全相同，是既有服务限制，不是此次升级新引入的回归。本轮未修改上层来适配引擎。

## 真实只读对照

在120已有环境的独立nice15进程，使用现有真实8.17客户端/Router及部署引擎builder，临时关闭本测试对象的ensure/mapping，没有改变运行配置。固定向量及实际默认QA/审核/软删条件；PaaS使用用户原问题、单公库、每路2条；Serverless使用公开已测入驻问题、mercado及mercado_mercado_janice、每路40条，它不是用户未提供全文的原问题。seq1→batch1→batch2→seq2，组间3秒间隔，msearch内部最多2个子查询并发，原分片并发默认保持。首次观测不等于受控冷缓存实验。

| 样本 | 首次逐个search | 首次msearch | 重复msearch | 最后逐个search | 每次完整解压响应 |
|---|---:|---:|---:|---:|---:|
| PaaS，Olive，2条/路 |2523ms|347ms|58ms|94ms|约0.465MB|
| Serverless，公私库，40条/路 |563ms|364ms|348ms|512ms|约11.26MB|

PaaS首轮向量子查询HTTP2431ms、ES took2420ms；BM25 took27ms。重复后的向量took18ms。主要首轮慢在ES协调/排队/执行范围，未取节点/磁盘统计，**缓存、磁盘或资源原因尚未确定**；不能将2523→58全部算作并行收益。可比较的后期热样本94→58也只是一组观察，非P95保证。

Serverless这组took13–44ms/子查询，网络接收与JSON解析亦明显。保持相同40预算时msearch约减少148–215ms，约32–35%；所有四轮逐路候选顺序、完整_source SHA和真实未改动QA本地重排分数SHA都相同。没有削减候选/字段/向量换取这些时间。ES8原生msearch在PaaS及Serverless均真实成功，全部子查询0分片失败、0超时。官方支持以一个请求执行多个搜索并控制子查询并发：[ES8.17 Multi search](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/search-multi-search.html)。

Serverless另取5条/路对照约280ms/1.54MB，但预算及KNN候选数也改变，只用于说明此前样本更小，不能用作同语义优化。诊断性_source=False仅用于观察fetch/传输，不进入业务重排，也不是可部署替代方案。gzip单路完整source收到约2.902MB解压数据、908KB传输长度（约减少69%），内容/候选/向量仍完整；本轮新连接下耗时未改善，不自动启用或保证更快。

`took`包括协调与数据节点通信、搜索排队和执行，不包括响应JSON序列化及向客户端发送；HTTP-took差不能简单等同地域RTT。[ES8.17 Search](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/search-search.html)。

独立probe实际29个原生HTTP读、32个搜索子查询、2次query embedding，无LLM/ES持久写/服务请求。所有诊断client关闭；PID/创建时间和源码SHA前后相同，host load1 0.56→0.58，空闲内存约23.4GB。未进行负载压测，不用PID不变证明线上延迟绝对没受影响。

另外串行低频调用当前线上/search四次：PaaS top2为585/286ms，Serverless top40为1102/689ms，2/40结果、ID和有限分数正确，各自两轮最终顺序/分数hash相同。此批含现场embedding和完整消费者，未复现用户四请求同到的4秒场景；样本和负载不同，不能说用户慢查询不真实。四次服务内ES/embedding额外调用没有合并进独立probe的29/2计数。

## 待修与验收边界

1. 优先在引擎内部恢复**同provider的真实原生msearch**，保留每索引每路预算、过滤、native HNSW、完整source及原响应/合并顺序。另按既有契约处理子响应错误与失败分片，不能仅替换一个helper而破坏在线成功/部分结果兜底。跨provider独立路由，必要并发也需限额；不改请求API或上层。
2. 对PaaS首次数秒波动再观察节点/读盘/缓存/搜索排队，不假称恢复并行能治好所有冷/热波动。是否启用gzip需同连接、同负载复测；本轮尚无延迟收益证据。
3. 继续保留重排向量。若后续选择减少传输，要先验证完整路径inner_hits回填及BM25-only同义/图片向量契约；没有这份验收时继续返回完整source。长期10QPS和同时QA+segment突发尚未压力验收。

本轮**尚未把并行修复部署或改进引擎实现**，不是宣称所有缺陷已关闭。只新增只读诊断工具及6个先读schema，工具及嵌入代码编译/schema覆盖检查通过；32个真实子查询已验，未新增镜像mock测试来冒充性能验收。

实际命令：

```bash
cd /root/knowledge_database_builder-es817-release-20261009
python -u tests/es817_online_latency_diagnostic_20261009.py \
  --output docs/reviews/es817_online_latency_diagnostic_20261009
```

输出目录必须为新的路径，拒绝覆盖。完整脱敏结果 [evidence.json](es817_online_latency_diagnostic_20261009/evidence.json)，实际HTTP服务复测 [service_readonly.json](es817_online_latency_diagnostic_20261009/service_readonly.json)。不保存知识正文、向量数值、凭据或真实读令牌。
