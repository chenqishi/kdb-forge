from fastapi import FastAPI
from kdb.entrypoints.http.retrieval.bootstrap import init_config
from kdb.entrypoints.http.retrieval.bootstrap import lifespan
from kdb.entrypoints.http.retrieval.routes import register_routes
from kdb.retrieval.modification.modify_knowledge import ModifyKnowledge
import kdb.retrieval.application.runtime as runtime_state
import logging
import os
import pathlib
import sys
import traceback
logger = logging.getLogger('kdb.entrypoints.http.retrieval.app')

app = FastAPI(lifespan=lifespan)


"""
Authors: qishichen(263436967@qq.com)
Date: 2024-10-16
"""


logging.basicConfig(
    level=logging.INFO,
    force=True,
    format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)


register_routes(app)


if __name__ == "__main__":

    pathlib.Path("./config").mkdir(exist_ok=True)
    #global SEARCH_DATA_INTERFACE
    config_path = sys.argv[1]
    try:
        runtime_state.SEARCH_DATA_INTERFACE = init_config(config_path)
        runtime_state.MODIFY_KNOWLEDGE_HANDLE = ModifyKnowledge(runtime_state.SEARCH_DATA_INTERFACE)
    except:
        tb = traceback.format_exc()
        logger.error(f"init config error, config_path: {config_path}")
        logger.error(f"traceback: {tb}")
        exit(1)
    import uvicorn
    # 多进程：每个 worker 独立跑一个事件循环，独立初始化 SEARCH_DATA_INTERFACE
    # （uvicorn 用 multiprocessing spawn 拉起 worker，sys.argv 会被 preparation data 带过去，
    #  所以上面的 sys.argv[1] 在子进程里同样有效，已实测确认）。
    #
    # 为什么需要：单进程下所有 handler 都是 async def 包同步阻塞 IO，全部在事件循环上串行，
    # 吞吐恒定 ~0.78 req/s，延迟随并发线性增长（并发8 时 p50 达 10.6s）。
    # 实测 workers=4 后并发4 吞吐 2.5 倍、p50 降 67%。
    #
    # 为什么是 4：机器 8 核；实测需求峰值 1.90 req/s（10 秒窗口）、瞬时最多 3 req/s，
    # 4 个 worker 约 1.5~1.8 req/s 够用且留余量。再往上加受阿里云 ES 服务端并发天花板限制
    # （该查询形态并发 4 时约 1.87 req/s，并发 8 不再增长），加了也吃不到。
    # 内存代价：单进程 342MB → 4 worker 约 1GB。
    #
    # 回滚不需要改代码：SEARCH_SERVICE_WORKERS=1 重启即可。
    workers = int(os.environ.get("SEARCH_SERVICE_WORKERS", "4"))
    logger.info(f"启动 uvicorn，workers={workers}")
    uvicorn.run("kdb.entrypoints.http.retrieval.app:app", host="0.0.0.0", port=8003,
                reload=False, workers=workers) # 提交git时reload记得设为False
