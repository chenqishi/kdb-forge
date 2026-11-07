# 精确空测试索引清理

2026-10-05 用户指令：“`payoneer_olive_sg_retrieval_test` 这两个不存在的index，直接清除掉，不要浪费位置”。只给出了一个准确名称，因此本轮先执行明确点名项；已通过问题工具询问第二个名称，不替用户猜测不可逆删除范围。

已删除**新 ES8 / PaaS** 的 `payoneer_olive_sg_retrieval_test`，时间2026-10-05 21:40:54 CST。原生 DELETE HTTP200、acknowledged=true；独立GET返回404。

删除前原生只读检查：准确物理名称，没有alias；UUID `pU1U97UhTm6-4JjyiqcaYw`、创建时间2026-10-05 UTC13:04:59.501与本轮wholeagent合成测试记录一致；`_count=0`，primaries docs count=0、deleted=0。复用既有维护流程的 native `add_block(write)` 等待在途写完成，要求 acknowledged/shards_acknowledged=true，再refresh、检查完整分片统计与同UUID/alias、0文档，随后仅删除该准确名称。没有通配符。

wholeagent 当时正在另一轮测试，已先通知并收到“不再查询该名字、停止回放并从测试名单移除”的反馈，避免删除后由旧建库契约自动重建。随后送达删除完成结果；不修改服务自动建库开关来适配测试。

旧 ES7 未删除或写入；真实 `payoneer_olive` 业务库、其它三个 `*_sg_retrieval_test`、`wayfair_wayfair_test2`、默认空库及迁移范围均未由此动作清理。不改实现/运行配置/alias/路由，不重启、部署、commit或push。

第二个索引名称及任何额外集群删除尚未明确，继续待用户回复；第二项不可因建议答案预选或经过时间而自动执行。

证据目录 [es817_empty_test_cleanup_20261005](es817_empty_test_cleanup_20261005)：只读元数据私有备份、请求/返回状态、UUID、删除ACK与最终404、wholeagent通知记录。配置和凭据不写入证据。原本不存在于迁移清单的测试库后来由测试自动创建，本次删除的是该实体，不能把“原先不存在”说成未发生删除操作。

wholeagent 后续实际确认已停止在途旧端回放，后续HTTP白名单排除已删除名称，仅用两端事先存在且非空的10个准确公/私库回放五题，执行无错误；完整报告 `/root/sell_agents/tmp/sg_retrieval_20261004/sg_existing_indices_only_e2e_20261005.md`，脱敏交接摘要及报告哈希见wholeagent_existing_only_confirmation.json。第二项仍未指定，未执行额外ES请求或清理。回放和Agent样本接近不等于全部检索等价：Wayfair segment4/5同位3、Olive QA19/20、Local部分排序/候选差异仍在；报告另记录Mercado旧端22467/SG22466实时数量差异，本清理不修改业务数据来掩盖该差异。
