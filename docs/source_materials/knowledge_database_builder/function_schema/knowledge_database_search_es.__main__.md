# `__main__`（8003 检索服务启动入口）

## 所属文件
`knowledge_database_search_service/src/knowledge_database_search_es.py`

## 启动方式
```bash
cd /root/knowledge_database_builder
conda activate py38
export PYTHONPATH="$(pwd):${PYTHONPATH}"
nohup python knowledge_database_search_service/src/knowledge_database_search_es.py \
      config/config_for_search_index.json \
      &> log/es_search_service.log.$(date +%Y%m%d) &
```
**不要用 `~/resstart_up.sh` 重启 8003** —— 那是全量重启（Dify、Redis、Java jar、微信桥都在里面）。

## Inputs
- `sys.argv[1]` — 检索服务配置路径。注意线上这份 config 里的
  `search_engine_config_path` / `embedding_config_path` 指向 **`/root/dify/knowledge_database_builder/config/`**，
  改仓库里那份不生效。
- `SEARCH_SERVICE_WORKERS` (env, 默认 `4`) — uvicorn worker 进程数

## worker 数为什么是 4
单进程下 11 个 handler 全是 `async def` 包同步阻塞 IO，**全部在事件循环上串行**：

```
并发  吞吐(req/s)   单请求 p50
 1      0.79        1.19s
 2      0.81        2.44s
 4      0.76        5.12s
 8      0.76       10.60s     ← 吞吐恒定，延迟线性增长
```

本地实测 `workers=4`（同机同网络，唯一变量是 workers）：

```
              workers=1              workers=4
并发2     0.40 req/s  4.83s     0.89 req/s  1.90s
并发4     0.43 req/s  8.75s     1.09 req/s  2.91s
并发8     0.46 req/s 16.79s     1.22 req/s  5.72s
内存        191 MB                 824 MB
```

**上限受阿里云 ES 服务端并发天花板约束，不是进程数**：该查询形态并发 4 时 ES 约 1.87 req/s、
并发 8 不再增长。所以 worker 再加也吃不到。8/19 实测需求峰值 1.90 req/s（10 秒窗口）、
瞬时最多 3 req/s，服务器利用率仅 17.2%（最忙小时 54%）—— 是秒级突发不是持续过载，4 个够用。

**一个耦合关系**：更早在 main 上测 `workers=4` 曾经**完全无效**（吞吐仍 0.82 req/s），
因为当时 BM25 路还挂着 `boost:0` 的 nested，ES 在并发 4 的天花板只有 1.22 req/s，
而单进程已经跑到 0.78，没有空间。**先减 ES 负载，多进程才有意义。**

## spawn 与 sys.argv
uvicorn 0.32 用 `multiprocessing.get_context("spawn")` 拉起 worker。
spawn 是全新解释器，但 `multiprocessing.spawn` 的 preparation data 里带了 `sys_argv` 和 `sys_path`，
子进程会恢复 —— 已实测确认 `sys.argv[1]` 在 worker 里有效，`lifespan` 能正确读到配置路径。

## 每个 worker 独立初始化
`lifespan` 里 `SEARCH_DATA_INTERFACE` / `MODIFY_KNOWLEDGE_HANDLE` 是模块级全局，每进程一份。
代价：类目字典、ES 客户端各 4 份；`_ensure_index` 每进程每索引各查一次 mapping（一次性）。
模块级没有后台线程、定时任务、文件写入，日志走 stdout 由 nohup 追加重定向，多进程共享 fd 安全。

## 回滚
`SEARCH_SERVICE_WORKERS=1` 重启即可回到单进程，不需要改代码走 git pull。

## SQL
无。
