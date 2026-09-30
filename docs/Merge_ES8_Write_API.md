# ES8 与写入 API 合并记录

## 来源

- 本地 `d62a5c6`：ES8.17 named API、native KNN/BM25、按 index 路由、兼容方法、挖掘边界。
- 远端截至 `a6d7d86` 的四个提交：modify 写入计划、FastAPI 薄路由/懒加载、单文档插删、audit=2 修复。
- 三处冲突：`src/kdb/crud/service.py`、`function_schema/service.KnowledgeService.md`、`pyproject.toml`。

## 决策

1. HTTP/modify 源代码保持远端实现，数据请求走本地 ES8 引擎，不切回 ES7。
2. 同名 CRUD 方法只保留兼容层实现；远端新名 `search_text_multi`、`web_search`、
   `batch_insert` 作为适配入口，保留注入参数、index 解析优先级及 caller dict 不变的修复。
3. 远端引用的 `kdb.category.client` 未随提交提供；其既有调用协议仅为
   `map_cate_name_to_id(client, name)`，默认复用本地通用接口，仍允许注入。
4. 补齐可选 `LegacySimilityTools` 导出和本地阈值兜底，杜绝缺依赖时静默跳过查重。
5. 保留本地文件操作、显式类目默认、空 index 文本过滤、fileName URL 渲染；
   Payoneer Olive 推断仍归挖掘，不恢复。
6. 包级 CRUD 导出改为惰性加载；`health`/`dry_run` 无需导入 CRUD、ES 或旧项目。
7. 合并远端 audit/from_type、关键词异常与多模态文本拼接语义；不复制旧 `_id` terms no-op。

## 验证方法

- 先检查 `git status`，`git fetch` 后按双方 commit/方法契约比较，不用整文件 ours/theirs 覆盖。
- 运行 `.venv/bin/python -m pytest -q -m 'not integration'`；API/modify 测试已从
  `tests_unit/` 纳入 `tests/` 的默认收集，缺依赖必须报错，不再 skip。
- `tests/test_merge_contracts.py`：真实 Service/Repository + 假 IO，覆盖三条 HTTP 写路径、
  synonyms、audit=2/非法值、查重兜底和注入、配置索引优先级、新旧检索方法、导入隔离。
- 检查无冲突标记、`git diff --check`，再创建 merge commit、普通 push；禁止强推覆盖。
- 本次只做离线验证，不访问生产/测试 ES，不执行迁移或部署。

注意：这些 HTTP 写入路径不等于旧 `/insert`、`/search`、`/web_search` 全部路径已实现；
方法存在和离线通过也不等于完整服务行为等价。

## 本次结果

- Python 3.9.6 隔离虚拟环境，elasticsearch-py 8.17.2；安装真实 FastAPI/Pydantic 2/httpx。
- 离线测试：52 passed，11 deselected（真实 ES 集成测试），无 skip。
- 远端 KnowledgeService 的 20 个公开方法均存在，参数名称/顺序检查通过；这不替代行为测试。
- HTTP/modify 源文件与远端保持一致，ES engine/router 源文件与本地 d62a5c6 保持一致。
- compileall 和 diff whitespace 检查通过；未访问 ES、迁移索引或部署服务。

## 合并后回归加固（2026-09-30）

基线为已推送的 merge `db996da`。用户明确本项目只面向 ES8，因此兼容范围是
业务方法/配置调用，不是 ES7 服务端。发现并修复：

1. 构造签名冲突：本地第五位置参数是 legacy_config，远端是 check_duplicate。
   合并后把位置配置当成查重开关，会静默丢失类目/LLM 等配置。现在 Mapping 按业务
   配置解释，bool/None 按查重开关解释；同次传两个配置明确报 TypeError。
2. 写入与 native KNN 的已有衔接缺口：modify 修改标题仅更新根 title_embedding，
   未同步 KNN 实际使用的 indexes.embedding。现在重算向量时，先按目标 index 取原文档，
   替换失效的标题/同义问派生项，保留自定义和图片检索项；显式 indexes 仍优先。
   同文本的归属沿用插入阶段按 text 去重的规则，不新增 provenance 字段。清空根文本
   时将向量设为 null；取不到源文档则不进行会丢失其他检索项的写入。

### 验证结果

- `.venv/bin/python -m pytest -q -m 'not integration'`：69 passed，11 deselected。
  原 52 项全部通过，新增 17 项位于 `tests/test_es8_merge_regressions.py`。
- 新测试贯穿 FastAPI → Service → Repository → 路由引擎 → **真实 elasticsearch-py
  8.17.2 client**，仅替换 Transport.perform_request，不访问网络。
- 覆盖 PaaS/Serverless 定向插入、修改、删除和 refresh；audit=2、同义问、自定义/图片
  索引；标题/同义问变更、空文本清理、显式索引替换；双路 BM25/native KNN、共享过滤、
  分索引去重、多模态渲染；web 分页、显式类目过滤；ES7/9 配置拒绝。
- 在独立测试进程中临时替换为 `db996da` 的三个修复前方法（未改工作区），同一组针对性
  用例得到 9 failed / 2 passed / 6 deselected，确认测试能捕获问题，而非只检查方法存在。
- ES engine/router 与 `d62a5c6` 无差异；HTTP/modify 与 `a6d7d86` 无差异。
  改动集中在 Service；方法名、HTTP 请求/返回结构和客户端依赖未变。
- compileall 和 `git diff --check` 通过。

### 验证边界与复用步骤

这不是阿里云真实 ES8.17 的验收，也未实测 HNSW 召回率、排序质量、刷新可见性或并发
更新。网络替身记录请求，不执行服务端 DSL。记录的集成索引仍是 config_test.json 的
test_case；在用户确认 ES8.17 地址与 native KNN mapping 前，不跑有写入的集成测试，
不自动创建/迁移/清空该索引。本轮无部署。

以后合并 Service 修改时，先比较双方构造函数的位置含义，而非仅检查参数名；对任何
文本修改接口，同时检查 root 向量与 indexes 检索向量。复跑上述离线命令，确认真实
ES8.17 测试环境后再补两种 provider 的写入/查询回环与召回效果验收。
