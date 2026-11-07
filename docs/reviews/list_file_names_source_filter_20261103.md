# /list_file_names 可选来源筛选（2026-11-03）

用户授权：增加 from_type_norm，可为空，空值表示不筛来源。

**最新状态：2026-11-03 22:51 已获授权上线，见 [上线验收](list_file_names_online_20261103.md)。下文开发阶段的“未部署”为当时快照。**

## 实现与调用

`POST /list_file_names` 新增 `from_type_norm: Optional[str]=None`。

```json
{"index_name":"wayfair","from_type_norm":"document","size":200}
```

非空字符串去首尾空白后使用 term 精确匹配；省略、null、空串、仅空白均不加来源条件。
这是用户明确要求的默认行为变化：旧的省略参数请求也不再限定 document/html/manual。
只接受单个字符串，不接受数组；始终保留 del_flag=0，文件名关键词筛选、聚合、size
限制和响应结构保持。成功消息去掉原固定来源白名单描述。

列表筛选独立实现，未修改 `_scope_filters`：文件名解析、预览和删除继续使用
document/html/manual 白名单。列表返回其它来源不意味着允许删除那些来源。
无文件名记录仍不生成 missing 桶；不同来源的同名文件在筛选范围内合并。
`total_count` 仍是返回值数量，不是完整分页总数。

## 开发现场

- 隔离 checkout：`/root/knowledge_database_builder-list-files-20261103`
- 目标：`main`；用户明确要求合入 main，不再新建分支。
- 原开发基线：`3aa4aadc854fd8e8fc6f31555754799882fbabd8`，原功能提交 `6523b07f`。
- 合入基线：`5ad024aaf46b701f51c04ece1230053272476a11`（本轮 fetch 后 origin/main）。
- 复用原隔离 checkout，以 detached HEAD 应用单个功能提交；未连带合入原开发基线上的其它任务提交，未覆盖本机旧目录脏改动。
- 修改 HTTP 模型/处理器、业务 list_file_names、对应 schema/API 文档、回归测试。
- 两层调用关系和引擎未变化，没有架构调整。

实现 SHA256：

| 文件 | SHA256 |
|---|---|
| knowledge_database_search_es.py | b1c443a351d1642054751af3c740642fdaa7f95fffb5904006bd8aa04cc20f6f |
| search_index_data_interface.py（保留线上5个提交后的部署整合版） | 88e9b26967c0a5ba6f41199f36f43a7e11e09c7f05dd1b2ceb4944e94de684b3 |
| test_list_file_names_source.py | 683742a868a981aee064369d5ecfcaa8ff0762105987fbed7668aeca40c37e7c |

## 验证

```bash
cd /root/knowledge_database_builder-list-files-20261103
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /root/kdb-forge/.venv-es817/bin/python -m pytest -q \
  tests/test_list_file_names_source.py tests/test_delete_by_file.py -p no:cacheprovider
git diff --check
```

main 基线重新验证：47 passed，72 warnings，2.45s（原开发基线为 2.55s）。新增来源筛选/HTTP参数测试23项，原文件删除相关测试24项。
警告为既有 Python 转义字符与 Pydantic 配置弃用提示。diff --check 通过。

新测试通过真实 FastAPI 模型/路由、实际业务方法及原工厂 fixture，mock 聚合边界；
验证最终查询条件、参数传递、响应结构和删除白名单。没有连接真实 ES，不能视为
线上新版本验收或 PaaS/Serverless 真实执行验证；未调用真实删除。

## 已知独立问题与发布状态

此前实测的 ES8 agg_terms 子聚合与业务 type_count 结构不一致问题仍待修；
本改动仅增加来源参数，测试使用原约定聚合返回结构，不宣称修复线上 type_count。

用户已明确授权提交推送，并进一步要求合入 main，不再新建分支。
本次提交目标为 `origin/main`。未部署、未修改配置、未重启服务；
线上接口当前仍不接收新参数。
前端/boot-admin 接入时须区分此开发版本与已部署版本。

## 用户随后授权上线

用户明确指令“那就上吧”。线上仍为3aa4aad，与远端main分叉5/1。
在同一隔离checkout将线上既有3aa4aad历史合并进main；功能代码对线上差异仅本次列表参数，
原5个提交全部保留。后续通过线上目录git pull --ff-only更新，不覆盖源码或4个既有脏文件。
发布工具 tests/list_file_names_online_20261103.py 复用原流程和服务身份守卫；默认只检查，
--execute才仅重启检索，并验证两库新参数及检索。运行配置、ES数据、挖掘进程保持。
发布完成的实际PID、目标SHA与验收结果另见本次上线报告。
