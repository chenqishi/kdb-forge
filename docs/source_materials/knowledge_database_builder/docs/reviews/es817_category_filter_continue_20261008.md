**mercado_local / payoneer_olive 类目过滤继续测试，2026-10-08**

在先前148组基础上新增 **89组真实新旧配对、178次服务请求**，其中Local40组、Olive49组。测试对象仍是旧目录8003，旧端ES7、新端8.17原物理索引；未修改检索实现、运行配置或任何真实ES数据，也未重启、部署、commit/push。学习量接口的实施由主会话另行处理，不在此子任务内。

实际合法非空类目条件没有发现串类目。旧新各462次命中均从原公私库独立定位来源，0无法定位、0仍歧义；其中439次符合实际预期条件，另外23次属于下面的**空ID数组契约差异**。不能将这些差异说成新版独有迁移回归，也不能把两端同错、前几条符合、HTTP200认作完整验收。

| 新增范围 | 配对数/结果 |
|---|---|
| `/search` QA | 25组；21组有真实正命中，另外4组为矛盾/空ID负控制。正命中首条相同17/21、完整顺序相同10/21 |
| `/web_search` | 64组；其中23组非空文本，独立BM25文本+类目计数两端23/23相符 |
| 小集合完整ID集合 | 5组/每端；均与独立原生全量小集合相符，不只是条数相同 |
| 通信/业务错误 | 178次均成功，无HTTP错误或HTTP200错误哨兵 |
| 来源复核 | 旧新各462次命中出现次数，共924次；不是924条不同知识 |
| 新增计数查询 | 主84组缓存未命中316次、补5组20次，共336次实际精确`_count`调用；另有两次预检各8次count、有限采样/mget等只读请求 |

原148组证据原样保留，合计执行237组配对。该合计是批次数，不意味着所有字段/任意组合已穷举。

**覆盖的实际数据和条件**

Local：业务地区-墨西哥、业务地区-巴西、默认分组、服务商信息。Olive：TikTok Shop墨西哥/印尼/东南亚/美国ACCU及父类、Noon、Bol、Chewy、Walmart、默认分组、eMAG。既存QA标题作可追溯正控制，另使用历史问题“入驻美客多需要什么材料？”和“TK 小店保证金能退到 P 卡吗”，来源与原记录ID都保存在matrix中，未杜撰业务数据。

实际测试父ID、父级字段、精确父路径、子ID数值/字符串、两个子ID数组、父子ID数组、父级AND子级、互斥ID与路径、OR两组、单审核状态、QA/segment类型集合、显式del_flag=1、文件AND类目、完整名称路径转换及名称+ID联合。数组category_ids为任一ID命中；同时传category_names与category_ids在既有业务层合并成OR联合，不能误以为两个字段是AND。本轮没有要求上游换字段或换物理索引。

所有非空文本web条件的计数使用独立DSL：精确类目条件加原BM25的title/content/indexes.text/synonyms_title匹配，并使用非限制分数阈值。没有拿“所有类目成员数”冒充带文本查询总数。两端23组都相符；本轮未验证默认5.3阈值下的全部计数行为。

**新增明确的接口差异：空category_ids在两个入口的含义不一致**

最小复现之一：

```http
POST /web_search
```

```json
{
  "text": "",
  "client": "mercado_local",
  "index_names": "mercado_local,mercado_local_mercado_local_admin",
  "condition_dicts": [{"category_ids": []}],
  "page_size": 10,
  "page_num": 1,
  "score_threshold": -1
}
```

旧新均返回10条、total_count=10323；原生空terms成员数为0。Olive同形请求也均返回10条、total_count=11260。`/search`同样空ID数组仍作为空terms发送，旧新均0条。第三个有其它字段的控制，在Local限定三个确实没有类目的既存ID后加category_ids=[]，旧新仍返回这3条，证明只是类目限制消失，ID限制没有丢失。

根因是未改动业务代码`search_index_data_interface.py:1342–1347`：取出category_ids、pop原字段，仅非空时写回。它与先前CAT02名称转换失败丢限制是同一流程；这是**旧新共有的入口契约差异**，不是新版引擎的terms空数组失效。23次命中按“显式空数组必须无匹配”的严格负控制预期均不满足，但若现有前端把空数组约定成“未选类目”，就不能直接称23次为越权/错误召回。必须明确省略字段与显式空数组的口径；此报告记录待用户确认，不擅自修改业务实现。

**既有问题仍在：total下界与类目内排序**

Local父ID、父级字段、两子ID联合、父子ID数组、OR两组共5组，旧新均报total_count=10320，而独立精确count=10863。与前报告CAT04一致：公库超过10000时原生total.relation=gte，服务只取value并加私库320。不是此次缺少543条知识，也不代表前10条串地区。代码位置`es8_search_interface.py:530–533`，旧代码亦只取total.value。3组空ID数组的“总数与严格空terms不同”另属上面的入口契约差异，不和gte问题混算。

QA21个正命中组中4组新旧首条变化；不是只剩浮点分数误差。Local父AND子限制墨西哥、历史入驻问题，旧首条偏“在美客多墨西哥站销售产品需要支付哪些费用？”，新首条为“法人（公司）在 Mercado Libre 注册需要哪些文件？”，Top5只重合1条。该例新首条更贴近材料问题，但不能据此证明总体升级更好。Olive把保证金问题限制TikTok墨西哥，旧首条是物流退货处理、新首条是退款IVA/ISR；两端均没有直接回答保证金退P卡，属于共同相关性不足，未审核或改写知识。

另有**相同筛选集合、不同表达形式改变排序**的对照：两个子ID放在一个数组，和拆成两个OR条件组，Local原生成员数均8285、Olive均1527。数组写法这两组新旧Top5完全相同；OR写法这两组新旧Top5都只重合1条，且同一端数组/OR排序也不同。当前两引擎的属性条件处于计分bool.must，此事实与此前评分/候选截断证据一致；本轮没有做相同query向量的候选评分拆分，不能仅凭本对照断言全部因果，更不能未经实证归为ANN随机性。精确合法类目过滤通过，候选和最终排名等价仍未通过。

**默认组、未分类、分页实证**

Local两端各10条有效记录缺primary_category.category_ids。限量抽取其中3条QA：两端按ID均能取回；加category_ids="1"均0。显式存储默认类目ID=1的Local/Olive各一个控制，两端均正确取回。说明“未分类”和“默认组”是不同存储成员集合，不能把默认组查不到无类目记录说成新版漏迁移。Olive两端有效样本集合的missing-category原生计数均0。

Local服务商信息精确成员数2，page_size=5第1页均返回完整两个ID，第2页均空，符合耗尽语义。工具初版统计中zero_despite_members=1指的正是这组第2页，不是知识漏召回；原始统计保留，解释/最终摘要排除这条诊断误报。Local默认组第1/2页、Olive eMAG第1/2页也已检查实际成员与返回量；未全量翻完这两个大集合，不能认定完整稳定分页验收。

Local默认组精确计数旧850/新849；当前旧公库11436、新11435，私库总数同为343、其中del_flag=0均323；这不是冻结相同快照。此前已经记录旧端新增数据未同步，本轮没有追平或全库校验，也不使用这个差1解释所有排名变化。第三/四级有效类目在四个真实索引两端均0，本轮没有造数据写ES；因此这两级保持未实测。Olive公库60项类目聚合仍有sum_other_doc_count=10，明确不是全量taxonomy覆盖。

**环境、复现、交付与边界**

基线旧目录main/`a36efc7245dedf2492f5be396f87390885f3a4f4`，保留此前所有脏改动与未跟踪现场。新端使用原8003旧项目服务，PID3214210，启动时间2026-10-05 20:46:59 CST。前后哈希相同：

| 文件 | SHA256 |
|---|---|
| `knowledge_interface_tools/es8_search_interface.py` | `113728335ebede4733b0d445f030c9117b2ac224cf7c1be92bbebe6bbafba502` |
| `knowledge_interface_tools/search_index_data_interface.py` | `224e12340f627a5b9e5bde0ac6c934f78f072eb7ffc804dc290ce18d944c385e` |
| `knowledge_database_search_service/src/knowledge_database_search_es.py` | `c4f81d69c59159b57072bf10253e2055232cb74224ea4d905c843799511a72db` |

新增工具`tests/es817_category_filter_continue_20261008.py`及8份函数schema；每个函数先写/读schema再实现，没有架构变化。AST语法及函数schema对应检查通过；本轮为真实限量集成测试，不是新增89条pytest，也没有重复宣称之前120项或148组通过。

实际主要命令：

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/knowledge_database_builder \
  /root/kdb-forge/.venv-es817/bin/python tests/es817_category_filter_continue_20261008.py \
  --phase prepare --output docs/reviews/es817_category_filter_continue_20261008
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/knowledge_database_builder \
  /root/kdb-forge/.venv-es817/bin/python tests/es817_category_filter_continue_20261008.py \
  --phase run --output docs/reviews/es817_category_filter_continue_20261008
# 另一次--phase run使用 ..._20261008_unclassified目录中保存的5组精确matrix
```

借用已有8.17测试venv作为解释器，没有改动新项目或环境。旧ES7用原生HTTP客户端，不用ES8客户端打ES7。每组请求前先HEAD四个既存原索引，禁止给自动建库的服务未知索引名。

证据目录：`docs/reviews/es817_category_filter_continue_20261008/`及`..._20261008_unclassified/`，包含预检完整mapping/计数/服务状态、实际类目发现、最小来源fixture、exact matrix/查询来源、配对回复、按源独立条件证据、source cache、native count缓存、statistics、执行日志、最终脱敏summary/manifest及工具diff。数据目录0700、文件0600，没有凭据或向量数值。原始配对和诊断统计没有被修正结论覆盖。

本轮未验证第三/四级实际数据、全Olive平台/全部TikTok站点、任意条件字段与时间/复杂cursor/sort、默认高分阈值下全分页、图片类目、固定大样本召回/重排质量、并发压力、全库增量一致性、真实CRUD写入。新增只读计数API由主会话处理，不扩展本子任务真实写权限。过滤成员正确、总数准确、候选/排名等价及业务回答相关性分别判定；当前仍不能宣布完全替代。
