# list_file_names_online_20261103 deployment helpers

复用旧 `es817_source_online_20261009.deploy_source` 发布流程与
`es817_online_rollback_20261009.validate_services` 身份守卫。用户已明确授权此次上线。

## read_json(path)
读取已 stat 且不超过 2 MiB 的 JSON 文件，返回解析值。不输出配置/凭据。

## digest(path)
流式 SHA256，返回十六进制；用于配置、代码、既有脏文件和日志外部状态验证。

## save(path, value)
原子替换私有 JSON 发布记录；临时文件权限0600。只写 backup/，不覆盖生产代码。

## api(path, payload=None)
限量调用 localhost 的 /openapi.json、/search、/web_search、/list_file_names；
payload 非空时 POST，只读。超时30秒，响应上限8MiB，返回JSON、耗时和字节数。

## probe()
读当前配置并用 Router 连接 payoneer_olive、mercado_local 已有索引，先 HEAD 验证。
仅 raw search 聚合/样本与上述 HTTP 读接口，不使用会自动创建索引的写调用。
对照每库6种来源参数与原始ES聚合；每库1次web查询和1次语义检索。
只保存计数、耗时、身份/集合哈希，不保存知识原文、向量或凭据。finally关闭client。

## main()
CLI --commit 为已验证且已推送目标SHA；默认仅检查，--execute 才发布。
必须从已知线上3aa4aad开始，校验现有activation中的两个服务身份、日志、配置、
4个既有脏文件。目标必须包含旧HEAD。只通过目标目录git pull --ff-only origin SHA
更新；拒绝新增路径碰撞。SIGTERM仅精确检索父进程，等待退出后原命令/环境/日志
启动；不强杀，不改挖掘进程，不改配置。不重复执行已有backup记录的部署。
新OpenAPI仅允许本次list_file_names变化，更新activation的检索身份，执行probe，
再次确认配置/脏改动/挖掘/日志不变。错误记录阶段并退出，由执行者检查后恢复，
不得盲目重复重启。

## SQL / 副作用
无SQL，无真实ES写入。备份、git pull、仅检索服务重启属于用户授权范围。
失败回退采用开发端revert本次功能并push，再在生产git pull，禁止覆盖生产代码。
