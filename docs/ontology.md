# 代码库本体说明

源码核对基线：`f7e7b2cf9bbfd82f6dae6d995b432c2c33b7133a`；核对日期：2026-11-15。此处记录源码核对范围，文档修订由 Git 历史记录，不代表真实环境验收。

这份本体描述 KDB Forge 的业务能力、实现模块、协作关系与维护边界。用途是从一个需求找到负责的代码，并判断修改会影响谁。对象保持在稳定的业务与模块层级；知识条目、客户、实际 index、普通字段和每个函数不逐个登记，知识数据增长不会扩大这份说明。

第一版使用这一份 Markdown 维护模型和代码链接。现有实现以源码为依据；接口、算法和参数细节继续由已有文档与函数契约维护。下文“入库去重与冲突检测”中的扩展建议单独标明，不代表已经实现。

## 怎样读这个模型

“知识入库”是业务能力，`retrieval/ingestion` 是实现模块，`POST /insert` 是提供该能力的工程入口。三者分别回答“做什么”“在哪里实现”“怎样被调用”，不能仅用目录名称代替业务含义。

本体只使用以下关系：

| 关系 | 含义与本项目示例 |
|---|---|
| 包含 | 业务归属：知识挖掘包含文档挖掘；不表示 Python import |
| 实现 | 能力到代码：知识入库由 `retrieval/ingestion` 实现 |
| 提供 | 入口到能力：检索 HTTP 服务提供查询、插入、更新与删除接口 |
| 调用 | 执行协作：入库检查调用查询；任务管理以子进程启动管道。需注明 Python 调用或子进程调用 |
| 约束 | 允许的职责与依赖方向：例如 `shared` 不导入业务域；不表示每个允许的依赖都已存在 |

下方能力表按业务域分组表达“包含”，代码列表达“实现”，边界说明表达“约束”；工程入口段表达“提供”，协作表表达“调用”。[架构图](Architecture_Overview_Diagram.md)展示整体依赖，[状态所有权](state_ownership.md)说明运行对象归谁持有。

## 业务能力与实现位置

主体分为知识检索、知识挖掘、多语言和公共模块。工程入口与运维工具另外组织。这里的“知识检索”沿用项目域名，也包含已有的知识写入、纠错和管理能力。

### 知识检索

| 能力 | 职责 | 主要实现与边界 |
|---|---|---|
| 查询与结果整理 | 查找已有知识、多查询、分页、分数整理与聚合 | [search](../src/kdb/retrieval/search/)、[ranking.py](../src/kdb/retrieval/ranking.py)、[statistics.py](../src/kdb/retrieval/statistics.py)；请求和返回适配见 [HTTP 路由](../src/kdb/entrypoints/http/retrieval/routes.py) |
| 入库与更新 | 准备数据、生成入库 ID、检查重复、插入、更新和按 ID 删除 | [ingestion](../src/kdb/retrieval/ingestion/)；[categories](../src/kdb/retrieval/categories/)负责类目处理；通过同一个 [SearchDataInterface](../src/kdb/retrieval/application/search_index_data_interface.py)调用 |
| 多模态内容组装与展示 | 入库时将文本和附件地址拼成 content；查询时将内部地址占位符展开为带文件名的 URL | [presentation/multimodal.py](../src/kdb/retrieval/presentation/multimodal.py)；组装影响入库内容及后续内容向量生成，展示影响检索返回；关联调用见下方协作表 |
| 知识纠错 | 结合检索和模型执行已有知识修改流程 | [modification](../src/kdb/retrieval/modification/)；具体入口是否写入以 [API](api.md)和函数契约为准，不能作为普通只读查重调用 |
| 知识维护 | 按文件操作、审核、导出、修复和清理 | [file_operations.py](../src/kdb/retrieval/file_operations.py)、[maintenance](../src/kdb/retrieval/maintenance/)；保留各操作现有筛选、快照及软删/硬删语义 |
| 检索引擎与索引路由 | 连接后端，执行查询及写入，解析索引路由 | [engines](../src/kdb/retrieval/engines/)；项目声明的支持范围为 ES 8.17.x；[工厂](../src/kdb/retrieval/engines/factory.py)仍保留 ES7/OpenSearch provider 选择分支，不代表旧后端已完成兼容性验收；具体路由见 [ES8 说明](es8_retrieval.md) |

`application` 持有门面、服务运行对象和业务适配。拆分职责文件不创建第二套引擎、类目缓存或检索服务状态。

### 知识挖掘

| 能力 | 职责 | 主要实现与边界 |
|---|---|---|
| 任务管理 | 提交、排队、资源计数、SQL 状态、进程控制、估算与任务报表 | [tasks](../src/kdb/mining/tasks/)；负责调度，具体处理阶段属于各来源管道 |
| 文档挖掘 | 文档 QA、QA/段落以及 Excel 上传处理 | [document](../src/kdb/mining/document/)；控制器在 `pipelines`，阶段与执行在 `workflows` |
| 网页挖掘 | 网页抓取、内容处理及 QA/段落生成 | [web](../src/kdb/mining/web/)；保留网页专属抓取及调度规则 |
| 对话挖掘 | 对话读取、清洗、身份处理、抽取、质量处理、问题复盘及报表 | [chat](../src/kdb/mining/chat/)；对话专属数据和 Prompt 选择归本域 |
| 挖掘公共能力 | 跨来源使用的质量、批内去重、schema 转换、解析切分、翻译、生成与运行辅助 | [common](../src/kdb/mining/common/)；[quality](../src/kdb/mining/common/quality/)、[deduplication](../src/kdb/mining/common/deduplication/)、[schema](../src/kdb/mining/common/schema/)各自负责其处理步骤；[llm](../src/kdb/mining/common/llm/)承接共用 Prompt 加载、模型调用与输出清理 |

五条管道的任务类型、阶段和开关统一见[挖掘与任务队列](pipelines.md)。`common` 服务于挖掘域；跨业务的基础能力才归顶层 `shared`。挖掘结果内部去重与对 ES 存量知识的入库查重分别归 `mining/common/deduplication` 和 `retrieval/ingestion`，不能因名称接近就直接合并。

挖掘公共能力还包含 [context](../src/kdb/mining/common/context/) 的业务上下文与回答查找、[multimodal](../src/kdb/mining/common/multimodal/) 的图片等多模态处理，以及 [ingestion/deleted_sources.py](../src/kdb/mining/common/ingestion/deleted_sources.py) 的已下架来源过滤工具。这里的 ingestion 不负责最终 ES 写入，multimodal 也不同于检索侧的 content 组装和 URL 展示。[exports](../src/kdb/mining/common/exports/)保留 Dify 数据集导出工具；本次静态搜索未发现核心入口或管道引用，不将其列为默认执行阶段，外部调用情况未核实。

### 多语言与公共模块

| 能力 | 职责 | 主要实现与边界 |
|---|---|---|
| 多语言识别 | 语言规则、模型加载、识别和标签转换 | [multilingual](../src/kdb/multilingual/)；运行模型由该域持有；挖掘翻译流程仍属于 `mining/common/translation` |
| 对象读取与上传 | 对象下载、上传、传输及对象访问服务的配置和缓存 | [shared/storage](../src/kdb/shared/storage/)；对外 HTTP 入口在 [entrypoints/http/files](../src/kdb/entrypoints/http/files/) |
| 外部连接与计算辅助 | 数据库访问、模型及其他服务客户端、向量与文本相似度辅助 | [shared/database](../src/kdb/shared/database/)、[clients](../src/kdb/shared/clients/)、[similarity](../src/kdb/shared/similarity/)；业务流程决定何时调用及如何处理结果 |
| 配置与基础处理 | 资源路径、通用类目树、文件和文本处理 | [shared/config](../src/kdb/shared/config/)、[categories](../src/kdb/shared/categories/)、[files](../src/kdb/shared/files/)、[text](../src/kdb/shared/text/)；不持有上层专项业务流程 |

### 工程入口与项目边界

[entrypoints](../src/kdb/entrypoints/)组织 HTTP、CLI 和定时接线，[scripts](../scripts/)提供启动、调度和检查工具，[operations](../src/kdb/operations/)放工程操作。四个核心 HTTP 服务为 retrieval、tasks（服务名 off_task）、files、multilingual；路由和安装启动前提分别见 [API](api.md)与[运行配置](runtime_configuration.md)。

满意度、身份映射和独立运营统计属于独立项目 assistant-data-tools。核心不导入该项目；配对版本与配置边界沿用运行配置说明。本体不登记部署机器、有效凭据、客户数据或历史执行报告。

## 当前协作关系

| 调用方 → 被调用方 | 方式与目的 | 代码依据 |
|---|---|---|
| 检索 HTTP → 检索业务门面 | Python 调用；把现有协议请求交给查询、入库等业务处理 | [routes.py](../src/kdb/entrypoints/http/retrieval/routes.py)、[application](../src/kdb/retrieval/application/) |
| 入库检查 → 查询与相似度辅助 | Python 调用；查找候选并按现有规则判断重复 | [deduplication.py](../src/kdb/retrieval/ingestion/deduplication.py)、[knowledge.py](../src/kdb/shared/similarity/knowledge.py) |
| 入库准备、查询 → 多模态组装与展示 | Python 调用；prepare 调用 `join_multimodal_contents`；单查询、多查询、分页调用 `render_multimodal_urls` | [prepare.py](../src/kdb/retrieval/ingestion/prepare.py)、[queries.py](../src/kdb/retrieval/search/queries.py)、[multi_query.py](../src/kdb/retrieval/search/multi_query.py)、[pagination.py](../src/kdb/retrieval/search/pagination.py) |
| 任务管理 → 来源管道 | 子进程运行管道 CLI；不是对管道实现的直接 import | [processes.py](../src/kdb/mining/tasks/processes.py)、[管道 CLI](../src/kdb/entrypoints/cli/mining/) |
| 来源管道 → 检索入库 | 子进程运行 `kdb.entrypoints.cli.retrieval insert_data_to_search_index`；批量入口读取文件并保留质量/审核等适配规则，再调用门面入库 | [文档 QA 阶段](../src/kdb/mining/document/workflows/qa/stages.py)、[文档 QA/段落阶段](../src/kdb/mining/document/workflows/qa_segment/stages.py)、[网页阶段](../src/kdb/mining/web/workflows/qa_segment/stages.py)、[对话阶段](../src/kdb/mining/chat/workflows/qa/stages.py)、[Excel 阶段](../src/kdb/mining/document/workflows/excel/stages.py)、[index_upload.py](../src/kdb/entrypoints/cli/index_upload.py) |
| 对话问题复盘 → 检索桥 → 检索 | Python 调用；查找已有知识用于覆盖情况分析；当前 document/web 没有导入该桥 | [unanswered_review.py](../src/kdb/mining/chat/query_analysis/unanswered_review.py)、[bridges/retrieval.py](../src/kdb/mining/bridges/retrieval.py) |
| 聊天抽取、通用质检 → 挖掘公共 LLM 能力 | Python 调用；共用 Prompt 加载、模型调用和输出清理，质检不反向调用聊天抽取器 | [chat/generation](../src/kdb/mining/chat/generation/)、[common/quality](../src/kdb/mining/common/quality/)、[common/llm](../src/kdb/mining/common/llm/) |

表中列出定位需求所需的主要协作；完整静态 import 图由现有架构检查计算。子进程命令与静态导入分别核对，不能将“Python 导入经过 bridge”扩大为“所有挖掘入库都经过 bridge”。

两个需联动检查的位置：

- **多模态维护**：[prune_dead_urls.py](../src/kdb/retrieval/maintenance/prune_dead_urls.py)保留了一份拼接实现，清理前通过 `rebuild_matches_current` 检查能否重建原 content。它与正式拼接函数在空值返回上有差异，修改拼接规则时同时审查，不能直接认作完全等价并合并；边界见[拼接契约](../function_schema/kdb.retrieval.presentation.multimodal.join_multimodal_contents.md)。
- **Excel 入库**：[Excel 控制器](../src/kdb/mining/document/pipelines/excel.py)的 `run_all_stages` 调度 `stage_3_insert_index`，该阶段显式传 `--is_update_data=1`、`--index_name_assign`，从 `index_input_file_path` 读取输入；结构化图片处理成功后该路径指向处理后的 JSON。修改入库参数或输入选择要覆盖此路径，细节见[阶段契约](../function_schema/kdb.mining.document.workflows.excel.stages.stage_3_insert_index.md)。

## 主要入口、调用方与回归起点

此表补充“提供／调用”关系及验证入口，帮助缩小影响范围；不代替完整代码调用分析，也不表示所有业务分支已被测试。

| 能力 | 主要入口或调用方 | 当前离线回归起点 |
|---|---|---|
| 查询、引擎与路由 | 检索 HTTP `/search`、`/web_search`；入库检查；对话复盘 bridge | [HTTP 契约](../tests/retrieval/test_business_http_contract.py)、[ES8 引擎](../tests/retrieval/test_es8_interface.py) |
| 入库与更新 | HTTP `/insert`；五条管道的批量入库 CLI，包括 Excel | [参数传递](../tests/retrieval/test_insert_check_duplicate_arg.py)、[HTTP 入库](../tests/retrieval/test_insert_ext_info.py)、[Excel 阶段](../tests/mining/test_excel_qa_segment_upload_control.py) |
| 多模态组装与展示 | 入库 prepare；单查询、多查询、分页；死链清理的重建逻辑 | [内容拼接](../tests/retrieval/test_multimodal_content_assembly.py)、[URL 展示](../tests/mining/test_multimodal_url_filename.py)、[死链清理](../tests/retrieval/maintenance/test_prune_dead_raw_urls.py) |
| 知识纠错 | `/modify_knowledge`、`/modify_knowledge_direct_update` | [HTTP 协议](../tests/retrieval/test_business_http_contract.py)、[服务初始化](../tests/entry_smoke/test_service_contracts.py)；这些不验证真实模型纠错质量 |
| 知识维护 | 按文件预览/删除 HTTP；维护 CLI 与自动审核定时入口 | [按文件删除](../tests/retrieval/test_delete_by_file.py)、[维护测试](../tests/retrieval/maintenance/) |
| 任务与来源管道 | off_task HTTP、管道 CLI、定时入口 | [依赖和状态](../tests/offline/test_business_boundaries.py)、[任务测试](../tests/mining/tasks/)、[管道测试](../tests/mining/)；涉及哪个来源就选择其测试，非完整真实任务验收 |
| 挖掘公共能力 | 来源管道各阶段、专项生成与质量处理、独立处理工具 | [上下文](../tests/mining/test_generic_mining_context.py)、[质量批处理](../tests/mining/test_qa_quality_batching.py)、[已下架来源](../tests/mining/common/ingestion/test_skip_deleted_sources.py)、[多模态处理](../tests/mining/test_multimodal_image_hash_blacklist.py) |
| 多语言识别 | multilingual HTTP `/lang_predict` | [规则与模型分支](../tests/services/test_extracted_business_adapters.py)；真实模型资源另验 |
| 对象访问与公共配置 | files HTTP、各业务客户端和启动器 | [对象访问](../tests/services/test_file_access_service_timeout.py)、[配置路径](../tests/shared/test_project_config_loading.py)、[启动预检](../tests/entry_smoke/test_launcher_startup.py) |

## 维护边界

1. **依赖方向**：`shared` 不导入业务域；`mining/common` 不导入来源专项、任务管理或 bridge；`retrieval` 不导入 mining 或工程入口。挖掘对检索的 Python 导入经过 `mining/bridges/retrieval.py`。业务模块不反向导入工程入口，现有子进程 CLI 调用单独保留。
2. **状态归属**：检索职责方法使用同一个门面实例；任务队列、锁、资源计数和停止标志归 `mining/tasks/state.py`。其他模型与服务状态位置见[状态所有权](state_ownership.md)，不能为新模块复制一份。
3. **协议与行为**：保持原有接口、参数、返回、默认值、认证和失败处理。新增行为需在对应功能设计和契约中明确，不从本体描述推导尚未实现的规则。
4. **实现依据**：修改函数前查[函数契约索引](../function_schema/current_index.md)；算法、字段、SQL 和阈值在对应契约中维护。本体只链接这些依据，不复制全部函数说明。
5. **验证范围**：使用现有[离线测试入口](testing.md)。离线断言、生产请求回放和真实模型/后端验收分别说明；本体描述不代表这些验证已经完成。

依赖与状态边界已有 [architecture.py](../scripts/testing/architecture.py) 和 [test_business_boundaries.py](../tests/offline/test_business_boundaries.py) 检查。静态检查覆盖 import，动态调用还需结合入口测试和管道测试判断。

## 用需求定位代码：入库去重与冲突检测

这是使用本体定位修改范围的例子；本版只增加维护说明。

| 定位项 | 当前实现或扩展位置 |
|---|---|
| 业务归属 | 知识检索 → 入库与更新；不因新增知识条目而新增本体条目 |
| 已有检查 | [find_duplicates](../src/kdb/retrieval/ingestion/deduplication.py)查询候选，再进行相似性判断，返回重复列表 |
| 已有写入 | [insert_data](../src/kdb/retrieval/ingestion/writes.py)按开关跳过重复，或软删除旧记录后插入；不是已实现的独立冲突分类流程 |
| 可复用能力 | 查询与索引路由、现有相似度/模型客户端；复用当前门面状态 |
| 受影响的调用方 | HTTP 插入与管道批量入库；包括 Excel 阶段显式传入的更新参数及图片处理后的输入选择，不能只验证一个入口 |
| 后续扩展建议 | 将新的检查和写入决策放在入库职责中；结果结构、判定算法及覆盖策略属于该功能设计，尚未实现，也不在全局本体解释通用词义 |
| 回归起点 | [批量入库参数测试](../tests/retrieval/test_insert_check_duplicate_arg.py)、[HTTP 契约测试](../tests/retrieval/test_business_http_contract.py)、[网页入库模型开关测试](../tests/mining/test_html_insert_llm_override.py)；新增能力需要补充相应行为测试，现有测试不证明冲突检测已存在 |

## 怎样保持这份说明精简

新增或调整稳定业务能力、职责归属、模块位置、入口关系及依赖边界时，更新本文件的相应行，并检查关联架构图。普通知识数据变动、函数内部实现和阈值调整只更新相应代码与契约；若改变模块协作或对外职责，再同步本体。

新增能力沿用“业务归属、职责、实现位置、调用关系、维护边界”记录即可。图中箭头只画有依据的关系；未落地的设计明确标为建议。阅读顺序是本体定位职责 → 源码与函数契约确认行为 → 选择受影响入口与测试；遇到不一致先核对源码，不用文档补造业务事实。

默认离线套件中的[文档链接检查](../tests/offline/test_document_links.py)验证 README、AGENTS、MEMORY 和 docs 下 Markdown 行内相对链接的本地目标是否存在；不检查外网和标题锚点。提交本体和导航修改时一并暂存新增文档，并核对暂存差异，避免本地存在但干净检出遗漏。
