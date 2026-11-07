# 来源类型统计接口实施与验收（旧项目，2026-10-08）

后续运行状态：用户明确授权本机重启后，旧8003已于08:59:00 CST加载本报告的实现，真实12统计配对、6输入控制、4原检索smoke通过。见[本机加载与重启报告](/root/knowledge_database_builder/docs/reviews/from_type_count_local_activation_20261008.md)。本报告原“未加载”描述保留为隔离开发阶段的历史记录。

任务 LEARNING-COUNT-API-20261008。用户已确认方案并要求旧、新版执行；原 `/get_learning_count` 尚未实现，最终仅新增 `POST /get_from_type_count`，默认 from_type=chat_auto。本报告是旧项目实施结果，新项目由既有“sg-kg检索重构”会话另行实施。

## 结果与运行边界

旧接口已在隔离开发 checkout 实现，新增88项行为测试+既有130项回归全部通过（218 passed）。12个真实只读进程内HTTP用例与各自原生计数一致，覆盖Serverless和PaaS。未修改正在运行的旧目录实现/配置，未重启、部署、commit/push或写ES。端点尚未加载至运行8003服务，不应把进程内ASGI验证描述为运行服务已经上线。

开发目录：`/root/knowledge_database_builder-from-type-count`，detached worktree，HEAD `a36efc7245dedf2492f5be396f87390885f3a4f4`。以旧服务现场为源码基线：从root复制已加载的engine1137283和service c4f81补丁，保留业务224e123、工厂984b512原HEAD实现；没有使用es8-dev广泛审计修复冒充运行基线。原文件SHA在 `from_type_count_baseline_20261008.json`，只复制两份现有已修改实现与安全测试支持，不复制/修改凭据或运行配置。

## HTTP契约

```json
{"index_name":"mercado_local","from_type":"chat_auto","start":"2026-09-01 00:00:00","end":"2026-09-30 23:59:59"}
```

```json
{"success":true,"count":123,"message":""}
```

- `index_name`原物理名；兼容`indexName`别名，两者冲突422。null/空/省略返回成功0且无ES调用。只接受单个名称，逗号/通配符/_all/空白/路径/前导排除符/超过255字节等非法范围或名称输入422，无版本后缀、映射或公私库拼接。
- `from_type`省略默认chat_auto，显式值精确匹配原字段；null/空/非字符串422。固定quality_level=high，不额外添加del_flag、audit_result、data_type、category或from_type_norm。
- 时间使用本地`yyyy-MM-dd HH:mm:ss`，不转UTC；只有两个非空时增加insert_time.gte/lte。单边有效时间故意忽略，与Java相同；反转范围正常0。无效格式/日期/时区422；不接收任意DSL或未知筛选字段。
- 使用原生_count精确计数，不继承Java默认_search可能在10000时返回下界的截断；此差异已在用户确认的方案中明示。
- 缺库、客户端错误或分片不完整返回HTTP200、success=false、count0、通用错误message，并记录异常。正常0是success=true。新路径启用严格count非负整数、failed=0和successful=total检查，拒绝非空failures/error及单物理名零分片的异常响应以及提前终止/非布尔超时状态，不把部分结果标为成功。无自动建库/mapping/embedding/source读取。

## 实现与兼容保护

HTTP model/handler → SearchDataInterface.get_from_type_count → 原工厂 → ES7/OpenSearch/ES8 native count。handler用asyncio.to_thread执行阻塞client请求。新增内部es_count_utils完整性校验；旧ES7 count新增可选require_complete=False，默认原调用返回语义不变；ES8保留既有失败分片重试，新接口显式严格校验；OpenSearch补原生body count能力。不修改Router、既有查询/CRUD请求、嵌套文档构造或业务默认筛选。

源码AST证据 `from_type_count_ast_contract_20261008.json`：182个原函数中，仅两个count方法为此次新增可选参数；其余180个函数AST不变。业务和service所有原函数AST不变。既有十个Request模型字段/默认/配置与升级前f873a593完全相同，仅新增授权的FromTypeCountRequest。

## 实际测试

```bash
env -C /root/knowledge_database_builder-from-type-count \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/knowledge_database_builder-from-type-count \
  /root/kdb-forge/.venv-es817/bin/python -m pytest -q \
  tests/test_from_type_count_api_20261008.py tests/test_es8_autocreate_20261005.py \
  tests/test_insert_ext_info_20261005.py tests/test_es8_interface.py \
  tests/test_dual_route_recall.py tests/test_es_mapping_compare.py tests/test_delete_by_file.py \
  tests/test_insert_check_duplicate_arg.py tests/test_search_response_ids.py -p no:cacheprovider
```

实际218 passed、399 warnings、6.28s；warnings为既有SyntaxWarning和Pydantic配置弃用重复导入提示。新文件88例；旧130例=86既有专项+32自动建库+12ext_info。用真实service/business/工厂/实际ES7、OpenSearch、ES8类，仅mock外部客户端及无关embedding/相似度边界，不mock整个业务或engine。涵盖含软删和待审知识仍被计数、qa/segment跨类型、边界日期、各provider、来源/alias/输入保真、12001不截断、错误/缺库/部分响应/不完整/坏count和重试后完整恢复；断言计数不创建/mapping/CRUD/search或embedding。

失败记录亦保留：第一次pytest参数误用保留名request导致collection error，修为payload后63通过；随后65+130全套中，旧metadata测试误把“新增授权Request类”当旧类被修改，194过/1失败。将其改为严格比较原10类并仅允许新FromTypeCountRequest后195通过；旧模型保护仍在，没有放宽原字段断言。`from_type_count_legacy_test_adjustment_20261008.diff`单列该调整。原181、195通过的中间日志均保留。随后两项目对齐单物理名验证，增加9个非法名称与两个year0001时间用例，并修strftime年不足四位的格式边界，206通过；随后对齐零分片却正计数/非空failures却failed0的异常响应保护，210通过（额外4例）；最终与新端对齐单物理名不应零分片、top-level failures及提前终止/非布尔超时保护，218通过（再增8例）。只读工具初次在版本/HEAD后用错Router方法名而退出，无ES写；修为实际resolve_provider后以下验证成功。

```bash
env -C /root/knowledge_database_builder-from-type-count \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/knowledge_database_builder-from-type-count \
  /root/kdb-forge/.venv-es817/bin/python tests/from_type_count_readonly_20261008.py
```

12例全部通过。真实工厂+真实ES8内部Router、原生client和未改变的统计业务方法通过ASGI handler；无lifespan/server启动，略过业务构造器避免无关类目/embedding I/O。先HEAD两端存在并核对ES7/8.17版本，仅计数。进程内引擎内存ensure=False，不写运行配置，has_build_index始终空。ES7参考通过旧版裸HTTP读取，不以ES8客户端访问ES7。最终一次正常执行3次版本GET、4次HEAD、36次native_count（新handler12+新原生对照12+旧原生12）；读取无文档source/向量。最初成功、参数对齐后成功、最终strict/hash绑定成功各一次；另初次工具方法名错误只执行预检7请求。所有client关闭。

| 原物理名 | provider | 默认chat_auto旧/新 | 双边时间旧/新（9/1至10/8） | 新接口vs新native |
|---|---|---:|---:|---|
| mercado_local | Serverless | 388/387 | 51/50 | 6/6一致 |
| payoneer_olive | PaaS | 4939/4939 | 2378/2378 | 6/6一致 |

默认/显式chat_auto/单边时间得到相同计数；document及不存在来源均0，两端相同。非默认来源非零行为有离线合成数据覆盖，真实document当前为0，不夸成真实非零覆盖。Local差额对应前份只读证据中旧端10/7新增ID24522b3f0f2566e6606121d75920ad3e而新端不存在；本轮计数未同步该记录，不添加审核条件掩盖数据差异。缺库/错误写保护仅离线测试，不为验证而真实创建或删库。

## 交付及未验证

- `from_type_count_implementation_20261008.diff`：相对实际运行源码基线的功能增量，避免夹带前次已存在ext_info/auto-create补丁。
- `from_type_count_implementation_manifest_20261008.json`：完整功能文件/SHA、基线、验证数、零副作用记录。
- `from_type_count_readonly_20261008/evidence.json`：脱敏每次参数/DSL/计数/分片/版本证据。
- `from_type_count_final_strict_regression_20261008.log`：最终实际pytest输出。

主要改动为service模型/handler、业务统计方法/Protocol、两引擎count及新utils，另测试、函数schema、架构图。复用的自动建库/metadata测试来自现有场景，不是新增95/130项测试。函数schema均先写/读再生成代码。

当前未验证运行服务已加载端点、真实ES7/OpenSearch客户端网络路径（原生ES7参考是裸HTTP）、>10000真实from_type数据、故障真实注入或压力/并发。既有类目漏过滤、计数relation丢失、排序差异、迁移追平等问题未因计数API通过而关闭；没有声称全面替代或同步数据完成。

新项目任务已实际送达thread01a0f061-f2ad-7b10-985c-cd856ca8a7bd，正在其隔离checkout实施，须回收其最终报告后才能说新版本已完成。禁止把本报告当作部署/重启/写数据许可。

`knowledge_database_search_service/src/knowledge_database_search_es.py` SHA256 `a14d1431568a399a4124c1f6817cec849259892dcdbab9137a6b86b4f12eda6b`

`knowledge_interface_tools/es8_search_interface.py` SHA256 `8b773057ecc41da40fc5d87eb1afc1bc21ecc4c8a9a8a23f27c6b17f69dc7343`

`knowledge_interface_tools/es_count_utils.py` SHA256 `0a4d82e166f98cb382fe39ecebed52156e7bcabc02870ba3f073471b4d229e78`

`knowledge_interface_tools/es_search_interface.py` SHA256 `1aaebeaf53587f4e9e585fb908d09318c0a0be636eb4f36b8076517fb5c739e7`

`knowledge_interface_tools/search_index_data_interface.py` SHA256 `509ec93d1b5e1c47391063af65304aebedd833180a5051e43d34a6c267b84b27`

独立请求模型跨项目对照：tests/compare_from_type_count_requests_20261008.py直接导入两版实际模型，无mock类，36种安全JSON输入接受/拒绝、alias/default/本地日期规范化一致，原输入未变，0差异；证据from_type_count_request_parity_20261008.json。这36项是独立探针，不计入88新增pytest数量，也不代表新项目HTTP计数实现已完整通过。

最终真实只读 evidence.json 记录了5个实际执行实现文件SHA，已与最终manifest逐一相等；不是拿旧代码响应证明新哈希。218测试通过后的运行目录engine/service/business仍保持原SHA/PID，见manifest runtime_unchanged_verified。
