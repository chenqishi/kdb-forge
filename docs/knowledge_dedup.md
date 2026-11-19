# 知识去重与冲突检查

实现分为快速检查、离线增量检查、文档检查和 Agent 工具四层。所有知识比较限定一个明确 index，QA 与 QA 比、Segment 与 Segment 比；不限制 platform，也不以消息 ID 作为内容判重标准。

## 四层入口

| 层级 | 已实现入口 | 行为 |
|---|---|---|
| 快速 | 原 `find_duplicates` / 单条与批量入库调用链 | 保留少量候选及原向量阈值；补充归一化文本相等；可选判断直接请求 LLM，不再请求 Dify |
| 离线 | `python -m kdb.entrypoints.cli.knowledge_dedup knowledge` | 指定增量范围 → 在线混合召回 Top60 → gte 重排 → 分数/主题词过滤 → LLM及证据校验 → 记录/处理 |
| 文档 | 同一 CLI 的 `document`；文档 QA、QA+Segment 管道的可选参数 | 主体名称 LLM 判断，或450字抽样的同文档 Segment 覆盖率>=70%；任一命中即可 |
| Agent harness | 原检索服务 `/knowledge_dedup/mcp`，默认不挂载 | 六个工具及 [skill](../resources/skills/knowledge-dedup/SKILL.md)，供既有 sell_agents skill_agent 组织多轮检索、处理与交互；没有新增 Agent |

原有单条/ChatQA/批量调用的 `is_update_data` 默认值不在本次修改范围内。快速层只有配置为需要 LLM 的调用才请求模型；原 Dify 配置的 key 不再用作 LLM key，需配置下述直接模型或既有显式 LLM 插件。

## 模型及结果

模型配置模板：[knowledge_dedup.json.example](../config/knowledge_dedup.json.example)。填好独立有效配置后，用 `--config` 或 `KDB_DEDUP_CONFIG` 指定。密钥可由 `api_key_env` 引用环境变量。`llm` 不配置 endpoint 时使用项目已有 `KDB_LLM_CLIENT_PATH` / `KDB_LLM_CONFIG` 插件；缺配置时明确失败，不返回“无重复”。快速层的原 similarity 配置新增 `llm: {endpoint, api_key, model}`，或使用同一显式插件。

重排默认 `gte-rerank-v2`（北京接口），以真实相关性分数筛选，不解释为重复概率。初始阈值0.1、至少1个共享主题词；可配置阈值、0/1/2个共享词及同义词映射。此值是保守起点，需按业务样本继续校准。主题词门槛仍可能漏掉完全换词的表达，Agent可放宽到0并做下一轮判断。长文本分块、请求按UTF-8字节上界分批，最终取对应候选的最高片段相关性；不丢弃超长部分。供应商限制及字段见[官方重排接口](https://www.alibabacloud.com/help/en/model-studio/text-rerank-api)。

关系分类如下：

| relation | 含义和处理 |
|---|---|
| duplicate | 完整语义等价，可按保留策略处理 |
| overlap | 包含关系或部分重叠，保留独立信息，第一版只记录 |
| conflict | 同一适用条件/时段下不能同时成立，允许修订旧知识 |
| different | 未发现重复或冲突，也可能同主题；不写入 `similarity_info` |
| uncertain | 证据或条件不充分，只记录，不能自动改写/删除 |

`evidence.current` 与 `evidence.related` 是模型从两侧标题/正文抽取的连续原文。代码逐字验证，不通过就降为 uncertain。政策、物流限制、资格及入驻流程等冲突，还要求两侧存在相同的明确生效时间/版本原文；入库时间或“目前”不能证明这一点。缺失条件的 ChatQA 要核实来源上下文，不能把相反说法直接当作可自动覆盖的冲突。

每条记录的 `similarity_info` 是JSON列表，含 `related_id`、`related_data_type`、`relation`、`relevance_score`、`reason`、`evidence`、`shared_topics`。新轮次更新已判断候选、保留本轮未涉及的关系。`dedup_check` 保存状态、内容指纹、时间、策略及阈值；指纹仅用于内容变化后的重检和并发保护，不参与内容去重。

`complete`表示本次限定候选范围检查成功，不代表整个索引绝无重复。`partial`是Agent显式候选检查，`pending`是正文修订后需要重检，`failed`会在下次增量中重新选取。待审使用现有 `audit_result=-1`；候选不限制审核状态。

新索引的这两个字段是仅保留 `_source` 的object。存量严格 mapping 索引需预先添加相同字段；[mapping片段](../resources/knowledge_dedup/es_mapping.json)供部署使用，不对既有同名字段强制改类型。

## 离线执行

```bash
# 先估算范围和token，不调用判定模型或写知识
python -m kdb.entrypoints.cli.knowledge_dedup knowledge \
  --index marsmind --data-type qa --since '2026-10-19 00:00:00' --unaudited \
  --config config/knowledge_dedup.json --estimate-only --output private/dedup/cost.json

# 默认只处理尚未完成检查或内容已改变的增量，只写结果
python -m kdb.entrypoints.cli.knowledge_dedup knowledge \
  --index marsmind --data-type qa --since '2026-10-19 00:00:00' --unaudited \
  --config config/knowledge_dedup.json --policy record_only --output private/dedup/check.jsonl

# 未入库知识：同类型JSONL，结果写回离线文件
python -m kdb.entrypoints.cli.knowledge_dedup knowledge \
  --index marsmind --data-type qa --input private/new-qa.jsonl \
  --config config/knowledge_dedup.json --policy keep_old --output private/dedup/new-check.jsonl
```

Segment换 `--data-type segment` 单独执行。可用 `--until`、`--task-id`、`--max-records`（默认500）控制范围；`--include-checked`用于策略/模型变化后主动重跑。`--dry-run`只产出报告。达到记录上限时 `selection_truncated=true`，达到候选上限会返回 `candidate_limit_reached`，都不能视作全量查完。

输出包含逐条报告、`.summary.json`，未入库输入另有全部带标记的 `.knowledge.jsonl` 及仅保留可入库项的 `.ready.jsonl`。失败退出码为2；正文已修订但仍需重检时状态partial、退出码3。无重复的记录也保存完成状态；失败不会保存成完成。

| policy | 动作 |
|---|---|
| record_only | 已入库只写关系和检查状态；未入库只写离线产物 |
| keep_new | 完整重复中保留入库时间较新的记录，其余软删 |
| keep_old | 完整重复中保留较旧记录；未入库新重复项标记skip |

时间相同用ID确定稳定保留顺序；存量没有入库时间时拒绝自动选择新旧。两种处理策略遇到确认冲突，均以较新知识修订较旧内容、重建文本向量并置为待审。若本次被选中的记录本身被修订，暂不沿旧结论删除重复项，标记pending等待下次重检。overlap和uncertain不自动处理。含多模态正文的冲突不自动改写，返回明确失败并保留原文，交给既有审核/多模态修改流程。

未入库文件默认不改变ES中的旧知识；实际插入并处理时显式加 `--insert-new`，先确认新知识写入成功再改旧记录。对已带完成标记的离线结果执行此步骤需加 `--include-checked`。不直接把带skip/failed项的完整 `.knowledge.jsonl` 作为入库文件。所有正文/软删修改先写本地journal，再使用ES版本条件更新；并发内容或审核状态变化会报错，不声称跨文档事务或自动回滚。

估算按文本长度、候选数和输出预算计算，有明确 `estimated=true`。实际LLM、rerank用量从供应商usage累计，失败调用若未返回usage会记 `unknown_usage_calls`；原embedding接口不返回token，会明确标为未知。不能把估算/未知用量当成已计费token。冲突改写产生的实际LLM用量计入汇总。

## 文档流程

在原文档任务的 `task_info` 中添加以下可选参数；省略时流程不变：

```json
{
  "document_dedup": {
    "enabled": true,
    "policy": "replace_old",
    "config_path": "config/knowledge_dedup.json",
    "seed": 0,
    "name_check": true,
    "content_check": true
  }
}
```

解析成功后检查，保留抽样偏移和seed方便复核。内容覆盖只把同一个 `ext_info.from_file_name` 的Segment匹配位置取并集，不能跨文件凑70%，不使用QA。匹配忽略空白和大小写，证据记录规范化片段及位置；连续匹配少于12字不计入，短文使用全文。

`record_only`写报告并继续；`skip_new`过滤重复文档后再生成；`replace_old`捕获旧文件全部QA/Segment快照，在新文档生成、入库完成并核对任务内新记录数量后，才精确软删旧ID。不会删除同文件名下本任务刚写入的ID。生成无内容、数量不足、并发修改或review_only时不能替换。没有新增状态表或独立任务类型。

也可独立执行 `... knowledge_dedup document --index ... --file-name ... --text-file ... --output ... --policy record_only`；解析后的页JSON增加 `--parsed-json`。CLI/工具直接指定 `replace_old` 会执行旧文档软删，不包含新文档生成；需要完整替换时使用文档管道。

## sell_agents 接入与权限

[harness配置](../config/knowledge_dedup_harness.json.example)默认 `enabled=false`。`KDB_DEDUP_HARNESS_CONFIG` 未设置或未启用时，原检索服务不挂载MCP端点。启用后每个Bearer token由服务端映射到 `is_admin=true`、`role=leader`及允许的具体indices；写操作另需 `allow_mutations=true`。工具参数不能覆盖身份。未授权请求不能列工具，Origin不在允许列表也会被拒绝。

[注册模板](../resources/knowledge_dedup/registration.example.json)沿用sell_agents的 `scope=admin_system`、`applicable_scopes=[role:leader]`，`default_enabled=0/status=0`保持未启用，工具 `user_visible=0`。部署时用既有管理方式注册skill及MCP工具，把真实服务地址和服务端授权token填入私有配置；本次不自动写sell_agents数据库，也不复制到其默认skills目录。

工具包括选取/估算、快速检查、召回、增量检查、指定候选精查及文档检查。默认工具检查使用dry_run；已授权任务可指定false。深挖由现有Agent自行改写query、调用recall和compare，按结果决定是否继续。工具为同步调用，大范围任务应分小批或使用CLI；当前没有新增后台任务队列。交互模式通过既有会话下一轮继续；非交互模式失败直接说明原因。

## 验证

默认 `./run_offline_tests.sh -q` 包含新增测试。定向入口为 `tests/retrieval/test_*dedup*.py`、`test_conflict_*.py`、`tests/services/test_dedup_harness.py`；覆盖范围隔离、模型错误与证据、批内重复、策略、并发版本、文档替换、CLI和权限。另保留原入口/文档管道/架构及文档链接回归。

真实模型案例复核和生产ES写入验收是不同范围。现有Payoneer案例可离线载入，使用真实rerank/LLM检查，不对生产索引写入；原始案例、配置及日志不入Git。

通过既有sell_agents服务入口验证两个Agent模式的独立测试如下。它使用真实skill_agent路由/Agent/LLM，技能存储与知识库使用明确的内存夹具，不访问生产知识或写技能库：

```bash
PYTHONPATH="$PWD/src:/absolute/sell_agents" python tests/integrations/dedup/skill_agent_service.py \
  --llm-config /absolute/private/agent_service_config.json \
  --output private/dedup/skill-agent-eval.json
```

该独立测试会调用配置中的deepseek模型，不属于默认离线测试。非交互场景验证实际记录结果且不删改正文；交互场景验证缺少范围时等待用户、不调用知识工具。
