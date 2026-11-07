# ES8 返回字段修复与真实新旧知识对照，2026-10-09

本机隔离实现已修复并验证：dual 的请求级 `_source` 策略对齐旧 ES7，正确请求和回填嵌套向量，保留业务重排所需根向量。200 组真实 ES8 查询与按旧策略构造的对照全部严格一致；真实 ES7/ES8 的完整 `/search` 返回分别有 91/100、88/100 组一致。因此可以确认本次字段修复通过，**不能认定全部新旧检索结果完全打平**。

## 现场、授权和源码

- 隔离开发目录：`/root/knowledge_database_builder-es817-release-20261009`。
- 分支：`codex/es817-native-batch-20261009`；HEAD：`12a86da7163c5136524a60730c6af476788933c5`，加本轮未提交修改。
- 修复前/当前线上 ES8 SHA256：`9ed795c5b837e8f6b46360ca46e0181feb67b08a288362275efe985111bba223`。
- 本机修复后 ES8 SHA256：`523e62a94c03d6d94d785210495245bd78cd0cd881532b7dd8166d77bdc1afca`。
- 真实旧引擎：git `f873a593` 中的 `EsSearchInterfaceOri`，SHA256 `7cb7bb06a8fc3c4bc99bcad133badcc776f32f96971a4c7d757a43b3ca13c0f1`。旧 SDK 7.10 独立进程查询真实旧库，新 SDK 8.17.2 查询实际 ES8.17.0 PaaS/Serverless；没有让 ES8 SDK 直接请求 ES7。

本轮只在隔离目录改代码、测试、schema、文档和记忆。没有 commit/push、生产 git pull、部署、服务重启、运行配置切换或任何持久 ES 写入。此前已上线的批量实现保留，不自动回滚。原服务 checkout 和既有未提交/未跟踪现场保留；不干扰独立迁移。

## 修改内容

| 位置 | 修复与验证边界 |
|---|---|
| `es8_search_interface.py:33,939` | dual 含向量时恢复旧 `excludes=[indexes.embedding,image_indexes.embedding]`；根 `title_embedding/content_embedding`、正文、类目和 metadata 保留。非 dual 模式及 dual 无向量保持原完整 source。 |
| `es8_search_interface.py:486` | inner_hits 请求使用 `indexes.text/indexes.embedding`，图片路径动态使用 `image_indexes.text/image_indexes.embedding`；响应内 `_source` 仍是相对键。修复相对请求字段导致空 inner source 的根因。 |
| `es8_search_interface.py:883` | 根据实际 nested 路径和 offset 回填，文本/图片数组分别处理；无效路径或越界不写入。 |
| `es8_search_interface.py:899` | dual 合并分别补齐文本/图片的缺失向量，保留已有向量，不以相同文字跨数组串写，不猜无 text 条目的对应关系。 |
| `es8_search_interface.py:981` | 原生批量请求失败后的独立查询保持同样 source 策略。 |

保持原生 HNSW/KNN、BM25/vector 分路、每索引预算、原生 msearch 并发上限 2 和原序合并。本轮没有改 Router、业务消费者、HTTP 格式、索引名、CRUD、数据存储或配置。请求级 source 过滤不会删除已存向量，与 Serverless 的持久存储向量优化不是同一个设置。

旧 dual 中只被 BM25 召回的知识没有 inner_hits 可补同义问法向量，会使用旧业务层的根向量回退。本次恢复这个旧行为，不是将所有向量一律裁掉。此前的相同命中控制实验说明完整 source 比旧策略多约 19.4% 解压响应字节，mercado_local 样本多 36.8%；不能称为“向量数量多 20%”，也不能把此次不同候选集合的 ES7/ES8 总字节差直接当成性能提升。

## 离线回归

新增 `tests/test_es8_source_compat_20261009.py`，共 15 项参数化行为测试。使用真实旧、新引擎方法和未改动业务相似度方法，只在 ES API 边界模拟响应。边界根据实际请求的完整/相对字段路径决定 inner source 内容，覆盖过滤到回填、合并、业务重排全过程，避免手工伪造已有 embedding 的 inner_hits 掩盖请求错误。

覆盖根向量和文本保留、BM25-only 回退、独立查询 fallback、非 dual 模式完整 source、图片/文本路径隔离、越界和未知路径、已有向量及无 text 条目保护。原 native batch 测试同步核对 dual source 策略。

| 执行 | 结果 | 证据 |
|---|---|---|
| 相关三个 ES8 测试文件首次运行 | 61 passed、1 failed；失败来自测试边界遗漏 kwargs 中的 `_source`，已修正测试边界，保留初次证据 | `es817_source_fix_unit_20261009.xml` |
| 修正边界后复跑 | 62 passed、3 warnings，0.96s | `es817_source_fix_unit_retry_20261009.xml` |
| 原 310 项 + 本轮新增 15 项 | **325 passed、2 既有 xfailed、417 warnings，7.87s**；0 failure/collection error | `es817_source_fix_regression_20261009.xml` |

两个 xfail 是既有 O01 单条挖掘失败仍可能报告任务成功、O03 示例 `es8.17` 在本 release 引擎初始化被拒绝。没有把它们称为已修；本轮线上使用合法 `8.17` 配置，不修改这个用户此前延后/单独讨论的范围。

完整回归命令使用既有 `/root/kdb-forge/.venv-es817/bin/python`，仅作为测试解释器，不运行/修改新项目。依赖不安装/替换；先 import 真实 elasticsearch，缺失的 fire/termcolor 仅从现有 py38 环境按文件加载纯 Python 包：

```bash
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/knowledge_database_builder-es817-release-20261009 \
  /root/kdb-forge/.venv-es817/bin/python - <<'PY'
import importlib.util, sys, pathlib, elasticsearch
pure_root = pathlib.Path('/root/miniconda3/envs/py38/lib/python3.9/site-packages')
for name in ['termcolor', 'fire']:
    if importlib.util.find_spec(name) is None:
        package = pure_root / name
        path = package / '__init__.py' if package.is_dir() else pure_root / (name + '.py')
        spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=[str(package)] if package.is_dir() else None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
import pytest
names = ['test_es8_interface', 'test_es8_native_batch_20261009', 'test_es8_source_compat_20261009',
         'test_delete_by_file', 'test_dual_route_recall', 'test_es8_autocreate_20261005',
         'test_es8_conditional_integration_20261008', 'test_es_mapping_compare',
         'test_from_type_count_api_20261008', 'test_insert_check_duplicate_arg',
         'test_insert_ext_info_20261005', 'test_off_task_es817_20261008', 'test_search_response_ids']
raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider',
    '--junitxml=docs/reviews/es817_source_fix_regression_20261009.xml'] + ['tests/' + name + '.py' for name in names]))
PY
```

该命令是实际验证记录。复用时应另起证据文件名，避免覆盖已有首次结果。

## 真实新旧查询：各 100 组

复用此前验证过的 200 个不同 query 及已有 1024 维向量，fixture SHA256 `7b3d935deb8831885c2a993127217d3b0017eb8191aee5bb2d62257549212830`。PaaS 为 payoneer_olive/payoneer 各 50；Serverless 为 mercado/**mercado_local** 各 50，包含各自私库联合/逆序。每 provider 80 QA、20 segment，20 个实际 category_ids 条件，top2/5/10/20/40、同义问法开关和阈值 0.4/0.6。

使用原 `SearchDataInterface` 和原 `/search` handler 在 120 独立只读进程内完成召回、相似度、重排、格式化，不启动服务、不请求运行服务。外部 embedding 边界复用已有向量，没有额外 embedding/LLM 费用。旧引擎运行真实类和真实旧 ES API，只禁止初始化建库/改 mapping；子进程 IPC 不是伪造候选响应。

每 query 比较三份结果：本机修复代码、冻结修复前 ES8 加上从实际旧类导出的 source 策略作为对照、真实旧 ES7。前两者比较实际请求、全候选及顺序、完整 source、四类向量、ES score/total、业务 similarity 和最终完整响应，全部逐值严格一致；最后一项单独作为真实新旧知识对照，不混淆算法和数据差异。

| 项目 | PaaS | Serverless |
|---|---:|---:|
| 完成不同 query 数 | 100 | 100 |
| 修复代码与旧 source 策略对照严格一致 | 100 | 100 |
| 真实 ES7/ES8 完整最终响应一致 | 91 | 88 |
| 最终知识 ID 顺序/集合一致 | 91 | 88 |
| 第一条知识 **ID** 相同 | 100 | 100 |
| 完整列表不同 | 9 | 12 |
| 公共候选的非向量 source 不同，case 数 | 3 | 0 |
| 公共候选的根向量不同，case 数 | 2 | 0 |

第一条 ID 相同不等于其正文和 metadata 必然相同。PaaS 三个 case 有公共知识源字段变化：14 个不同 ID 的 insert_time/update_time 不同，其中 2 个不同 ID 的正文/答案及 content 根向量也不同。已读出的新库时间为当天 2026-10-09，旧库仍是 9 月；证据只能证明两端当时存储版本不同，不能据此指定写入方或断言是迁移错误。本轮不自动改数据、覆盖新库或再次同步。

Serverless 公共候选正文、metadata 和根向量没有检测到变化，完整列表差异伴随候选集合差异。旧 script_score 精确扫描与新 native ANN 是需要区分的背景，但不能把所有差异未经逐路验证统一归因 ANN。没有固定自然语言 query 的人工质量标注，不判断多出的知识必然更好或更坏。

用相同输入额外复核三个代表性反例，初次 200 组结果保留，不用复测覆盖：

| case | 公库/知识类型 | 旧结果仅有项：排名 / 原业务最终 score | 新结果仅有项：排名 / 同一业务 score | 候选阶段证据 |
|---|---|---|---|---|
| paas-018 | payoneer_olive / segment | 10 / 0.6059191022 | 9 / 0.6134390190 | 新项不在旧候选中；旧项仍在新候选中，最终被排名挤出 |
| serverless-002 | mercado / segment | 5 / 0.7097577504 | 4 / 0.7311780680 | 新项不在旧候选中；旧项仍在新候选中，最终被排名挤出 |
| serverless-055 | mercado_local / QA | 40 / 0.8037215104 | 36 / 0.8273849477 | 两项分别不在另一边的候选中 |

三组公共候选正文/metadata/根向量无检测差异，公共最终知识分数差均为 0；修复代码与旧 source 策略对照仍严格一致。新增加的知识按原业务相似度指标更高，但这不是人工相关性评价，也不证明其它 18 个不同列表的原因已经逐条定位。16 次 ES8、12 次 ES7 native 只读请求，0错误/guard违规，线上身份与 SHA 未变。证据 [反例复核](es817_source_fix_counterexamples_20261009/evidence.json)、[排名分数](es817_source_fix_counterexamples_20261009/selection_scores.json)，完整私人反例另存 0700/0600 排除版本控制的目录。

额外发现/保留边界：引擎返回的 `total` 在 PaaS 99 组、Serverless 97 组不同。旧类 dual 对各子请求 total 取全局最大值；当前 ES8 按路汇总各索引后取最大值，再汇总 provider，且向量子请求算法不同。本次没有改 total 计算，它与 source 策略对照完全一致，但不符合“全部公开输出已打平”的结论。本轮 `/search` 最终返回不暴露这项 engine total，不能据此忽略公开接口差异。

真实 200 组共 410 次 ES8、209 次 ES7 native 只读请求，0 guard 违规、0原生错误、0持久写、0运行服务 HTTP。证据 [完整汇总](es817_source_fix_validation_20261009/evidence.json)、[逐 case](es817_source_fix_validation_20261009/cases.jsonl)、[差异汇总](es817_source_fix_validation_20261009/difference_summary.json)。私有反例受 64MiB 总量限制，只实际保存 4 个 PaaS case，不把未落盘的其它反例说成有完整私人快照。

## 同一存储数据的补充对照

另外限制到旧、新两端完整 `_source`（包括所有已存向量）逐值完全相同的既有知识，排除数据版本变化：四公库分别检查 29/29/28/28 个公共候选，全部源数据相同，各选择 10 条，加入相同 `_id` 条件，各做 5 个 QA query、top10、同义问法开启。

**20/20 完整最终响应逐值相同**，包括返回知识 ID/顺序、正文、metadata、业务最终 score。原生召回分数不要求 ES7/ES8 跨算法逐字相同。该实验是受限可比语料上的验证，不替代上面的实际 200 组，也不证明全库 ANN 与旧检索数学等价。

34 次 ES8、37 次 ES7 native 只读请求，0错误/guard违规，未创建测试索引、未写 fixture 到 ES。证据 [相同源数据对照](es817_source_same_data_20261009/evidence.json)。

## 复现和交付

在开发目录执行（证据目录必须不存在，已存在时用新的目录名）：

```bash
env PYTHONDONTWRITEBYTECODE=1 python tests/es817_source_fix_validation_20261009.py \
  --fixture data/es817_parallel_100_20261009_private_run3/inputs.json \
  --output docs/reviews/es817_source_fix_validation_20261009 \
  --private-output data/es817_source_fix_validation_20261009_private
env PYTHONDONTWRITEBYTECODE=1 python tests/es817_source_same_data_20261009.py \
  --fixture data/es817_parallel_100_20261009_private_run3/inputs.json \
  --output docs/reviews/es817_source_same_data_20261009 \
  --private-output data/es817_source_same_data_20261009_private
env PYTHONDONTWRITEBYTECODE=1 python tests/es817_source_fix_validation_20261009.py \
  --fixture data/es817_parallel_100_20261009_private_run3/inputs.json \
  --output docs/reviews/es817_source_fix_counterexamples_20261009 \
  --private-output data/es817_source_fix_counterexamples_20261009_private \
  --case paas-018 --case serverless-002 --case serverless-055
```

工具先验证存在、部署版本、只读预算及线上进程/文件 SHA。原生请求起始至少间隔 0.5s，batch 并发最多 2，宿主负载过高会暂停/终止探针。配置仅修改内存副本关闭 ensure/mapping 初始化；不切实际运行配置。旧 SDK 子进程和新 Router/client 正常关闭，无 PIT/scroll 上下文。本次记录的 120 检索父进程 2431343、挖掘父进程 1533339、身份和守卫文件 SHA 前后保持一致。

本轮三阶段合计 460 次 ES8、258 次 ES7 native 只读请求，共 718 次；不包含此前独立的并行/串行 200 组测试和 source 诊断。完整 200 组探针工具的历史 SHA 与后来加入三 case 复核参数的最新工具 SHA 分别记录，不能用最新文件 hash 冒称历史执行版本。

图片动态字段与回填已通过离线测试，此前四库限量只读未找到 image_indexes 样本，本轮不冒称图片真实数据链路已经验收。未进行在线 HTTP、真实写 CRUD、并发压力或全面新旧自然语言质量评测；其它公开接口/已知限制不因本次 source 修复自动关闭。

可审代码/schema/测试/工具差分见 `es817_source_compat_fix_20261009.patch`，文件及证据 SHA 见 `es817_source_compat_fix_20261009_manifest.json`。本轮修复代码尚未发布；需要用户针对这次变更另发明确上线指令。
