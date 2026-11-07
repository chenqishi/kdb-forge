# ES8与旧版请求级_source策略差异，2026-10-09

结论：用户指出的差异成立。旧ES7 dual不会返回全部嵌套向量；当前部署ES8的在线召回返回完整_source，字段策略未对齐。已用同一ES8查询、相同命中列表做实测，排除了新旧ANN命中差异：三个QA样本约多19.4%解压响应字节，mercado_local同义问法较多的样本多36.8%。不是“向量条数只多20%”，也不是数据迁移让正文变大。

本轮仅只读诊断和新增本地测试工具/schema/报告/私有反例。未修改引擎/业务实现、运行配置或生产数据，没有commit/push、生产pull、部署或服务重启。用户对每次发布必须明确授权的纠正继续生效。

## 对照源码和真实配置

旧版 `knowledge_interface_tools/es_search_interface.py:32/36/1316/1337` 默认dual，两个召回路的外层请求使用 `_source.excludes=[indexes.embedding,image_indexes.embedding]`。根title_embedding、content_embedding保留；正文、类目和其余metadata也保留。向量路nested inner_hits.size=3，请求字段是完整路径 `indexes.text/indexes.embedding`（1085行），返回相对_source后按offset补入indexes。只有BM25命中的文档不补同义问法向量，会退回根title向量；旧版1342–1347行已明确记录这个取舍。

120旧配置 `/root/dify/knowledge_database_builder/config/config_es_engine.json` 的recall_mode override为null，因此使用旧默认dual。旧实际search_multi、_restore_inner_embeddings、_build_nested_vector_clause的AST与升级前f873a593完全一致；不是拿新增测试期望当旧契约。旧引擎文件SHA1aaebeaf53587f4e9e585fb908d09318c0a0be636eb4f36b8076517fb5c739e7。

当前ES8 `knowledge_interface_tools/es8_search_interface.py:968` 构造body只有query/size，没有_source过滤，全部已存根/嵌套向量返回。494行的inner_hits includes仍用相对`text/embedding`，真实内层_source为空；这是已知残留请求过滤错误。当前外层完整_source提供向量，掩盖了回填问题。本次原生并行改动保留了此前串行ES8的source行为；200组串行/并行严格一致，不等于这个旧版字段契约已经对齐。

旧web分页另有_PAGE_SOURCE_EXCLUDES（四类向量都不返回）；本表针对QA/search的dual召回，不能把它泛化为全部公开入口或所有旧模式都裁同一组字段。请求级_source过滤只控制本次返回，不改变ES持久存储；与先前Serverless“智能过滤向量字段”的存储优化是两个设置。

## 同命中列表的真实只读实验

在120旧目录现有独立ES8虚拟环境、新nice15进程内，使用真实当前类，配置副本ensure=False/autoMapping=False；所有8个原物理名先HEAD存在，不允许自动创建。复用前述200-case私有输入，不额外embedding/LLM。每公库选一个已有title向量、QA、synonyms=true、公私联合查询，每路20条预算，子请求native并发上限2，起始间隔至少0.5秒。

每组依次：①实际当前engine.search_multi，捕获原生full_source请求/响应；②只改实验请求的inner_hits includes为完整nested路径，外层继续完整；③同一query/k/候选/条件/预算，完整inner路径加旧版两个外层excludes。使用真实ES返回，没有手工伪造inner embedding或写索引。

四组的①→②、②→③命中_index/_id、顺序、_score、total均严格相同；非裁剪字段逐值相同；②→③实际inner_hits逐值相同。字段比较包含根向量，根向量没有省略或改值。表中旧策略列是**同一新ES8索引上的旧请求策略实验**，不是旧ES7实际请求。

| 查询来源/公私联合 | 当前完整返回字节 | 旧策略实验字节 | 当前多出 | 旧策略可补回嵌套向量 | 业务similarity变化 |
|---|---:|---:|---:|---:|---:|
|payoneer_olive|5,373,127|4,500,743|19.383%|40|0条|
|payoneer|3,884,388|3,252,692|19.421%|29|0条|
|mercado|5,363,705|4,491,538|19.418%|40|0条|
|mercado_local|6,947,731|5,077,454|36.835%|66|2条|

计量口径是native transport收到的**整份解压JSON响应字节数**，不是线上网络压缩长度、存储占用或合并后文档的向量条数。完整source向量数统计按原始子请求hits计，有同文档跨路重复传输；补回后的merged计数另列，不能混用。

前三组raw hits各80/58/80，当前外层各有80/58/80个indexes向量；旧策略外层为0，向量路inner带回40/29/40个。mercado_local raw hits80，当前外层152个indexes向量，旧策略inner返回66个。这解释了同义问法较多时差异更大，并非固定20%开销。

只修inner includes而外层继续full，会重复传输向量：四组②字节分别6,243,778 /4,515,749 /6,234,242 /8,384,172。减少传输须把请求过滤和正确回填作为整体验证；不能只加外层excludes，让内层仍为空。

此前9,303,064→11,260,868（+21.045%）是实际旧ES7 vs新ES8另一个查询的整份响应比较，当时候选152 vs127，ANN/旧script_score召回列表不同；无法把那次1,957,804字节逐个归因到字段。本次同命中控制实验独立证实字段策略足以产生约19.4%及更大差异，不能声称精确复刻了那次21.045%的所有组成。

## 排序差异反例：旧版BM25-only取舍

serverless-054（mercado_local及私库）①完整source与②完整inner路径后的merged数据完全相同。改为旧策略后68个merged候选仍是相同的68个，但2条只被BM25路召回的文档失去同义問法向量；两条原先各4个indexes向量变为0，title/content根向量逐值一致。不是qualified inner_hits回填失败：两条根本没有进入vector route。

| 身份hash前缀 | vector路命中 | title分：完整/旧策略 | 最终similarity：完整/旧策略 |
|---|---|---|---|
|52744ded…|否|0.7466198503 /0.6822177652|0.8770245179 /0.8126224327|
|99c656d1…|否|0.4973121003 /0.4972181833|0.6009544150 /0.6008604980|

完整数值在脱敏证据中保留；最大下降0.06440208516422208，前20排序不相同，实际好坏未人工评定。该取舍属于旧版已有行为；当前ES8多返向量让原业务消费者计算了更多同义问法分，构成升级后返回/排序差异。不能以“多返字段更保险”宣称旧检索行为完全等价，也不能把恢复旧策略后分数变化描述成新的inner_hits故障。

单case重复6次原生读确认相同结果，已把准确输入及两条完整/旧策略真实文档存入本地0700/0600私有反例目录，公开报告仅hash/分数/数量。路径 `data/es817_source_alignment_20261009_private/serverless-054.json`，394,627字节；可用200输入fixture和--case重复，无需写测试索引。

## 边界和交付

首次4组诊断24次native读；针对反例再6次，0guard违规、0HTTP/分片/超时错误、0持久ES写、0embedding/LLM、0运行服务HTTP。两次结束client关闭，无PIT/scroll。120检索/挖掘进程身份以及守卫中的引擎/Router/业务/service/活动配置SHA前后全部相同。架构无变化。

每公库额外最多2条image_indexes既存向量样本查询，四库均未命中；image路径真实inner回填仍未验收，不据此断言全部数据库没有图片。qualify_inner测试工具按nested.path生成包括image_indexes的完整字段，但没有真实样本就不能当作图片回填验收通过。没有全量扫描、远程压测、真实写入、自然语言query集质量评审或业务流量切换。

工具 `tests/es817_source_alignment_20261009.py`；各函数schema已先补读。只读证据 [首次](es817_source_alignment_20261009/evidence.json)、[反例复测](es817_source_alignment_20261009_repeat/evidence.json)。完成基础语法验证，没有新增实现测试或借此重复未改实现的310项测试。最新工具SHA见manifest；初次证据中的tool hash是尚未添加私有反例捕获时的实际版本，追加诊断没有改动查询和字段实验核心。

复测命令：

```bash
env PYTHONDONTWRITEBYTECODE=1 python tests/es817_source_alignment_20261009.py \
  --fixture data/es817_parallel_100_20261009_private_run3/inputs.json \
  --case serverless-054 \
  --output docs/reviews/es817_source_alignment_20261009_repeat \
  --private-output data/es817_source_alignment_20261009_private
```

输出目录必须新建；已有本次输出不要覆盖，复用时指定新的名字。工具SSH明确禁用remote bytecode写入，只读guard复用200-case实现。

待后续代码修复的具体范围：完整路径inner_hits请求字段（文本/图片）、按入口恢复旧_source策略并保留必要根向量、真实业务回填/重排反例回归；当前只报告，不修改实现或自行上线。源码基线12a86da7163c5136524a60730c6af476788933c5，当前引擎SHA仍9ed795c5b837e8f6b46360ca46e0181feb67b08a288362275efe985111bba223。与 [200-case并行对照](es817_parallel_100_20261009.md) 分开验收。
