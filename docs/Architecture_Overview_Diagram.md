# 总体业务主题与工程依赖

业务层按目标、业务域、能力、流程规则逐层展开，再映射到实现。层级含义与业务归属见[代码库本体](ontology.md#总体业务金字塔)。

## 总体业务主题框图

图从上到下依次为 L0 业务目标、L1 业务域及支撑主题、L2 业务能力、L3 流程与规则、L4 实现。实线表示业务分解及实现映射，虚线指向各实现的契约和验证依据。

```mermaid
flowchart TB
  GOAL["业务目标：把多来源内容转化为可维护、可检索、可复用的业务知识<br/>管理业务概念与规则定义"]
  GOAL --> PRODUCE["知识生产"]
  GOAL --> USE["知识管理与取用"]
  GOAL --> SUPPORT["语言与内容支撑"]

  PRODUCE --> MC["知识提取、任务组织与质量处理<br/>文档 / 网页 / 对话"]
  USE --> KC["知识入库、维护与查询<br/>更新 / 纠错 / 检索 / 结果整理"]
  USE --> OC["业务本体管理<br/>文档 / 审核与启停 / 作用域 / 模板"]
  SUPPORT --> SC["语言识别与对象访问"]

  MC --> MF["流程与规则<br/>任务调度、来源处理、提取与质检"]
  KC --> KF["流程与规则<br/>入库查重、更新维护、检索与展示"]
  OC --> OF["流程与规则<br/>校验、版本控制、审核与启停<br/>作用域选取、整篇克隆"]
  SC --> SF["流程与规则<br/>语言判定、对象读取与上传"]

  MF --> MI["实现：mining<br/>tasks / document / web / chat / common"]
  KF --> KI["实现：retrieval<br/>ingestion / modification / maintenance<br/>search / ranking / presentation"]
  OF --> OI["实现：retrieval/ontology<br/>validation / service / repository<br/>本体 HTTP 与克隆 CLI"]
  SF --> SI["实现：multilingual<br/>shared/storage 与 files HTTP"]

  MI -.-> EVIDENCE["实现依据：接口文档 · 函数与 SQL 契约 · 回归测试"]
  KI -.-> EVIDENCE
  OI -.-> EVIDENCE
  SI -.-> EVIDENCE

  classDef goal fill:#17324d,color:#fff,stroke:#17324d
  classDef domain fill:#e8f0fe,color:#17324d,stroke:#9bb7df
  classDef ontology fill:#fff2cc,color:#5f4500,stroke:#c69500
  classDef implementation fill:#f3f4f6,color:#273444,stroke:#bac3cf
  class GOAL goal
  class PRODUCE,USE,SUPPORT domain
  class OC,OF,OI ontology
  class MI,KI,SI,EVIDENCE implementation
```

黄色分支是本次补齐业务层级的本体管理能力。它已实现独立的管理与选取接口；默认新增为启用且待审，默认查询未删且审核通过，业务选取还要求启用；挖掘、入库、查询尚未接入本体规则执行。客户/行业/全局是本体适用作用域；数据库、模型客户端、配置等是共用技术支撑，具体依赖见下图。

## 工程实现与依赖

工程组织沿用知识检索、知识挖掘、多语言、公共模块。工程入口负责参数、HTTP 响应和生命周期，业务模块不得反向导入入口。下图箭头表示调用或依赖方向。

```mermaid
flowchart TB
  ENTRY[工程接入层：HTTP / CLI / 定时入口]
  ENTRY --> RET[知识检索 retrieval]
  RET --> ONTOLOGY[业务本体 ontology：文档校验 / 服务 / 仓储]
  ONTOLOGY --> MYSQL[shared/database/mysql：共享连接池]
  ENTRY --> TASK[知识挖掘：任务管理]
  ENTRY --> LANG[多语言 multilingual]
  ENTRY --> FILES[files HTTP：对象访问入口]
  FILES --> STORAGE[shared/storage：对象读取与上传]
  TASK --> DOC[文档挖掘 document]
  TASK --> WEB[网页挖掘 web]
  TASK --> CHAT[对话挖掘 chat]
  DOC --> COMMON[挖掘公共模块 common]
  WEB --> COMMON
  CHAT --> COMMON
  CHAT --> BRIDGE[检索衔接 mining/bridges/retrieval]
  BRIDGE --> RET
  COMMON --> QUALITY[质量 / 去重 / schema / 解析切分 / LLM]
  RET --> SHARED[顶层公共模块 shared]
  QUALITY --> SHARED
  LANG --> SHARED
  STORAGE --> SHARED
  SHARED --> INFRA[数据库 / 对象存储 / 模型客户端 / 配置 / 文件 / 文本]
  AUX[独立项目 assistant-data-tools：满意度 / 身份映射 / 运营统计] --> SHARED
```

任务管理通过子进程启动管道 CLI，图中任务到管道的箭头包括运行时调用，不全是 Python import。`scripts/testing/architecture.py` 校验实际静态 import 方向和环；动态命令的入口另有离线断言。

当前检索桥只有对话域的未回复问题复盘调用：用问题改写检索现有知识，再判断知识覆盖情况。document/web 当前没有调用该桥，图中不画这些依赖。files HTTP 属于工程入口，shared/storage 属于公共能力。

| 目录 | 职责与边界 |
|---|---|
| `retrieval/application/` | 唯一 SearchDataInterface 门面、服务运行对象与业务查询 |
| `retrieval/ontology/` | 完整业务本体文档及投影、MySQL 事务判重/版本/软删、作用域选取；入口同检索服务，无 ES 依赖、无元素级 CRUD |
| `retrieval/search/`、`ranking.py`、`statistics.py` | 查询、多查询、分页、分数整理与计数聚合 |
| `retrieval/ingestion/`、`categories/`、`file_operations.py` | 数据准备、ID、入库去重、写入、类目与按文件操作 |
| `retrieval/presentation/` | 入库 content 的多模态组装与检索返回 URL 展示；死链维护保留另一份有空值差异的重建实现，修改时联动检查 |
| `retrieval/engines/` | 项目声明支持 ES8.17、索引路由、协议与初始化；工厂仍保留 ES7/OpenSearch provider 选择分支，保留代码不代表旧后端已验收 |
| `retrieval/maintenance/` | 审核、导出、迁移、修复与清理 |
| `mining/tasks/` | 唯一队列状态、资源计数、SQL 记录、子进程、提交、估算与任务报表 |
| `mining/document/`、`web/`、`chat/` | 各来源专属管道、阶段、数据读取与处理 |
| `mining/common/` | 共用 llm、quality、deduplication、schema、parsing、segmentation、generation 等 |
| `mining/bridges/retrieval.py` | 挖掘在 Python 内导入检索的唯一模块；公共质检不依赖该桥或聊天抽取器 |
| `multilingual/` | 模型加载、规则优先识别、标签转换与唯一模型状态 |
| `shared/` | 通用存储、SQL、客户端、相似度、类目树、配置和文本文件处理，不导入业务域 |
| `entrypoints/http/` | 四服务：retrieval、tasks、files、multilingual，保留原协议 |
| `entrypoints/cli/`、`entrypoints/scheduled/` | 参数解析、命令注册、日志接线，业务函数在所属域 |
| `operations/data_migration/` | SQL 迁移；ES 迁移属于 retrieval/maintenance |

## 公共能力的调用方向

聊天抽取和通用质检共用的 Prompt 加载、模型客户端及输出清理在 `mining/common/llm/`。两者均可调用这些公共函数，公共函数不导入抽取器或质检流程。聊天专用 Prompt 选择仍在 `chat/generation/`。

shared 只依赖自身和基础库；mining/common 不依赖 chat/document/web/tasks/bridges 的专项实现；retrieval 不依赖 mining 或入口。挖掘对检索的 Python 导入必须经过桥接模块；管道另通过子进程启动检索 CLI 入库，调用链见本体说明。核心不导入 assistant_data_tools；独立项目只可导入 kdb.shared。默认离线测试检查静态导入约束，动态入口另行验证。

## 状态与重复实现

检索方法按职责拆分后仍绑定到同一个 SearchDataInterface 实例。五条管道保留各自控制器和调度规则，阶段函数继续使用原实例。队列、锁、停止标志和资源计数只由 mining/tasks/state.py 持有，详见[状态所有权](state_ownership.md)。

完全相同的两份文档切分实现、两份深度爬取实现分别合并为一份。函数只有依赖和语义也一致时才合并：页面输出共用文件 I/O，但文档格式化保留图片地址，审阅格式化仅保留文本，两种 formatter 分开。

本地数据集 ID 为 `retrieval/ingestion/raw_records.py::gen_local_dataset_record_id`；知识入库 ID 为 `retrieval/ingestion/identifiers.py::gen_data_id`。两者算法和用途不同，不能合并。正式批量入库仍关闭本地读取器的可选 ID 生成。

## 独立辅助项目

assistant-data-tools 管理满意度、身份映射、独立运营报表和工作流评测，使用自己的配置与产物目录，固定配对 assistant-data-tools 0.1.0 / kdb 0.2.0。四个核心服务与辅助项目的 CSAT 是独立部署单元；CSAT 的 URL、签名和返回保持原样。项目拆分不自动迁移系统 cron、私有配置或线上进程。
