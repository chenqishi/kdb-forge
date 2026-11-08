from typing import Any
from typing import Dict
from typing import List
import kdb.retrieval.application.runtime as runtime_state
import logging
logger = logging.getLogger('kdb.entrypoints.http.retrieval.app')

async def query_remote_service(text: str, index_names: str, condition_dicts: List[Dict[str, Any]], size: int=10, search_type: str='qa', data_type: str='text', use_synonyms: bool=False) -> Dict:
    logger.info(f"query_remote search params: {text}, {index_names}, {condition_dicts}, {size}, {search_type}, {data_type}, {use_synonyms}")
    raw_result, total_num = runtime_state.SEARCH_DATA_INTERFACE.search_data_by_query(query=text, index_names=index_names, condition_dicts=condition_dicts, size=size, search_type=search_type, data_type=data_type, use_synonyms=use_synonyms)
    if raw_result is None:
        return None, 0
    else:
        return raw_result, total_num


async def web_remote_service(text: str, index_names: str, condition_dicts: List[Dict[str, Any]], client: str = None, page_num: int=1, page_size: int=10000, score_threshold: float=None) -> Dict:
    logger.info(f"query_remote search params: {text}, {index_names}, {condition_dicts}, {page_num}, {page_size}, {score_threshold}")
    raw_result, total_num = runtime_state.SEARCH_DATA_INTERFACE.web_search_data(query=text,client=client, index_names=index_names, condition_dicts=condition_dicts, page_num=page_num, page_size=page_size, score_threshold=score_threshold)
    if raw_result is None:
        return None, 0
    else:
        return raw_result, total_num
