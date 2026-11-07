**旧、新来源统计接口实施验收与类目测试结果，2026-10-08**

当前运行状态更新：用户随后明确授权本机重启，两版接口已在8003/8012加载，08:59:00/08:59:30 CST重启后真实计数验证通过。见[本机加载与重启报告](/root/knowledge_database_builder/docs/reviews/from_type_count_local_activation_20261008.md)。下文“尚未加载”是实施交付时的历史状态，不能沿用为当前状态。

用户确认执行的LEARNING-COUNT-API-20261008已在两项目的隔离开发目录完成，实现POST /get_from_type_count，from_type默认chat_auto。两版原物理索引名不转换、不拼公私库；筛选固定quality_level=high，精确原from_type字段；起止时间齐才增加insert_time闭区间，不追加审核/软删/类目条件。用_count精确计数，异常/缺库/不完整结果失败0，正常0成功，计数不创建索引。共同方案中的>10000改用精确数已保留，不复制Java默认search的下界截断。

| 项目 | 开发目录 | 源码基线 | 实际pytest | 真实只读 |
|---|---|---|---|---|
| 旧 | /root/knowledge_database_builder-from-type-count | HEAD a36efc7245dedf2492f5be396f87390885f3a4f4，加实际运行engine1137283/servicec4f81快照 | 218通过=88新增+130既有 | 12进程内HTTP/native一致，5实现文件hash与最终manifest相符 |
| 新，指定sg-kg既有会话负责 | /root/kdb-forge-learning-count-20261008 | HEAD 9d5b8de140fd910a57733657185dfb31e19b984b，加其原未提交源码快照；branch codex/learning-count-api-20261008 | 322通过=134新增+188既有 | 12计数HTTP/native一致，另3空名HTTP成功0，含原Basic认证流程 |

上述是隔离实现与进程内HTTP验证。旧、新运行服务均未加载新增端点，本轮没有部署、重启、commit/push、切配置/路由/别名或ES持久写操作。新项目通过正式codex_tui send_message_to_thread已送达用户指定既有thread01a0f061-f2ad-7b10-985c-cd856ca8a7bd，不新开替代会话，不把旧实现派给新项目。

独立跨项目输入模型36组：接受/拒绝、默认值、别名冲突/保真和本地时间规范化完全一致；新端沿用既有认证，旧端保持其现有认证边界。两版计数严格模式检查count非负整数、完整分片、失败/提前终止标志，旧count方法的未显式严格调用默认语义保留；原CRUD/检索请求模型不变。新统计路径只读初始化避免自动ensure/embedding，不改变正常检索初始化。数据返回形状和错误可观测性见各版本报告与证据，不能用配置选中了8.17作为语义验收证明。

真实重点索引默认chat_auto：mercado_local新387，旧原生388；窗口9/1至10/8新50/旧51；payoneer_olive新旧均4939，窗口均2378。Local的一条差额已在早先只读证据定位为10/7源端新增记录24522b3f0f2566e6606121d75920ad3e的新端缺失。本轮不写数据追平或添加条件掩盖差额。新统计API对其所查集群与原生_count一致，不代表旧、新数据冻结一致。

**类目继续测试**

在前148配对后追加89配对/178服务请求，Local40、Olive49，25search/64web；0通信/业务错误。每端462次来源定位全成功无歧义；有效限制439次命中均符合。23组非空文本web的独立BM25+类目计数全部相符；5组小集合完整ID集合也相符。

仍有边界和未关闭问题：

- 显式category_ids=[]：旧新search均0，web均取消类目限制；3组严格负控制出现各23次命中。属于既有入口契约差异，要决定空数组与省略是否同义，不归为新版迁移回归，当前未修改业务。
- Local大集合total_count下界：5组旧新同为10320，原生精确10863。原total.relation=gte丢失，不代表少543条文档。新countAPI使用精确_count；它没有修原web接口的total表达。
- 21个QA正控制首条17一致、全序10一致；合法类目内仍有排序与相关性差异。此轮不保证召回/重排等价，不用ANN随机性概括所有原因。
- 第3/4级、图片类目、大集合完整稳定分页、默认高分阈值全覆盖、压力并发和增量全库一致性仍未实测。未分类与默认组按实际源集合区分，不能把没有类目但已迁移的记录称作新版遗漏。

**可审阅交付**

- 旧实施报告：/root/knowledge_database_builder/docs/reviews/from_type_count_api_implementation_20261008.md；增量diff：/root/knowledge_database_builder-from-type-count/docs/reviews/from_type_count_implementation_20261008.diff；文件/SHA：/root/knowledge_database_builder-from-type-count/docs/reviews/from_type_count_implementation_manifest_20261008.json；真实evidence：/root/knowledge_database_builder-from-type-count/docs/reviews/from_type_count_readonly_20261008/evidence.json。
- 新指定会话已产出交付报告：/root/kdb-forge-learning-count-20261008/artifacts/learning_count_api_20261008/delivery_report.json；功能增量patch：/root/kdb-forge-learning-count-20261008/artifacts/learning_count_api_20261008/implementation.patch；文件/SHA：/root/kdb-forge-learning-count-20261008/artifacts/learning_count_api_20261008/implementation_manifest.json；pytest XML：/root/kdb-forge-learning-count-20261008/artifacts/learning_count_api_20261008/offline_regression.xml；真实只读：/root/kdb-forge-learning-count-20261008/artifacts/from_type_count_readonly_20261008.json。交付时逐文件SHA与manifest匹配，原226基线文件0变化、隔离内0非预期修改。
- 类目报告：/root/knowledge_database_builder/docs/reviews/es817_category_filter_continue_20261008.md；summary、manifest、脱敏配对与成员证据同名目录，补测..._unclassified目录单列，保持既有148组文件。
- 共同请求对照：/root/knowledge_database_builder-from-type-count/docs/reviews/from_type_count_request_parity_20261008.json，36例不混计pytest数量。

原旧目录运行engine/service/business哈希与PID3214210、10/5启动时间未改变。新项目原未提交现场与迁移保持；实现patch相对现场快照，不包括其其他预先存在迁移/检索修复。没有将本轮测试通过扩大为ES8完全替代或生产上线许可。
