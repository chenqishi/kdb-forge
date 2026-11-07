# /list_file_names 来源筛选上线验收

2026-11-03，用户明确授权“那就上吧”。已在main/120旧项目完成上线。

## 代码与服务

- 目录：`/root/knowledge_database_builder`；实现部署提交 `a6058547c03025f17ffb844c2a9eb48658274178`。
- 线上原HEAD `3aa4aad` 的5个提交已在开发环境合入main，未丢失；线上通过
  `git pull --ff-only origin a6058547c03025f17ffb844c2a9eb48658274178` 快进，无直接覆盖源码。
- 北京时间22:50:44开始，22:51:01健康验收完成。
- 仅检索服务重启：原PID47173 → 新PID2977520，4个worker和resource tracker，8003正常。
- 沿用 `.venv-es817/bin/python`、原命令/进程环境及原日志；未安装或替换线上依赖。
- 挖掘PID1533339未变，6000/health code=0；运行配置4文件与既有脏文件4项SHA全部不变。
- 原日志继续追加；本次窗口新增19466字节，Traceback和ASGI异常计数均0。
- 无ES写入、无索引/别名/路由变更、无知识删除/审核。

## 真实验收

PaaS `payoneer_olive` 和Serverless `mercado_local`：
每库测试来源参数省略、null、空串、空白、document、auto_learning，共12次列表请求。
各请求的文件名和doc_count均与独立原始ES聚合完全一致；size=5限量验证。
4种空值语义一致，document及auto_learning准确限制来源。

| 索引 | 列表6次 | web_search | search |
|---|---|---|---|
| payoneer_olive / PaaS | 全通过，15–44ms | 2条，58.50ms | 2条，3071.81ms |
| mercado_local / Serverless | 全通过，18–39ms | 2条，49.68ms | 2条，431.37ms |

检索用已有QA标题，语义调用包含embedding与本地重排；PaaS首次调用3.07秒如实保留，
不是压测或稳定延迟结论。web返回total=10000是现有接口口径，本次没有将其当精确库存。
OpenAPI已出现可选from_type_norm，其他端点及模型未改变。

另从sg经公网 `120.77.147.247:8003` 验证OpenAPI与mercado_local的auto_learning列表，
返回集合哈希与main机内请求一致。共17次成功只读业务请求（16机内+1公网），另有OpenAPI检查。
已将线上生效状态同步给boot-admin-sg；未部署或修改boot-admin。

原始脱敏记录：[list_file_names_online_20261103.json](list_file_names_online_20261103.json)。
生产私有发布记录：`backup/list_file_names_20261103/`，包含阶段、原激活记录、原进程环境与pull结果。
环境备份仅在生产私有目录，不提交凭据。

## 测试与限制

合并代码后的接口/删除回归47项通过。额外尝试旧回退工具的9项测试时，本地8.17测试venv缺psutil，
9项均在import失败；生产venv有psutil但无pytest，未安装依赖或修改环境。此9项不计通过。
生产实际身份守卫和发布默认只读preflight已成功，验证了现有两服务身份；部署工具通过Python3.9语法检查。

本轮仅验证来源参数和检索健康；此前已知type_count子聚合契约问题仍未修复，不宣称全部接口问题清零。

## 回退边界

若后续需要回退本次功能，在开发端基于最新main revert功能提交 `0cfb6c19`，保留已合入的线上5个提交，
解决文档/记忆冲突并验证后push；生产仍仅通过git pull更新，再使用精确进程身份、原环境和日志重启检索。
不直接覆盖生产代码，不reset或clean，不运行会切回ES7配置并重启挖掘的旧完整回退命令。
本轮未执行回退。后续新的部署/重启仍须当次明确授权。
