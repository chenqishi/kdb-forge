# 旧目录 ES7 / ES8.17 独立 query 对拍

任务：用户要求自行抽取一批 query，对比一致性、差异原因和效果。2026-10-05，主批执行时间北京时间 **23:03:41–23:06:45**；随后完成只读归因及重复查询。此次新增测试工具和证据，**未修改引擎、业务实现、运行配置，未重启、部署、commit/push或写 ES 数据**。

## 结论

**并非完全一致。QA 前五条稳定，segment 有实质变化，而且有改善也有退步。**

| 比较项 | QA Top20：30组 | segment Top5：30组 |
|---|---:|---:|
| 首条相同 | 30/30 | 25/30 |
| 前五条及顺序相同 | 30/30 | 13/30 |
| 全部结果及顺序相同 | 27/30 | 13/30 |
| 结果集合相同 | 28/30 | 13/30 |
| 共同命中 / 旧版总命中 | 598/600（99.67%） | 124/150（82.67%） |
| 共同命中的正文/业务字段变化 | 0 | 0 |
| 服务错误、空答、错误哨兵 | 0 | 0 |

这里的“相同”按 API 返回 `(dataset,id)` 判断，正文比较 q/a/content/ext_info/metadata/primary_category/synonyms_title，时间戳和 score 单列。**同一 ID 的实际物理位置另用原请求中的两库 _mget 解析**：API dataset 会优先沿用文档内的 dataset，例如 mercado_local 中的记录可显示 mercado，不能直接拿 API dataset 当物理索引。

全部5组首条变化各向新旧服务重复请求一次，**十次的结果顺序均与初次相同**。这不是本次偶发排序抖动。证据：[重复查询](es817_independent_query_compare_20261005/repeat_evidence.json)。

## 样本和请求

五个平台各6条，共30条独立样本：15条既存历史/回归问法、15条从旧库已审核非删除 QA 标题抽取的正向控制。历史类包含上下文补全问法、既有测试问法及一条移除邮箱的问法，各自来源已标注；**不能把它们统称为30条随机真实用户历史，也不能据此声称线上覆盖率**。标题类从旧公库按 _doc 取最多60条，再从有效、去重标题的首/中/尾位置选3条；为可追溯方便保留源 ID，重建后 _doc 顺序可能变化，复现须使用保存的 samples.json。

QA 使用真实原 workflow 请求：private,public；top_k20；threshold0.4；audit_result=[1,2]、data_type=[qa]；use_synonyms=true。segment 使用 public,private；top_k5；threshold0.4；data_type=segment；use_synonyms=true；业务按原逻辑补 audit_result=[1,2,-1]。没有调整上层请求。120次 HTTP 顺序请求，轮换旧/新先后，间隔0.15秒，单次60秒超时，无自动重试。

旧服务：120.77.147.247:8003，原 ES7.10；新服务：sg 本机127.0.0.1:8003，**/root/knowledge_database_builder 旧目录**，ES8.17 PaaS/Serverless。所有十个原名公私库先 HEAD、确认非空，没有请求不存在的测试库，避免 /search 自动建库副作用。

| 平台 | 公库 / 私库 | QA 全序相同 | segment 全序相同 | segment 首条相同 |
|---|---|---:|---:|---:|
| mercado | mercado / mercado_mercado_local_admin | 6/6 | 1/6 | 4/6 |
| payoneer | payoneer / payoneer_payoneer | 6/6 | 4/6 | 6/6 |
| payoneer_olive | payoneer_olive / payoneer_olive_payoneer_olive | 5/6 | 4/6 | 5/6 |
| wayfair | wayfair / wayfair_wayfair_test2 | 6/6 | 1/6 | 5/6 |
| mercado_local | mercado_local / mercado_local_mercado_local_admin | 4/6 | 3/6 | 5/6 |

历史/测试类：QA全序13/15、首位15/15；segment全序3/15、首位10/15。标题控制类：QA全序14/15、首位15/15；segment全序10/15、首位15/15。标题控制显著更容易命中，不能混合后夸大实际用户问法效果。

## 首条变化的实际相关性

逐条查看原文；只评价“文本是否能回答当前问法及有没有明显串主题”，不做知识审核、不改变 audit_result，不断言平台政策事实已核实。不使用 ES 原始分数或本地余弦大小代替相关性判断，也不把目录里的外部链接当作已读取的回答。

| query / segment案例 | 旧首条实际内容 | 新首条实际内容 | 判断 |
|---|---|---|---|
| 在Allegro平台，回款周期是多久一次？ / Olive-H1 | 新账户欢迎计划、佣金折扣及促销优惠，不含回款频率 | 账户管理中的回款：银行对公账户每月1号和14号；第三方账户自主设置 | **新结果更好**，直接包含问题所需信息；这里仅判断相关性，政策时效另需审核 |
| 要填Wayfair申请流程里的推荐码吗？ / Wayfair-H2 | 入驻邀请邮件、填写企业问卷、入驻联系人；未直接说明推荐码 | 产品安全认证、检测实验室、OSHA等 | **新结果更差**，从相关入驻说明变为另一业务主题；旧结果也不构成完整答案 |
| 我的KYC审核不通过怎么办 / Mercado-H3 | KYC注册步骤、资料一致性及收款方式设置 | KYC帮助目录和国家材料链接、网站页脚 | **新首条可直接利用的信息减少**；新Top2仍有股东证明书说明，不能把首条下降说成整个Top5都变差。旧首条也未直接说明拒绝原因 |
| 发下入驻链接 / Mercado-H1 | 填表须知：主营平台链接、指定邮箱才能收到邀请 | 近乎同一段文字，图片URL及文档ID不同 | **实质内容接近，均未直接给入驻申请链接**；不是首条ID变化就一定变差 |
| 我想入驻，目前月均销售额1万美金左右 / MercadoLocal-H3 | 巴西微型企业ME注册及年收入上限说明 | 申请品牌官方店铺的一组链接 | **均不能直接判定这位客户的入驻资格**；新旧都需要更多业务上下文，不能把新分数稍高解释为改善 |

以上5组更完整的 ID、旧新前3条和判断依据见 [人工相关性记录](es817_independent_query_compare_20261005/manual_relevance.json)。其他尾部变动也有新增有用正文替换纯图片、以及活动问题混入财报/入驻说明的情况，不能从首条一致推导整个结果集质量一致。

**一致也可能不够好。** 本批新旧 QA 首条均存在：Noon修改收款账户命中“Bol后台无法自行更改收款账户”；Wayfair推荐码命中“Wayfair推荐产品功能”；Wayfair再开几个店铺命中“单一商品列表销售多件商品”；美客多本土入驻材料命中“收货服务地址信息”。Olive 的 eMAG 物流标题控制虽在 QA 正确命中自身，segment 首条却是 Bol 物流；DSCO/FedEx 对接标题控制的 segment 首条是 Fyndiq 联系人。这些是本次观察到的旧新共有召回/排序质量不足，**不能归因于迁移新增错误，也不能因与旧版一样就判为好结果**。QA15条标题控制全部命中自身只说明这些正向控制成功，不等于所有业务问法满意。

## 原因：已证实与未确定分开

### D01：候选评分组成发生变化，旧候选在本地重排之前被截掉

**不是仅仅“ANN大概不准”。** 对5组首条变化，用同一个实际模型生成的query向量分别查询旧新原生路由，保留原属性条件，读取实际候选；再单独测属性条件分值，并用保存向量在本地算余弦。共40个候选文档的评分拆解，原生观测与计算最大误差小于 **4.8e-7**。

旧向量路得分 = 属性条件得分 + max嵌套cosine；新向量路得分 = 属性条件得分 + (1+max嵌套cosine)/2。向量的仿射变换**单独使用**时不改变排序，但本引擎在外层 bool.must 中保留有分值的属性条件，因此两者叠加后相对权重变了。[ES8.17 cosine 分值公式](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/dense-vector.html)、[bool.must/filter评分规则](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/query-dsl-bool-query.html)支持这一解释。

**属性条件本身的分值也不同**。仅 data_type=segment 的 term 查询，真实 _explain 显示 IDF 的 n/N 已变化。例：Mercado 的旧KYC说明7a34...，n/N旧523/8016、新509/7514；新首条目录ce416...，旧776/8935、新477/7247。旧索引已有大量 Lucene 删除文档统计，重建后多数消失；公库虽同为3主分片，字段统计并不相同。Local私库更从3主分片变为1主分片，term分数从不同分片的1.8971/1.8206变为统一1.3805。**_stats.docs.count/deleted含nested底层文档，不能当业务知识数。** 删除统计、分片和字段统计的差异均有实证；没有声称删除统计单独解释了每个 BM25 尾部变化。

具体例：Mercado-H3，旧KYC说明的cosine=0.797707，旧属性分4.728783、旧向量路总分5.526490；新属性分4.691226、新预计总分5.590080。帮助目录cosine=0.780434，旧属性分4.443047、旧预计总分5.223481；新属性分4.719916、新实际总分5.610134，反超。两条向量和正文都相同，评分组合足以解释这两条的相对位置改变。HTTP最终本地score仍是旧业务公式，丢掉的候选没有进入该阶段，业务重排无法再把它找回来。

在5个segment控制中，仅将新原生 num_candidates 从100增到500，k仍5，**均未补回缺失的旧向量Top5文档**；扩大k/size到20并用500候选，则15个缺失旧向量候选中的14个回到可见集合。该实验仅诊断候选截断，**没有改线上参数，也不构成“扩大候选即可完全等价”的验收**。k是每分片候选数，最终size另行截断，不能将k说成整个请求的唯一全局预算。[8.17官方KNN说明](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/query-dsl-knn-query.html)。

这项需要在引擎候选评分/预算中解决，保留native KNN和旧业务重排。单纯乘2只能校准向量斜率，不能恢复重建前的属性/BM25字段统计；移除属性评分或扩大候选也会改变旧候选契约，不能未经复验就称完整兼容。

证据：[候选对照](es817_independent_query_compare_20261005/candidate_evidence.json)、[40条评分拆解](es817_independent_query_compare_20261005/score_decomposition.json)、[真实IDF解释](es817_independent_query_compare_20261005/attribute_explain.json)。代码位置：旧es_search_interface.py的1043/1260/1289/1328；新es8_search_interface.py的391/426/458/509/865；业务search_index_data_interface.py的1124/1360/1382。

### D02：同义问法向量的返回口径不同，部分QA共同命中得分小幅提高

存储向量没有变化，但旧dual对BM25-only结果排除 indexes.embedding，没有向量路inner_hits可补；当前新服务返回完整source，因此这批共同命中可利用全部同义问法向量。例：Olive-H1的“eBay回款周期”f9d65...两端都只被BM25召回，旧返回nested向量0个、新7个；本地score从0.885432到0.888920。Olive-T1“eMAG平台如何入驻？”e47f...旧0个、新3个，0.844540到0.852387。业务公式并未改变，输入不同，导致差分。主批共4组有大于1e-6的共同命中score差异；其余共同score差仅浮点舍入。

新旧QA前五仍全部相同，但尾部发生2组集合替换、1组同集合换序。这批证据不支持“新旧score必须逐字相等”，也不支持忽略向量输入差异；如要恢复旧口径，必须同时保留向量路回填，不能单独剪掉字段。

### D03：已发现增量数据差异，但它不解释本批QA/segment变化

十库核验：Mercado旧22467、新22466，另九库count相同。旧多的一条：21a06a620a341eab49125da0fa29edfd，“美客多周报/申报时，如果上周一已经填过，今天还需要重新填吗？没有填的话有什么时间要求？”，insert_time=2026-10-05 18:04:59，audit_result=-1、data_type=qa、del_flag=0；新端 _mget不存在。时间晚于原迁移完成记录，属于后续新增待同步线索，不能当作原冻结批次必然漏灌的证明。它不满足本批QA的audit1/2，也不满足segment类型，因此**不能拿这1条缺失解释这60组排序差异**。

针对首位、替换候选和共同score变化文档，解析实际物理位置后读取115条：**全部两端存在、115条向量相同、正文及删除标记相同**；仅Payoneer两条活动记录的insert_time/update_time不同。这里确认的是抽查范围，不是全量一致性验收。证据：[source对照和缺失记录](es817_independent_query_compare_20261005/source_evidence.json)、[十库预检](es817_independent_query_compare_20261005/preflight_before_run.json)。

### D04：当前运行引擎仍有inner_hits过滤残留，完整source暂时遮住了它

8组真实原生诊断中，新vector路的inner_hits embedding均空；当前请求仍以相对text/embedding过滤，运行源码约503行，旧使用indexes.text/indexes.embedding。但当前根source完整返回，嵌套向量仍在，因此本批并未观察到服务重排向量丢失或score归零。**若未来恢复旧lean source而不先修过滤，会再次丢重排输入。** 不能将“当前完整source可用”说成该inner_hits缺陷已经关闭。此前复审已有此问题，本轮不是新发明缺陷，也没有加载隔离checkout的广泛审计修复。

## 验证范围和成本

- 主批120次真实/search，补充复查10次；没有向运行服务发insert/update/delete请求。
- 8组原生路由控制：48次限量_search，同query向量分别用于旧新，旧调用仅网络/索引解析边界mock以捕获真实构造的DSL；新使用当前真实builder。5组评分拆解：每组两次_search、两次_mget，另外读取mapping及12次限量_explain。没有把离线mock写参数称为真实写成功。
- 115条source抽查，_mget每批<=40；原生_search每次size<=60。额外AliEmbedding调用13次，未调用LLM评审；向量数值只留内存，证据只保存维度、指纹和标量。
- 工具本地9项比较/写阻断断言通过，无网络；真实主批及诊断最终通过。第一次诊断工具将_source:false放在_mget body被400拒绝，已修工具请求并重新执行；这是工具请求错误，不计引擎缺陷，不隐瞒为成功。
- 单线程主批HTTP耗时中位数旧0.686s、新1.639s；新旧地址、网络位置、embedding调用不同，**不是同机压测或吞吐验收**。QA原生响应新完整source往往更大，当前serial四路请求与源数据回传值得单独评估，不能本批直接宣称性能优劣已定。
- 没有执行/search之外的/web_search端到端对拍，没有相同冻结全量query集、人工相关性金标、远程压力、真实写/脚本测试；没有验证全部index或所有CRUD。前轮120/130项离线测试不作为此次30query的新增测试数量。

## 基线、工具和复现

运行源码目录 /root/knowledge_database_builder，main HEAD a36efc7245dedf2492f5be396f87390885f3a4f4加既有未提交修改；服务PID3214210，最近启动2026-10-05 20:46:59 CST，本轮未改变。

| 实现 | 本轮开始及结束SHA256均为 |
|---|---|
| es8_search_interface.py | 113728335ebede4733b0d445f030c9117b2ac224cf7c1be92bbebe6bbafba502 |
| search_index_data_interface.py | 224e12340f627a5b9e5bde0ac6c934f78f072eb7ffc804dc290ce18d944c385e |
| knowledge_database_search_es.py | c4f81d69c59159b57072bf10253e2055232cb74224ea4d905c843799511a72db |

新增只读工具为tests/es817_independent_query_compare_20261005.py和tests/es817_independent_query_diagnose_20261005.py，对应function_schema已先写后实现；没有架构变化。源文件及证据哈希见同目录manifest.json。全量服务回复存paired_responses.private.json（0600，证据目录0700）；报告及脱敏索引/标量证据不保存凭据或向量。保留所有既有未跟踪文件和脏改动。

```bash
cd /root/knowledge_database_builder
# 重跑使用已保存samples.json；prepare重新抽样可能因_doc顺序改变而产生另一批标题。
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/knowledge_database_builder \
 /root/kdb-forge/.venv-es817/bin/python tests/es817_independent_query_compare_20261005.py \
 --phase run --output docs/reviews/es817_independent_query_compare_20261005
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/knowledge_database_builder \
 /root/kdb-forge/.venv-es817/bin/python tests/es817_independent_query_diagnose_20261005.py \
 --output docs/reviews/es817_independent_query_compare_20261005 --sources \
 --cases mercado-H3:segment mercado-H1:segment payoneer_olive-H1:segment wayfair-H2:segment \
 mercado_local-H3:segment payoneer_olive-H1:qa payoneer_olive-T1:qa mercado_local-H1:qa
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/knowledge_database_builder \
 /root/kdb-forge/.venv-es817/bin/python tests/es817_independent_query_diagnose_20261005.py \
 --output docs/reviews/es817_independent_query_compare_20261005 \
 --score-cases mercado-H3:segment mercado-H1:segment payoneer_olive-H1:segment wayfair-H2:segment mercado_local-H3:segment --repeat
```

复现应先把samples.json复制到新的报告目录并使用新--output，保留本次冻结证据；上述路径仅展示原执行参数。索引被删/不存在或空时工具拒绝继续，不自动建库。评分统计和实时新增可能随时间变化。

逐query结果、来源和各组差异：[30条抽样清单](es817_independent_query_compare_20261005/samples.json)、[60组摘要](es817_independent_query_compare_20261005/paired_summary.json)。
