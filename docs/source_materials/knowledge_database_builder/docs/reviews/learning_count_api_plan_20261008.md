**按来源类型统计接口方案：旧项目与sg-kg检索重构共用契约（2026-10-08）**

用户已确认本方案并授权旧、新项目实施；旧版在隔离目录完成，新版由指定既有会话实施。按用户最新修改，新增 `POST /get_from_type_count`，增加字符串参数 `from_type`，省略时默认 `chat_auto`。旧项目与重构项目请求/返回格式相同。Java原有 `getLearningCount(indexName,start,end)` 可省略from_type继续使用默认口径，内部改为请求检索服务；其他来源类型由调用方明确传入from_type，无需Java持有两套ES连接、处理PaaS/Serverless路由。

```json
{
  "index_name": "mercado_local",
  "from_type": "chat_auto",
  "start": "2026-09-01 00:00:00",
  "end": "2026-09-30 23:59:59"
}
```

```json
{"success": true, "count": 123, "message": ""}
```

`index_name` 使用原物理名；可兼容Java常用 `indexName` 入参别名，若两者同时存在且冲突应拒绝，而非选错索引。`start/end` 可省略或null。时间按原Java本地日期格式 `yyyy-MM-dd HH:mm:ss` 处理，不隐式转UTC。返回count为整数。正常空索引名或合法查询0命中，返回成功/count0；ES错误、索引不存在或分片结果不完整，兼容Java异常归0的行为，返回失败/count0并记录日志，区分失败与实际0。计数路径不得创建缺失索引或修改mapping。

**原统计条件逐项保留：**

| 条件/行为 | 接口口径 |
|---|---|
| quality_level | 精确等于high |
| from_type | 精确等于请求参数；省略时为chat_auto，不替换成from_type_norm或做来源名称转换 |
| 时间 | 仅start、end都非空时添加insert_time的gte/lte，含两端；只提供一个时按Java原行为不加时间范围 |
| 审核/删除/知识类型/类目 | 不自动加audit_result、del_flag、data_type或类目条件 |
| 索引范围 | 只按传入原名统计，不自动拼客户私库、公库或版本后缀 |
| 请求失败 | count0，同时success=false、可观测日志；不将部分分片计数标成功 |

建议通过 `_count` 精确统计，不走文本/embedding召回或读取文档source。**与原Java的一项明确差异**：Java `_search` 没有设置track_total_hits，超过10000时可能读到下界值10000；方案建议新接口返回真实总数，两项目一致，不复制该截断。默认from_type下业务筛选条件完全相同，但大于10000时数值口径改进必须在方案确认时明确，不静默称为逐字等价。[ES8.17 search计数说明](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/search-search.html)、[count API](https://www.elastic.co/guide/en/elasticsearch/reference/8.17/search-count.html)。当前两重点索引已验证的默认chat_auto条件计数均未超过10000，其他来源类型尚未实测。

旧项目实现边界：HTTP模型/handler → `SearchDataInterface` 独立统计方法 → engine统计方法。现有ES7与ES8均有 `count_by_query(index_name,query)`，接收原生DSL；应核对旧ES/OpenSearch保留路径及完整分片校验，不能复用会补del_flag/audit或触发ensure建库的检索入口。当前ES8该方法通过 `get_client_by_index` 选provider；一期给单个原索引名，无须改Java选择cluster逻辑。旧项目的既有search/web/CRUD参数与实现不因新增此接口而变化。

重构项目由既有“sg-kg检索重构”会话负责，遵守其API → Service → engine/Router边界，添加相同统计契约和native count路径，不借用旧服务充当新服务。现已授权隔离实现、测试、schema及报告；未授权据此部署、重启、修改运行配置、写ES或commit/push。本会话不修改新项目源码或停止其迁移。

验证要求：两版相同请求模型与DSL；from_type省略的chat_auto默认、显式chat_auto、其他已有来源类型及无命中类型；空名、无时间、完整时间、单边时间、含边界时间、start>end、0/正值/超过10000、missing index、HTTP/分片错误均有离线行为测试。使用真实业务方法与真实engine实现，仅mock外部客户端；新增接口不得触发ensure/create。真实验证只选已确认存在的原索引，native count与新HTTP接口比对，PaaS/Serverless均覆盖；不会为测试创建业务或staging索引。需要重启使端点可用时另遵循用户当时授权，不能把本方案当作当前重启许可。

**已完成的方案可行性只读验证**（不是新HTTP接口已验收）：

| 原物理索引 | 无时间：旧/新 | 2026-09-01至2026-10-08：旧/新 |
|---|---:|---:|
| mercado_local（Serverless） | 388 / 387 | 51 / 50 |
| payoneer_olive（PaaS） | 4939 / 4939 | 2378 / 2378 |

Local差额已在最近10条源样本中找到：`24522b3f0f2566e6606121d75920ad3e`，旧端insert_time=2026-10-07 12:03:49、quality_level=high、from_type=chat_auto、audit_result=-1、del_flag=0；新端不存在。不能通过增添审核/删除条件或修改统计代码把差额掩掉。本轮未同步/删除该知识；接口正确性应对照各端同条件真实计数，数据一致性另行追平。

证据：`docs/reviews/es817_category_filter_compare_20261008/learning_count_readonly_evidence.json`、`learning_count_difference.json`。旧接口已在/root/knowledge_database_builder-from-type-count实施，新增88+既有130=218通过，12真实只读ASGI/native一致；未加载运行8003。实施报告from_type_count_api_implementation_20261008.md及隔离目录的diff/manifest为交付。新项目已由指定thread01a0f061完成，目录/root/kdb-forge-learning-count-20261008，新增134+既有188=322通过，12真实只读ASGI/native一致；交付报告位于该目录artifacts/learning_count_api_20261008/delivery_report.json。两版汇总见from_type_count_old_new_acceptance_20261008.md。方案未自动授权部署和真实写测试。
