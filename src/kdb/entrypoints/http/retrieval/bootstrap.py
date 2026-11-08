from contextlib import asynccontextmanager
from fastapi import FastAPI
from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
from kdb.retrieval.modification.modify_knowledge import ModifyKnowledge
import json
import kdb.retrieval.application.runtime as runtime_state
import logging
import sys
import traceback
logger = logging.getLogger('kdb.entrypoints.http.retrieval.app')

def init_config(config_path: str = "./config/config_for_search_index.json") -> dict:
    try:
        search_data_interface = SearchDataInterface(config_path=config_path)
        return search_data_interface
    except FileNotFoundError:
        logger.error(f"配置文件 {config_path} 不存在")
        raise
    except json.JSONDecodeError:
        logger.error(f"配置文件 {config_path} 格式错误")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行

    if runtime_state.SEARCH_DATA_INTERFACE is None:
        config_path = "./config/config_for_search_index.json"
        if len(sys.argv) > 1:
            config_path = sys.argv[1]
        try:
            runtime_state.SEARCH_DATA_INTERFACE = init_config(config_path)
            runtime_state.MODIFY_KNOWLEDGE_HANDLE = ModifyKnowledge(runtime_state.SEARCH_DATA_INTERFACE)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"init config error, config_path: {config_path}")
            logger.error(f"traceback: {tb}")
            raise e
    yield
    # 关闭时执行
    pass
