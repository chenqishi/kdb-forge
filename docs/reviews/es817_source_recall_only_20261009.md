# 同一 ES8：修改 source 策略前后的召回 ID 对照

2026-10-09。已完成用户明确要求的对照：**两边都是新 ES8 引擎和相同的新库，只比较本次 `_source` 字段策略修改前后，PaaS 100/100、Serverless 100/100 召回一致。** 本次没有查询旧 ES7，也没有用“修复前代码加旧策略的 oracle”代替未修改的真实基线。

## 对照对象

- 工作目录：`/root/knowledge_database_builder-es817-release-20261009`。
- 分支 `codex/es817-native-batch-20261009`，HEAD `12a86da7163c5136524a60730c6af476788933c5`，已有 source 修复尚未提交。
- 修改前：从该 HEAD 精确取出的真实 ES8 类，完整 outer source、原相对 inner source 请求，SHA256 `9ed795c5b837e8f6b46360ca46e0181feb67b08a288362275efe985111bba223`。
- 修改后：本机实际修改的真实 ES8 类，outer 排除 `indexes.embedding/image_indexes.embedding`，正确请求完整路径的 inner_hits 并回填，SHA256 `523e62a94c03d6d94d785210495245bd78cd0cd881532b7dd8166d77bdc1afca`。

两份真实类仅加载到 120 的独立测试进程内存，共用实际 ES8 client/Router、同一份配置副本和相同的既有索引；线上代码没有替换。两种实际部署均为 ES8.17.0，使用现有独立 ES8.17.2 SDK 解释器。整个过程未改引擎实现、配置、索引或数据，也未发布/重启/commit/push。

每 query 轮流执行修改前/后。调用原业务层和原 `/search` handler 的进程内链路以保证 ES 收到实际业务查询，embedding 边界复用相同的已有向量，不启动服务、不向运行服务发 HTTP。验收项是 **ES 原始召回和引擎合并候选**，不把业务最终 top-K 的排序差异混入召回 ID 判断。

## 样本和实际结果

复用准确的 200 输入 fixture，SHA256 `7b3d935deb8831885c2a993127217d3b0017eb8191aee5bb2d62257549212830`。每 provider 100 个不同 query；PaaS 为 payoneer_olive/payoneer 各 50，Serverless 为 mercado/**mercado_local** 各 50，包含原名私库联合与逆序。每 provider 80 QA、20 segment，20 个实际 category_ids 条件，包含同义问法开关、不同 top-K 和阈值。查询文字、向量、库名、条件、预算两边相同。

| 验收项 | PaaS | Serverless |
|---|---:|---:|
| 完成不同 query 数 | 100 | 100 |
| 原始每路 `_index/_id` 及顺序一致 | 100/100 | 100/100 |
| 合并候选 ID 集合及顺序一致 | 100/100 | 100/100 |
| 原始/合并召回分数一致 | 100/100 | 100/100 |
| 原始各路与引擎 total 一致 | 100/100 | 100/100 |
| 去掉 source 设置后，实际 query/全部其他选项一致 | 100/100 | 100/100 |
| 其余 source 字段及根向量一致 | 100/100 | 100/100 |
| 修改后返回的嵌套向量与原完整 source 对应值一致 | 100/100 | 100/100 |
| 只在修改前/后出现的候选 ID | 0 | 0 |

**没有任何召回 ID 差异，没有差异复测或用复测覆盖首次结果。** 原生每路比较保留 `_index`，不会把不同索引内的同名 ID 错当同一条知识；顺序、分数和 total 都严格比较，不取整或设置浮点容忍。

两边各执行 696 个真实原生子查询。修改前 696/696 无 outer source 裁剪，修改后 696/696 使用准确的两个 excludes。比较器仅从复制的请求里去掉顶层 `_source` 和 `inner_hits._source`，原有 query/filter/KNN k/num_candidates/size/sort/score 等全部保留；原始发给 ES 的请求从未被比较器改写。

附加源字段检查只允许嵌套 embedding 按预期减少；正文、metadata、根向量仍需相同，修改后仍返回的嵌套向量必须等于修改前同一知识、同一数组 offset 的原向量。不能将这个检查描述成所有同义问法向量都完整返回，因为裁剪本来就是只补回命中的部分向量。

## 验证工具与边界

新增只读工具 `tests/es817_source_recall_only_20261009.py`，逐函数 schema 已先创建/读取。工具复用既有读预算、负载、内存和线上进程/配置/源码守卫；冻结源码经 SSH stdin 加载，不覆盖服务 checkout。关闭 ensure/mapping 初始化只发生在配置副本中，索引先确认存在，不自动创建。

工具比较器的 11 个离线测试通过（0.15s）：`tests/test_es817_source_recall_only_20261009.py`。验证相同数量但 ID/index/order/score/total/query 不同均会被发现，source normalization 不改查询控制项或输入，根向量/metadata 改变和嵌套向量错误也会被发现。测试只运行实际比较器函数，不连接 ES。未重复运行未改变的 325 项引擎回归。

实际命令（在上述开发目录）：

```bash
env PYTHONDONTWRITEBYTECODE=1 python tests/es817_source_recall_only_20261009.py \
  --fixture data/es817_parallel_100_20261009_private_run3/inputs.json \
  --output docs/reviews/es817_source_recall_only_20261009

env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/root/knowledge_database_builder-es817-release-20261009 \
  /root/kdb-forge/.venv-es817/bin/python -m pytest -q \
  tests/test_es817_source_recall_only_20261009.py -p no:cacheprovider \
  --junitxml=docs/reviews/es817_source_recall_only_comparator_20261009.xml
```

真实执行共 410 次原生只读 HTTP（400 次成对检索、10 次版本/索引准备），0错误、0 guard 违规、0持久 ES 写、0额外 embedding/LLM、0运行服务 HTTP。请求起始间隔至少 0.5s，msearch 并发上限 2，负载过高会停探针；结束正常关闭共享 Router/client，无 PIT/scroll。源码/配置/线上检索及挖掘进程身份前后相同。本机 `/root/kdb-forge/.venv-es817` 仅用于离线比较器测试，没有运行或修改新项目实现。

结果只覆盖此次 200 个样本的同 ES8 source 变更召回验收；不扩张为任意查询、故障 fallback、图片真实样本或新旧 ES7/ES8 全接口效果验收。之前汇报的 91/100、88/100 属于另一个 **旧 ES7 库与新 ES8 库** 的对照，不能拿来回答这次用户问的“source 字段修改有没有改变新引擎召回 ID”。

证据：[完整汇总](es817_source_recall_only_20261009/evidence.json)、[逐 case](es817_source_recall_only_20261009/cases.jsonl)、[比较器测试](es817_source_recall_only_comparator_20261009.xml)。本轮新增工具/测试/schema/报告的差分见 `es817_source_recall_only_20261009.patch`，实现与证据 SHA 见 `es817_source_recall_only_20261009_manifest.json`。原有实现和既有任务现场全部保留。
