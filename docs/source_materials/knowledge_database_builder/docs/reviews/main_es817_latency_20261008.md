# main 新 ES8 库只读小样本耗时，2026-10-08

用户要求简化方案，直接在 main 测一遍新库检索，优先保护在线服务。已完成：main（现有 SSH 目标 shenzhen-120，120.77.147.247）单进程、低优先级、串行直接读取现有 ES8.17 库；没有启动测试服务、调用线上检索API、写入main文件、安装依赖、git操作、改变任何服务/配置或重启。

使用当前旧项目实际 EsSearchInterfaceES8._build_search_query 构造 BM25/native KNN 两路查询，来源为此前真实类目矩阵的两个历史问题：mercado_local 墨西哥入驻材料、payoneer_olive TikTok墨西哥保证金。原类目/QA/审核条件沿用，每路返回5条，完整_source保留，包括重排所需的根/嵌套向量。仅查原名公库；没有自动拼私库。实际线上查询同时包含公私库时的全部请求链没有在此测量。

本机生成两个query embedding，两个地点共用同一向量和同一ES地址、DSL/条件。main串行执行4次_search，随后sg用相同的独立标准库HTTP传输再执行4次，调用间隔5秒，无重试、无profile和压测。每地点另有2次版本GET和2次精确索引HEAD；准备阶段sg另有2次HEAD。共18次ES只读调用，另有2次embedding调用。所有集群版本均实证8.17.0，不访问旧ES7。

| 原索引 | main，两路HTTP合计 | sg，相同两路HTTP合计 | main/sg ES took合计 | 完整响应大小 |
|---|---:|---:|---:|---:|
| mercado_local，Serverless | 202.6 ms | 605.7 ms | 30 / 28 ms | 各1355044字节 |
| payoneer_olive，PaaS | 318.7 ms | 764.9 ms | 286 / 29 ms | 669555 / 669554字节 |

四路每次均返回5条，failed_shards=0、无timeout；main/sg各路命中ID和顺序相同。两个地点都保留完整向量，没有通过裁剪字段获得更快结果。单次HTTP计时包含客户端发送及接收完整响应，使用每provider的持久连接；预检已包含连接建立。JSON解析另计：Local两路main19.0/sg22.2ms，Olive8.6/10.1ms；这些解析耗时不在上表HTTP数字内。

这批样本main比sg快约2.4–3.0倍。Local ES took相近而完整HTTP相差约403ms，支持地域路径/响应传输是慢的重要因素；Olive第一次main端ES耗时本身更高，说明服务端缓存或负载也有波动。不能把HTTP耗时减took严格等同纯网络RTT，其中还可能含连接、序列化、响应发送等。ES官方也区分took与请求/响应网络传输：[Search API](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/search-search.html)。这是一次小样本观察，不是P95/稳定吞吐证明，更不是完整/search接口端到端耗时；未计入embedding、业务重排和HTTP服务排队。没有据此更改任何在线参数或召回策略。

main在线检索进程PID307354、启动ticks、工作目录和服务/引擎源码hash前后一致；load1从0.36到0.28，空闲内存充足。sg旧8003 PID3751589、新8012 PID3751674和源码同样前后保持。实际操作没有任何在线服务进程管理、配置写入、ES文档/mapping/alias更新或迁移动作。小量只读ES查询仍会使用共享检索资源，本轮没有做10QPS或并发压力测试，也不把PID未变当作线上P95绝对无变化的证明。

复用既有只读访问方法和历史类目样本，新增工具[main_es817_latency_20261008.py](/root/knowledge_database_builder/tests/main_es817_latency_20261008.py)及5份函数schema，先写/读schema再实现。main探针仅在内存执行，连接凭据经SSH stdin传递，无凭据/向量数值/业务原文落入交付输出。证据目录0700、文件0600。

- [逐请求耗时与前后进程证据](/root/knowledge_database_builder/docs/reviews/main_es817_latency_20261008/evidence.json)
- [汇总、请求数与工具/evidence哈希](/root/knowledge_database_builder/docs/reviews/main_es817_latency_20261008/summary.json)
- 同目录execution.log保留实际执行输出。原入口拒绝覆盖已有证据；再次测试需使用新的输出目录。

实际命令（没有在main复制或覆盖应用代码）：

```bash
env -C /root/knowledge_database_builder \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/root/knowledge_database_builder:/root/knowledge_database_builder/tests \
  /root/kdb-forge/.venv-es817/bin/python tests/main_es817_latency_20261008.py
```
