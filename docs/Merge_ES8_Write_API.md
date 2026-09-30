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
