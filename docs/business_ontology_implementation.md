# 业务本体实现说明

本页按已落地源码说明业务本体的处理过程、数据约束和模块位置。实现基于重构后的代码，当前接口、函数命名及行为以 `main` 分支为准。请求和响应字段详见 [API 文档](api.md#业务本体)。

## 代码组成与调用关系

HTTP 请求由现有检索应用接收，依次经过请求模型、路由、业务服务和存储层。创建及整篇更新在进入写事务前执行文档校验。存储层复用共享 `MySQLConnector`；元信息接口直接返回常量，不连接数据库。

| 位置 | 已实现职责 |
|---|---|
| [ontology_routes.py](../src/kdb/entrypoints/http/retrieval/ontology_routes.py) / [ontology_models.py](../src/kdb/entrypoints/http/retrieval/ontology_models.py) | 注册 8 个操作，检查请求参数，定义响应模型及错误处理 |
| [service.py](../src/kdb/retrieval/ontology/service.py) | 创建、替换、状态切换、删除、详情、列表、作用域选择；组装返回视图 |
| [validation.py](../src/kdb/retrieval/ontology/validation.py) / [models.py](../src/kdb/retrieval/ontology/models.py) | 文档结构、大小、名称、字段组合及跨节点引用校验，生成存储投影 |
| [repository.py](../src/kdb/retrieval/ontology/repository.py) | 参数化 SQL、连接管理、事务判重、版本条件更新、搜索与选取 |
| [schema.py](../src/kdb/retrieval/ontology/schema.py) / [ontology.schema.json](../src/kdb/retrieval/ontology/ontology.schema.json) | 共享枚举和限制；从 Pydantic 模型生成、核对 JSON Schema |
| [ontology_clone.py](../src/kdb/entrypoints/cli/tools/ontology_clone.py) | 直接调用 service，复制源文档到目标客户作用域 |
| [建表](../migrations/20261117_ontology.sql) / [审核字段迁移](../migrations/20261118_ontology_review_status.sql) | 创建或升级唯一业务表 `dops_ontology` |
| [resources/ontology](../resources/ontology/) | 全局、行业、客户三份完整示例文档及 HTTP 验收脚本 |

现有 [routes.py](../src/kdb/entrypoints/http/retrieval/routes.py) 只增加本体路由的导入与注册，保留原有 12 个操作。对应函数的 Inputs、Outputs、SQL 契约位于 [function_schema](../function_schema/)，文件名前缀为 `kdb.retrieval.ontology`、`kdb.entrypoints.http.retrieval.ontology` 和 `kdb.entrypoints.cli.tools.ontology_clone`。

service 与 repository 的公开操作使用以下名称；失败后按ID回查直接复用 select_ontology_by_id，不保留 probe 包装。

| 操作 | Service | Repository |
|---|---|---|
| 创建 | `insert_ontology` | `insert_ontology` |
| 详情 | `get_ontology` | `select_ontology_by_id` |
| 列表 | `list_ontologies` | `list_ontologies` |
| 整篇更新 | `update_ontology` | `update_ontology_document` |
| 状态切换 | `update_ontology_status` | `update_ontology_status` |
| 软删除 | `delete_ontology` | `delete_ontology` |
| 作用域选取 | `select_ontology` | `select_ontology` |

## 存储及事务

只有 **1 张业务表 `dops_ontology`**。一行保存一套完整本体，`data_json` 是 MySQL JSON 列；类、属性、关系、枚举、规则和术语均保存在文档内。

| 字段或索引 | 实际用途 |
|---|---|
| `id` / `ontology_id` | 自增物理主键 / UUID4 hex 对外标识；分别有主键和唯一索引 |
| `client/product/name/alias_name/description` | 从校验后的文档生成的五个投影列，用于筛选、判重和列表展示 |
| `status` | `active` 启用或 `inactive` 停用；创建默认 active，与审核状态独立 |
| `review_status` | `pending` 待审、`approved` 通过、`rejected` 驳回；创建默认 pending |
| `revision` | 创建为 1；成功替换、切换状态或首次软删时加 1 |
| `del_flag` | 0 正常、1 已删除；软删保留整篇文档 |
| `create_time/update_time` | 毫秒精度时间；对外格式为 `YYYY-MM-DD HH:mm:ss.SSS` |
| 三个普通索引 | `(client,product,name,del_flag)`、`(client,product,status,review_status,del_flag)`、`(update_time,id)` |

业务键是 `(client, product, name)`。数据库没有该业务键的唯一约束或生成列；插入及整篇替换都在同一写事务内，以 `SELECT ... FOR UPDATE` 检查未删除行，待审、驳回和停用记录同样占用业务键。默认迁移使用 `utf8mb4_0900_ai_ci`，业务名称判重按数据库排序规则执行；文档内部名称的比较另用 NFKC + casefold。

每次写入显式开启 REPEATABLE READ 事务，成功 commit，异常 rollback，最后分别关闭游标和连接。MySQL 1213 死锁整笔重试一次；仍失败或锁等待超时返回 503。插入遇到 1062 时重新生成一次 UUID。共享连接器按进程懒加载，沿用大小为 5 的连接池，每次操作设置 `utf8mb4`。连接配置来自 `KDB_MYSQL_CONFIG`，缺省使用项目配置路径。

这些判重约束依赖接口的事务逻辑，直接绕过接口写表不会获得同样的业务保护。写入成功后，service 会另行读取该行组装响应；写入和回查不是一个包含响应快照的事务。

升级旧表先运行20261118迁移再启动新代码：新增review_status默认pending，原active保持启用，原draft转inactive并revision+1，既有内容不自动审核通过。迁移可重跑，不重置已存在的审核结果；文档、ID及软删标记保留。新建表直接具有两个状态字段和更新后的作用域索引。

## 文档校验顺序

`validate_document` 接收对象或 JSON 对象字符串，按以下顺序处理：

1. 解析对象，检查能否序列化为合法 JSON，按紧凑 UTF-8 字节数检查 1 MiB 上限。
2. 检查 `schema_version`，当前只接受 `1.0`。
3. 递归检查行控制保留字段，并去掉所有字符串值的首尾空白。`extensions` 子树跳过保留字段扫描。
4. 以严格 Pydantic 模型检查结构、类型、枚举、必填项、数量和长度，拒绝未知字段。`client/product` 必须是小写编码，不自动转小写。
5. 检查自由字典大小：根 `llm_hints`、`extensions` 各不超过 64 KiB，节点 `llm_hints` 不超过 16 KiB。
6. 按 NFKC + casefold 比较同集合名称、类内属性名、枚举内值和各节点别名的重复，存储保留去空白后的拼写。节点名称禁止点号和 ASCII 控制字符。
7. 检查属性类型组合：array 需要 item_type，enum 需要 value_set，object 需要 ref；不适用的字段不能附带。
8. 检查 identity、属性 ref/value_set、关系 subject/object、规则 applies_to、术语 refers_to 的目标是否存在。引用比较使用同样的名称折叠方式，不重写引用字符串。
9. 补默认值、排除 None 后，再检查实际存储文档是否超过 1 MiB，并生成五个投影列。

返回的校验问题最多 50 条，包含 `path/reason/message`。文档超过 200 KiB 会记录告警。JSON Schema 表达结构约束；跨节点唯一性、引用及字段组合仍由服务端逻辑检查。

## 8 个接口的实际行为

| 操作 | 处理过程 |
|---|---|
| `POST /insert_ontology` | 校验文档 → 事务判重 → 插入 → 回查元数据；返回 201，不带完整文档 |
| `POST /get_ontology` | 默认只返回未软删且approved的记录；支持full/document/outline，可显式筛选pending/rejected/all，软删筛选独立 |
| `POST /list_ontologies` | 按作用域、启停状态、审核状态、关键词和删除标记筛选，默认未删且approved，分页返回元数据；查询投影不加载整篇文档 |
| `POST /update_ontology` | 读取现有行 → 校验整篇文档 → 禁止修改 client/product → 事务内判重并按 revision 更新 → 回查元数据 |
| `POST /update_ontology_status` | 按 revision 独立更新 status/review_status（至少一个）和时间、版本；不重写文档，相同状态也使版本加 1 |
| `POST /delete_ontology` | 软删除；revision 可选；已删除行重复调用成功，版本不再增加；不存在返回 404 |
| `POST /select_ontology` | 从 active、approved、未删除行中选出一个符合优先级的本体；不合并文档 |
| `GET /ontology_meta` | 返回结构版本、枚举和限制，不创建数据库连接 |

update_ontology、update_ontology_status 的 SQL 条件包含 `ontology_id/revision/del_flag=0`。更新行数为 0 后回查：不存在或已删除返回 404，仍存在则返回 409 和当前 revision。update_ontology 可以修改名称，未指定 status 时沿用当前状态；未指定 review_status 时重置为 pending，也可显式指定审核结果。单独切换启停不改变审核结果。delete_ontology 在已经删除时保持幂等，即使调用方携带旧 revision，也返回已删除结果。

full 包含行元数据、删除标记、完整文档和文档字节数；document 顶层返回 `ontology_id/status/review_status/revision/document`；outline 返回类、属性名称及各集合计数。列表只返回元数据，不返回 `data_json`。所有写响应和读视图都包含两个状态；详情不满足审核/软删筛选返回404。

成功响应采用 `success/message` 加业务字段。错误响应采用 `success=false/code/message/details`：参数错误 400、未找到 404、业务键或版本或作用域冲突 409、文档过大 413、文档校验失败 422、数据库不可用 503、其他存储错误 500。错误处理器按匹配路由的 ontology tag 区分作用范围，其他路径沿用已有处理器。

ID 统一从 body.ontology_id 取得，删除的 revision 也移到 body；get_ontology 的 view/include_deleted/review_status 和 list_ontologies 的筛选、分页继续使用 query。默认分页复用 DEFAULT_PAGE_SIZE=100，service 统一检查范围并返回带字段路径的400，路由只解析类型。创建及其他写入返回 OntologyMeta；详情为 Full/Outline 联合类型，列表为 OntologyListItem，选取为 SelectedOntologyDocument/Outline 联合类型。

## 搜索和作用域选取

列表中，未传 client/product 表示不按该字段过滤，传空串表示只取公用作用域。默认只返回未软删且审核通过的记录，review_status=pending/rejected/all可显式调整；include_deleted与审核筛选相互独立，默认不过滤启停状态。默认每页 100，最多 100。q 匹配名称、说明及别名；deep=1 以 OR 方式额外匹配完整 JSON。`!/%/_` 在 LIKE 查询中转义为字面量。

关键词排序分值为：名称精确 100、别名精确 90、名称前缀 70、名称包含 50、其他命中 20，再按更新时间和 id 倒序。别名精确匹配使用 JSON_CONTAINS，区分拉丁大小写；别名包含匹配不区分大小写。deep 查询会扫描文档，不使用全文索引。

select_ontology 的优先级为客户行业 → 客户通用 → 行业 → 全局。仅参与请求作用域的 active、approved、未删除行进入候选；可按 name 进一步精确筛选，同层按更新时间及 id 倒序选一行。

只传 client 时，优先该客户 product 为空的通用行；如果只有该客户的行业行，允许选最近更新的一条。`fallback` 严格按选中行的 `(client,product)` 是否等于请求作用域计算。未匹配返回成功响应、`ontology=null`、`scope=none`。`include_document=false` 返回大纲，默认返回选中文档；各层本体不会继承、拼接或补齐。

## 模板克隆与实际取舍

克隆 CLI 先调用同一 select_ontology 逻辑选源，因此可能选中回落层；随后校验源文档、深拷贝、改写目标 client/product、再次校验，再调用 insert_ontology。默认创建 active + pending，克隆件不继承源的审核结果；dry-run 只解析、校验和输出摘要，不写入。目标 product 未指定时使用请求的 source-product。模板后续修改不自动传播到已克隆客户。

对原设计中矛盾或遗漏处，实际采用以下口径：deep 搜索使用额外 OR；client-only 允许客户行业回落；fallback 采用作用域比较公式；写事务显式使用 REPEATABLE READ 并重试一次死锁；归一化补默认值后重新检查文档上限；insert 返回生成 ID 供回查，document 采用独立响应模型，删除结果保留 del_flag。详细说明见 [API 文档中的实现口径](api.md#v8-设计中相互矛盾处的实现口径)。

审核状态由现有写接口维护，沿用原认证行为；不新增审核人、审核意见、审批流程或审核历史表。

本期没有元素级 CRUD、继承合并、历史版本表、ES 同步、embedding、前端页面或新增认证体系。软删记录保留删除时文档，但 revision 并不表示保存了每次历史快照。生产库迁移和生产上线属于部署动作，不由导入模块自动触发。

## 已配套的验证代码

| 位置 | 覆盖内容 |
|---|---|
| [tests/retrieval/ontology](../tests/retrieval/ontology/) | 文档校验、Schema 一致性、业务服务、HTTP 协议、SQL 参数与异常、资源清理及克隆 |
| [test_mysql_repository.py](../tests/integrations/ontology/test_mysql_repository.py) | 真实 MySQL 建表、业务键冲突、并发创建、版本更新、软删重建、Unicode、搜索、投影和作用域选择 |
| [acceptance.sh](../resources/ontology/acceptance.sh) | 17 步 HTTP 流程：创建默认状态、独立审核/启停、查询可见性、修改后待审、回落、旧版本拒绝、软删重建及不同 product 同名 |
| [test_business_http_contract.py](../tests/retrieval/test_business_http_contract.py) / [test_service_contracts.py](../tests/entry_smoke/test_service_contracts.py) | 原 12 个检索操作的协议回归；保留原 OpenAPI 快照，允许新增本体路径 |

离线与真实数据库测试分别运行，默认离线守卫保持启用。真实 MySQL 测试要求显式开关及专用测试库。执行入口和范围见 [测试说明](testing.md)；机器执行结果、服务状态及部署配置保存在仓库外，不包含于源码提交。
