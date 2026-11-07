**旧目录检索条件、类目限制补测：2026-10-08**

10月5日的30个 query 对拍未覆盖类目限制，也不能代表所有条件组合已经验收。本轮补做148组真实新旧配对。用户最后澄清重点为 **mercado_local和payoneer_olive**；此前另外加测的mercado结果作为额外证据保留，两者不是同一索引。结论：Local墨西哥/巴西及Olive合法ID/路径过滤的实测命中均符合类目，但仍有新旧排序差异；网页查询名称解析失败后会丢弃限制。另外mercado简写路径/名称存在既有漏召回，不能移用这个结论说Local路径同样失效。不能宣布完整等价。

测试对象是旧项目 `/root/knowledge_database_builder` 实际运行服务，不是隔离开发目录中尚未加载的广泛审计修复。旧端 ES7.10.0，新端 PaaS/Serverless 均8.17.0；两端每组请求相同，使用原物理索引名。先 HEAD 确认十个既存公私索引，再请求服务，避免读接口的自动建库副作用。没有修改业务/引擎实现、运行配置或真实 ES 数据，没有部署、重启、commit/push。

**范围和实际计数**

| 批次 | 配对组数 | 内容 |
|---|---:|---|
| 基础条件矩阵 | 95 | 五平台；QA/segment/web；类目路径、ID单值/数组、一级名称/ID、二级名称/ID、完整字段路径；AND/OR、不存在类目、审核、删除、类型、文件限制 |
| 边界补充 | 10 | 名称完整路径、同义评分开关、阈值、top_k=1/5/10、网页第2页、类目+类型+审核 |
| Mercado/Olive重点补充 | 35 | 两平台各5类目，类目ID/路径的QA与segment；Mercado增加完整keyword字段定位对照 |
| Local澄清后重点补充 | 8 | 同query分别限制墨西哥/巴西；QA/segment，ID/路径 |
| 合计 | **148** | **81组QA、24组segment、43组web；296次初始矩阵HTTP请求** |

初始296次中295次HTTP200、没有错误哨兵；Local最后一组旧端一次RemoteDisconnected，无HTTP响应，原样配对重试2次请求均成功。最终148组都有可比响应，保留初次通信失败，不将它猜测为引擎故障。原文复核旧新各792次命中，共1584次，按原请求公私库 mget 确认实际来源，核对类目、类型、审核和删除条件；这些是命中出现次数，不是1584条不同知识。没有无法定位或仍歧义的ID。发现的过滤违规为两端各78次，均来自名称未解析的8个条件组，见下文。其余实际命中未发现条件违规。空结果、阈值主动排空及数据本身无该类型分别记录，不能以零违规推导完整召回。

| 平台 | 全部配对组数 | 重点类目 |
|---|---:|---|
| Mercado | 37 | KYC、Listing管理、FULL仓、财务回款、账户注册 |
| Payoneer Olive | 35 | Noon、Allegro、Bol、TikTok墨西哥、TikTok印尼 |
| Payoneer | 17 | 平台入驻-noon |
| Mercado Local | 45 | 墨西哥、巴西独立与组合；同义/阈值/页码 |
| Wayfair | 14 | 默认分组；该样本不能证明细分业务类目的隔离效果 |

**确定问题及归属**

| 编号 | 实证、影响 | 归属/状态 |
|---|---|---|
| CAT01 P1 | Mercado按简写类目路径或中文名称可能完全查不到；Wayfair路径过滤只命中私库、漏公库 | 新旧均复现的既有mapping/查询不匹配；未修实现 |
| CAT02 P1 | `/web_search` 名称无法转ID时被删除，剩余空条件触发广泛查询，返回不属于所要求类目的知识 | 新旧均复现的既有业务行为；未修实现 |
| CAT03 P2 | 有效类目过滤内，部分新旧QA/segment候选与最终排序仍不同 | 升级后兼容差异未关闭；本轮未逐项量化所有原因 |
| CAT04 P2 | web把原生 `total.relation=gte` 下界当整数总数返回 | 新旧均存在；不能把该数字当精确总数 |

CAT01最小复现：相同query“我KYC上传一直失败，网页报错”，`/search` 使用原公私库、QA、audit_result=[1,2]、top_k=5、score_threshold=0.4。条件中的 `category_path="运营问题类型-KYC 验证"` 两端均0条，使用同类目 `category_ids="2014570291872186369"` 两端均5条。独立精确字段计数两端均有14条符合审核条件的QA；仅定位请求改为 `primary_category.category_path.keyword` 也均5条。重点补测的另外4个Mercado类目简写路径同样0条，ID与完整keyword路径均有命中。

真实mapping显示，Mercado和Wayfair公库的相关类目字段是 `text` 并带 `.keyword`，新旧保留一致。当前引擎 `es8_search_interface.py:347–375` 仅加 primary_category 前缀后使用term/terms；旧实现 `es_search_interface.py:1205`、`:1631` 有同一逻辑。精确term查询不会分析输入，直接用于分词字段可能找不到完整值。[ES8.17 term官方说明](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/query-dsl-term-query.html)、[multi-fields官方说明](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/multi-fields.html)。这是查询/mapping不匹配，不能归为此次迁移丢掉类目数据。

Wayfair新端默认分组的精确计数为公私合计20974，而简写路径web只报256，公库没有召回。完整带.keyword路径也不是全局解决方案：其公库可查，但私库相应字段是keyword，没有同名.keyword子字段，会漏掉私库。**完整字段请求仅是定位对照；修复应保留上游原请求，兼容各索引实际mapping，不能要求上游统一换字段。**

CAT02最小复现：`/web_search`，text为空、page_size=10、score_threshold=-1、原有index_names；条件 `[{"category_names":"__absent_category_20261008__"}]`。五平台旧新均返回10条，独立目标计数0，每条都不满足该限制。三组只传叶子名称（KYC 验证、noon、墨西哥）也放开过滤，两端各出现28次不符合预期类目的命中，另加不存在名称的50次，共78次。

实际业务字典按**完整类目路径**索引名称：`search_index_data_interface.py:192–195`、`:228–236`。因此叶子名不能被当作支持的完整路径；基础证据的 `names_valid` 标签在这三组仅表示叶子名试探，不代表合法完整路径。补充的“运营问题类型-KYC 验证”“平台入驻-noon”“业务地区-墨西哥”完整名称路径均正确转换并过滤，web总数分别21、37、4797，旧新一致。类目树GET均成功并能找到对应categoryId，不能将失败误归为类目服务不可用。

确定的问题在 `web_search_data:1334–1347`：删除category_names、丢掉空的转换结果，随后不写category_ids，导致限制消失。即使输入格式不受支持，也不应该静默扩大查询；后续需明确返回错误/空结果等处理契约。本轮只记录，不更改上层。`/search` 未实现 category_names 转换；其支持的类目入口为category_ids/category_path/各级字段，不能把web的名称转换自动外推到/search。

CAT04对照：墨西哥+巴西组合的精确count为10863（公库10543、私库320），旧新web却均报10320。真实size=0查询公库返回 `{value:10000,relation:"gte"}`，私库 `{value:320,relation:"eq"}`；当前 `_total:529–533` 丢掉relation。这是总数下界问题，本组实际命中没有串地区，也不能据此声称漏了543条已存文档。

**Mercado和Olive重点结果**

用户澄清后加测Local：同query“美客多本土入驻需要哪些资料？”，分别以类目ID和路径限制墨西哥、巴西，QA与segment各一组，共8组。旧新每组均返回5条，80次实际命中及独立source重放均符合地区、类型、审核和删除条件，没有墨西哥/巴西串类目。QA目标计数墨西哥3685、巴西4600，两端一致；segment分别929、1048，两端一致。**两地区QA的Top5每组仅重合2条，首条均变化；墨西哥segment重合4/5，巴西segment5/5且顺序一致。** 类目限制通过不等于新旧检索结果已等价。

下表仅按ID限制、同query的代表QA/segment组；QA均返回5条。各类目符合QA审核条件的原生计数旧新一致。所有276次重点命中都满足实际类目/类型/审核/软删除条件。Top5比较以(dataset,id)为准；少于5条按实返比较。

| 平台/类目 | 符合条件QA数（每端） | QA首条相同 | QA Top5重合 | segment返回数（每端） | segment首条相同 |
|---|---:|---|---:|---:|---|
| Mercado KYC | 14 | 是 | 5 | 1 | 是 |
| Mercado Listing | 702 | 否 | 2 | 5 | 是 |
| Mercado FULL | 59 | 是 | 5 | 5 | 是 |
| Mercado 财务回款 | 9 | 是 | 4 | 2 | 是 |
| Mercado 账户注册 | 15 | 是 | 4 | 0 | 不适用：没有符合条件segment |
| Olive Noon | 193 | 是 | 1 | 5 | 是 |
| Olive Allegro | 158 | 是 | 4 | 5 | 是 |
| Olive Bol | 1363 | 否 | 2 | 5 | 是 |
| Olive TikTok墨西哥 | 393 | 是 | 4 | 5 | 是 |
| Olive TikTok印尼 | 1134 | 是 | 3 | 5 | 是 |

Olive的名称/路径/ID过滤在合法请求中没有发现串平台或串TikTok地区；**这不等于排序和相关性验收通过**。例如Bol入驻条件，旧QA首条是“Bol平台入驻有哪些门槛要求？”，新首条是“Bol入驻介绍”，Top5仅重合2条；Allegro回款query的segment两端都把欢迎计划佣金优惠排第一，均未直接回答回款周期。Mercado“批量修改刊登”两端segment首条均为含批量编辑步骤的文档，但QA首条分别偏商品目录更正/销售条件修改。这些结果只作检索相关性评估，没有审核或改写知识。

另一个受控反例：Mercado Local同query“墨西哥怎么入驻？”、相同墨西哥类目和QA审核限制，use_synonyms=True时旧首条“墨西哥站怎么入驻 Mercado Libre？”，新首条“法人（公司）在 Mercado Libre 注册需要哪些文件？”。只关闭同义评分后两端Top5顺序一致，共同分数差约浮点误差。该例说明排序输入差异必须继续处理，不能以类目过滤正确替代排序验收；没有建议关闭线上同义功能。10月5日已证明的完整source与旧BM25-only嵌套裁剪差异、评分量纲/分片统计见[此前报告](es817_independent_query_compare_20261005.md)，不将本轮全部差异未经分析都归为ANN随机性。

阈值与top_k实际返回检查通过；高阈值1.2主动返回空属于预期控制。显式del_flag=1的15条目标知识中抽取10条，旧新命中均正确。一个相同ID在公私库有不同类目，初版诊断器把不相关私库副本也判入，已通过返回的物理/source元数据独立解析纠正；原始日志保留，最终以resolved证据为准。没有发现该例del_flag过滤失效。另有一条Payoneer源知识两端都缺primary_category，仅在名称失败后的广泛查询出现，不算新版丢字段。

**数据、源码、证据与未验证边界**

本轮预检公库数量：Mercado旧22468/新22466，Payoneer15951/15948，Olive60508/60508，Wayfair38925/38923，Local11436/11435；对应私库数量均相同。合计差8条，相对10月5日新端数量不变、旧端增加7条。不是同一冻结快照，也未在本轮做全库增量追平，不把数量差自动判为迁移遗漏或过滤错误。

源码基线main/a36efc7245dedf2492f5be396f87390885f3a4f4，加保留的既有未提交改动。引擎SHA256 `113728335ebede4733b0d445f030c9117b2ac224cf7c1be92bbebe6bbafba502`，业务层 `224e12340f627a5b9e5bde0ac6c934f78f072eb7ffc804dc290ce18d944c385e`，服务 `c4f81d69c59159b57072bf10253e2055232cb74224ea4d905c843799511a72db`；前后不变。服务仍PID3214210，启动时间10月5日20:46:59 CST。

新增工具 `tests/es817_category_filter_compare_20261008.py` 与对应function_schema，未引入架构变化。实际运行使用既存 `/root/kdb-forge/.venv-es817/bin/python` 作为测试解释器，代码/运行对象仍旧目录；没有修改该venv或新项目。命令为：

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/knowledge_database_builder \
  /root/kdb-forge/.venv-es817/bin/python tests/es817_category_filter_compare_20261008.py \
  --phase prepare --output docs/reviews/es817_category_filter_compare_20261008
# 分别对基础目录、supplement、mercado_olive_focus运行；准确请求保存在各matrix.json
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/knowledge_database_builder \
  /root/kdb-forge/.venv-es817/bin/python tests/es817_category_filter_compare_20261008.py \
  --phase run --output docs/reviews/es817_category_filter_compare_20261008
```

这是实测诊断，不是重跑原120项pytest。工具语法检查、12项独立条件/脱敏断言、3项来源解析断言及全部实际命中的source重放已执行。初始发现阶段聚合text字段、初版mget根部_source参数各有一次诊断400，已修正工具请求形状；基础矩阵首次中止时另有4次服务请求，未计入280次完整矩阵，原始诊断现场归档，不能把它们当成业务引擎错误或抹掉。

证据目录 `docs/reviews/es817_category_filter_compare_20261008/`：预检/类别mapping与聚合、四个matrix及真实配对回复、Local单组重试、all_condition_evidence/all_statistics最终合并、resolved_condition_evidence与source快照、focused_summary、category_service_evidence、total_relation_evidence、manifest/哈希和工具diff。目录0700、数据文件0600，无凭据或向量数值。

尚未穷举任意condition_dict字段/组合、第三/四级类目、复杂时间范围、tags/keywords、图片筛选、跨集群联合条件、重排质量的固定大样本、并发/压力、完整CRUD或全库迁移一致性。本轮web主要用空text明确核验过滤与总数，不等同于全部文本web排序质量。过滤是否生效、是否完整召回、排序是否等价必须分别判断；上述未通过项均保留，不以HTTP200或旧新同错认定通过。
