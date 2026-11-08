from kdb.mining.bridges.defaults import DEFAULT_CONDITION_DICTS
from kdb.mining.bridges.defaults import DEFAULT_SEARCH_CONFIG
from kdb.mining.bridges.defaults import PROJECT_ROOT
from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence
import copy
import logging
import os

def build_search_interface(search_config_path: str = DEFAULT_SEARCH_CONFIG):
    """初始化线上同款检索接口。"""
    from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
    return SearchDataInterface(config_path=search_config_path)


def search_knowledge(
    sdi,
    query_variants: Sequence[str],
    index_names: str = 'wayfair',
    condition_dicts: Optional[List[dict]] = None,
    top_k: int = 5,
) -> List[dict]:
    """多路检索并按 _id 合并去重，保留各路最高分。"""
    if condition_dicts is None:
        condition_dicts = DEFAULT_CONDITION_DICTS
    # search_data_by_query 会就地给条件补 audit_result（:741），传共享常量进去等于
    # 跨线程改同一个 dict。这里深拷贝一份，隔离调用方的对象。
    condition_dicts = copy.deepcopy(condition_dicts)
    merged: Dict[str, dict] = {}
    for variant in query_variants:
        try:
            docs, _total = sdi.search_data_by_query(
                variant, index_names=index_names,
                condition_dicts=condition_dicts, size=top_k)
        except Exception as exc:  # noqa: BLE001
            logging.warning('检索失败 query=%r err=%s', variant, exc)
            continue
        for doc in docs or []:
            doc_id = str(doc.get('_id') or doc.get('title'))
            score = float(doc.get('similarity') or 0.0)
            existing = merged.get(doc_id)
            if existing is None:
                merged[doc_id] = {
                    '_id': doc_id,
                    'title': doc.get('title') or '',
                    'content': doc.get('content') or '',
                    'similarity': score,
                    'hit_by': [variant],
                }
            else:
                existing['similarity'] = max(existing['similarity'], score)
                if variant not in existing['hit_by']:
                    existing['hit_by'].append(variant)
    return sorted(merged.values(), key=lambda d: d['similarity'], reverse=True)
