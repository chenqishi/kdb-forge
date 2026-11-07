# Wayfair检索只读检查（2026-11-02）

检查时间：北京时间18:37–18:39。结论：**main上的wayfair索引和抽查检索链路正常**，6次服务请求均返回真实知识，无错误占位。

当前路由为Serverless，服务端版本8.17.0。原始总文档数69,230，计数分片失败0；显式条件 `del_flag=0 AND quality_level=high AND audit_result IN [1,2,-1] AND data_type=qa` 下为19,056条。该条件计数包含待审记录，不等于所有入口默认可见数量。main HEAD为3aa4aadc854fd8e8fc6f31555754799882fbabd8，配置SHA在证据中记录。

| 入口与场景 | 返回 | 耗时 |
|---|---|---:|
| main本机 `/web_search`，空文本分页 | 3条真实知识 | 53ms |
| main本机 `/web_search`，关键词STP | 返回3条，总匹配74 | 258ms |
| main本机 `/search`，已有STP考核标准问题 | 3条，样本ID首位 | 331ms |
| main本机 `/search`，已有超过60天未回款问题 | 3条，样本ID首位 | 421ms |
| main本机 `/search`，Wayfair入驻需要什么资料 | 3条，包含供应商入驻信息相关知识 | 349ms |
| sg经main公网8003 `/search`，STP考核标准 | 3条，与main该请求ID及顺序相同 | 582ms |

两条精确标题样本预先用原始ES只读查询选取已审核high QA；服务调用使用原默认过滤、top_k=3、use_synonyms=true。所有测试均为HTTP200且有实际记录，未将仅HTTP200视为成功。语义入驻查询用于连通性及基本相关性抽查，不代表完整召回质量验收。

空文本分页的total_count=10000为当前接口返回口径，不是索引实际文档数，库存以native count为准。

本轮未检查其他wayfair私有索引、全部类目组合或浏览器前端完整调用链；没有写数据、改代码/配置、部署或重启。脱敏结果和ID证据见 [wayfair_retrieval_health_20261102.json](wayfair_retrieval_health_20261102.json)。
