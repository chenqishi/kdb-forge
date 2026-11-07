# 按文件软删除：Serverless限制、替代方案和验收边界

2026-10-08，核对旧调用链、历史真实证据与当前隔离集成代码。此次仅解释和记录，没有修改实现、发起ES请求、部署或重启。

## 受影响的调用

`SearchDataInterface.delete_by_file` 按原文件名/类型/审核条件生成query，然后调用引擎 `update_by_query(..., {"del_flag": 1})`。语义是软删除，文档不被物理删除。旧ES引擎发送内嵌Painless赋值；此前目标阿里Serverless实际返回 `script_unsupported`。这是该托管平台的脚本限制，不是ES8取消了update_by_query。PaaS仍走原生服务端更新。

官方依据：[阿里Script白名单](https://help.aliyun.com/zh/es/user-guide/script-whitelist)说明默认禁用、需审批、脚本文本须完全一致，且目前16c以下不开放审批；[ES8.17 update_by_query](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/docs-update-by-query.html)仍支持脚本赋值、快照批处理和冲突统计。当前应用是否具备审批资格，本次未读取其规格或修改白名单。

## 为什么旧版优先用服务端批更新

`knowledge_interface_tools/es_search_interface.py` 的update_by_query说明以及 `docs/按文件名删除知识服务_方案.md` 第5节明确记录：先把成千上万条hits拉回再更新，曾遇到分片取消导致结果不完整，可能误报删完。原生服务端批更新避免把全部正文/向量传到应用侧，支持限流和冲突统计。这一选择有实际理由，不能将替代方案宣称为全面更优。

## 当前替代方案

隔离目录 `/root/knowledge_database_builder-es8-conditional-integration-20261008` 的ES8引擎保持原HTTP参数、query、索引名、ID和业务层调用。仅Serverless分支采用PIT固定快照，每页最多50条，读取完整source，在应用内只赋值指定字段，再以原_index/_id/routing和版本条件批量写回。它不删除重建索引、不改物理名，也不把软删除改成硬删除。

检查失败分片、超时、精确总数和分页游标；不完整结果不会被直接当作全部成功。写入带if_seq_no/if_primary_term，版本已变化时不会覆盖新数据。相关并发控制见[官方说明](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/optimistic-concurrency-control.html)。

## 代价、差异和未验证项

- 完整正文及向量需要从ES传到应用、再传回，应用处理和多次小批请求增加耗时与资源消耗。两种更新方式都会重新索引文档，不能把重新索引成本说成无脚本方案独有。未做真实大批量性能/压力验证。
- 使用开始时的快照，期间新增的匹配记录不自动加入；并发修改冲突按原proceed策略跳过并统计，可能仍需后续复查。这类快照/冲突边界原生update_by_query也存在。
- 中途失败可能已完成一部分，不会自动回滚。当前适配抛出错误，但异常返回没有完整成功前缀统计或持久恢复进度；不能承诺故障后无需复查。原生批更新也非事务，但会提供更多原生任务/失败信息。
- 必须保证存储source完整；配置禁用或裁剪source时拒绝破坏性替换。历史已经缺失的字段不能靠source=True补回。
- bulk设8MiB保护，单条文档加动作超过此限明确拒绝。这是未接受的支持边界差异，不等于所有旧输入已经完全打平。

若当前应用能获准原脚本，保留原生服务端更新可以减少应用侧传输并延续旧流程；是否升级规格/申请白名单由用户决定，本次未实施。无脚本适配是绕过已确认平台限制的备用实现，不能据此忽略其代价和验收空缺。

## 已验证与运行状态

当前集成的更新相关56项离线行为测试通过（41复用、15追加），相关总计300 passed、2既有xfail。进程内HTTP测试使用真实路由、业务、工厂和ES8类，外部ES/embedding边界模拟，不能称真实业务写入成功。

2026-10-05原隔离修复曾在当时批准的合成记录验证del_flag 0→1→0及正文/向量保真；该证据不是当前集成版本真实写验收。本次未重放写测试。当前运行目录未加载此集成补丁，无部署或重启；完整CRUD、压力和故障恢复尚不能统称通过。

集成引擎SHA256 `d9a30277f6464d639a9255800506f8bc9fffeff062834e10cd1839d1df4cd9fc`，与交付报告一致。具体代码/测试证据见隔离目录 `docs/reviews/es817_conditional_update_integration_20261008.md` 及同名证据目录。本说明不改变此前冻结的验收日志和manifest。

## 补充纠正：单字段更新无需全量传输

用户质疑“只是改其中一个字段，为何这么麻烦”。核对后，应区分两个入口：已知ID的单文档更新可用 `_update` 携带 `doc: {del_flag: 1}`，不需调用方提供Painless或读取/回传完整文档；按文件名条件更新需要先找到所有命中ID，原生update_by_query的赋值才涉及被禁用的脚本。

原隔离 `docs/reviews/es817_source_policy_live_20261004.md` 已有真实单文档局部更新、正文和四类向量保真的证据；当前集成类的公开update也使用client.update(doc=...)。不能把禁用Painless扩大说成该部署所有局部更新都不可用。[官方Update API](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/docs-update.html)与[Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/docs-bulk.html)支持局部doc更新。

此前完整source写回是为了统一保留通用条件更新的对象整体替换、字段路径赋值、同值updated统计等语义；这不是del_flag单字段更新必须付出的代价。更轻的候选路径是保留PIT/小页完整性检查，只取_index/_id/routing/版本，bulk update发送局部标量字段，原接口不变。这样可避免正文和向量应用侧往返；ES内部仍需要source并重新索引。对象局部doc合并不能不加区分地替代原来的整体赋值。

此候选尚未替换当前集成中的完整source分支，不能引用原300项测试宣称它已经通过。实施前需补对应schema与行为回归，验证批量doc更新的原routing、CAS冲突、失败统计、same-value计数（默认noop与原脚本updated不同）、禁止upsert和完整遍历；真实组合写测试需要对应授权。本轮只是核对和更正解释，未改实现或写ES。

## 按条件设置对应什么接口

ES原生的_update_by_query就是按query条件在服务端批量修改，对应MySQL的UPDATE ... SET ... WHERE ...。单文档_update可接受局部doc，_update_by_query不接受单文档式doc作为SET参数。旧项目使用script表达赋值，但这不是唯一的服务端赋值路径；它也支持pipeline，内置set可修改字段。不能再将“批准脚本或应用侧更新”说成只有这两个选择，详见下方本轮发现及真实无落盘模拟。

## 重要更正：内置set配合pipeline是另一条原生路径

用户指出普通字段改值理应支持。进一步沿阿里8.17 API支持列表读完“附录二：支持的白名单”，发现此前遗漏的内置set处理器；官方把它与需审批的script处理器分列。阿里同时列出_update_by_query、pipeline创建和simulate API。Elastic8.17官方明确示例：注册包含set的pipeline，再给_update_by_query指定pipeline，即可在服务端按条件赋值，无Painless，无应用侧正文/向量往返。

- [阿里8.17处理器白名单](https://help.aliyun.com/zh/es/user-guide/retrieve-enhanced-supported-parameter-configurations)：set设置字段值，字段存在覆盖、不存在创建；script自定义逻辑另需白名单。
- [阿里8.17 API列表](https://help.aliyun.com/zh/es/user-guide/retrieve-an-open-source-api-with-enhanced-application-support)：Document及Ingest API。
- [Elastic8.17 UBQ的pipeline用法](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/docs-update-by-query.html)：Update documents using an ingest pipeline。

旧语句被script_unsupported拒绝的原始证据仍真实有效，仅证明目标应用当时拒绝那两条具体脚本文本；它不能证明没有其他原生改值方式。先前仅依赖通用Script白名单文档给出的方案不完整，不能将这一遗漏归因于用户或平台。

北京时间2026-10-08 23:34:33–23:34:34，复用旧项目make_client/commons裸HTTP客户端，以既有配置只做两次请求：GET /确认8.17.0，POST /_ingest/pipeline/_simulate，内联pipeline为 `{"processors":[{"set":{"field":"del_flag","value":1}}]}`。模拟输入是三份自造fixture（del_flag为0、1、缺失），其余含正文、ext_info及六条1024维向量（四类路径）。三个输出全部del_flag=1，完整_source与仅改此字段的预期逐值/哈希相同。

无创建/更新存储pipeline，无创建索引、读写业务文档、mapping/alias/route或运行配置变更，无服务启动/重启。模拟是内存执行，不是持久ES写入；借用现有解释器与配置不等于执行新项目。脱敏实证见[es817_set_processor_simulation_20261008.json](es817_set_processor_simulation_20261008.json)。没有重复发送被拒绝的Painless。

后续优先候选为固定del_flag=1的专用pipeline（注册一次、查询时显式引用），保持原文件query、索引名、conflicts/refresh/限流和返回统计，不设index.default_pipeline，不动上游接口。真实应用的pipeline注册及_update_by_query写入尚未授权/执行；模拟通过不等于真实批量更新或完整CRUD验收。实施前还需核对既有default/final pipeline及条件筛选、冲突、失败统计和向量保真，不将本轮模拟计入此前300项pytest，也不覆盖历史验收manifest。本轮不修改引擎实现；当前全source适配仍在原隔离集成目录。

## 2026-10-09 实写补测（承接后续授权）

上述“尚未授权/执行”是当时状态。用户随后明确授权使用 test_case 并复制其他索引样本，已完成真实 Serverless 原生 pipeline/set 条件更新验收：47 条仅测试 fixture，单条/文件 QA 与 segment/多批次/同值/零命中均通过，完整 source 逐值保真；人为故障实测 10 条更新 9 条、失败 1 条，不具事务回滚。新增 9 项离线回归通过，真实失败响应不会被公开引擎路径假报全部成功。

另发现 requests_per_second=1 请求返回 -1.0、无节流，10 条/5 批次 0.639 秒；本部署不能依赖该参数限速，待确认/适配。四个自有临时 pipeline 已删除，47 条 fixture 恢复测试初始值并保留。未改生产/源索引数据或实现、部署、重启。原生候选尚未集成运行服务，不宣称完整 CRUD 验收已通过。完整报告位于 `/root/knowledge_database_builder-es8-conditional-integration-20261008/docs/reviews/es817_test_case_pipeline_20261008.md`，脱敏证据与新 manifest 独立保存，不覆写之前集成验收。
