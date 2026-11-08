#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
ES / OpenSearch 裸 HTTP 只读客户端（外加 _bulk 局部更新）。

为什么不用 knowledge_interface_tools.es_search_interface.EsSearchInterface：

1. `EsSearchInterface.__init__` 会 `_ensure_index`，即**建索引 / 改 mapping**，
   对只读的导出、盘点、重打标场景是副作用，不能碰生产索引。
2. 阿里云 ES Serverless 不支持 scroll（返回 serverless_unsupported_exception），
   只能走 search_after；见 backup_es_data._backup_with_search_after。

原先这个类写在 data_control_tools/relabel_qa_quality_by_llm.py 里，
data_control_tools/export_qa_to_excel.py 也要用，且那个文件顶层 import 了
chat_qa_extract / quality_tools 等重依赖，所以抽到 commons 下共用。
"""

import json
import logging
import time
from typing import Any
from typing import Dict
from typing import Iterator
from typing import List
from typing import Optional
from typing import Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 阿里云 ES Serverless 单请求写入上限 15MB；partial update 很小，200 条远低于上限，
# 但仍保留 413 折半重试，避免换索引/换集群时静默失败
DEFAULT_BULK_BATCH = 200

# 阿里云 ES Serverless 会把跑得慢的分片任务直接取消（task_cancelled_exception），
# 此时 HTTP 仍是 200，只是 `_shards.failed > 0` 且 hits 少了一整个分片的量。
# search_after 的游标又只认最后一条 hit，被取消那个分片在这一段的文档就**永久跳过**，
# 表现为「跑完没报错，但导出比 _count 少几千条」（mercado_local 实测 10007 -> 6675，
# 且每次跑少的条数都不一样）。所以这里必须查 _shards 并重试整页。
SHARD_RETRY_TIMES = 4
SHARD_RETRY_BACKOFF = 2.0
# 重试仍被取消时把页大小折半，降到这个下限还失败就抛错，不要静默少捞
MIN_PAGE_SIZE = 50


class PartialShardFailure(RuntimeError):
    """部分分片失败/超时：ES 返回 200 但结果不全，绝不能当成功用。"""


def shard_failure_reason(payload: Dict[str, Any]) -> Optional[str]:
    """
    返回「这次响应结果不全」的原因；结果完整则返回 None。

    判据：`timed_out=true`（部分分片超时，返回的是已有结果），
    或 `_shards.failed > 0` / `successful < total`。
    """
    if payload.get('timed_out'):
        return 'timed_out=true'
    shards = payload.get('_shards') or {}
    failed = int(shards.get('failed') or 0)
    total = int(shards.get('total') or 0)
    successful = int(shards.get('successful') or 0)
    if failed > 0 or (total and successful < total):
        failures = json.dumps(shards.get('failures') or [], ensure_ascii=False)[:500]
        return f'shards total={total} successful={successful} failed={failed} failures={failures}'
    return None


class EsHttpClient(object):
    """search_after 分页、_count、terms 聚合、_bulk 局部更新。"""

    def __init__(self, hosts: List[str], username: Optional[str] = None,
                 password: Optional[str] = None, timeout: int = 60):
        if not hosts:
            raise ValueError('ES hosts 为空')
        self.base_url = hosts[0].rstrip('/')
        self.auth = (username, password) if username and password else None
        self.timeout = timeout
        self.session = requests.Session()
        # 长任务（几千次请求）里偶发连接超时是常态，没有重试会让整轮白跑。
        # 只对连接级错误和 5xx 重试，业务级 4xx 仍然立即抛出。
        retry = Retry(total=5, connect=5, read=3, backoff_factor=1.5,
                      status_forcelist=(502, 503, 504),
                      allowed_methods=frozenset(['GET', 'POST']))
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=20)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    @classmethod
    def from_config(cls, config_path: str, timeout: int = 60) -> 'EsHttpClient':
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        return cls(hosts=cfg.get('hosts') or [],
                   username=cfg.get('username'),
                   password=cfg.get('password'),
                   timeout=timeout)

    def _request(self, method: str, path: str, body: Any = None,
                 raw_body: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
        url = f'{self.base_url}{path}'
        headers = {'Content-Type': 'application/json'}
        data = raw_body.encode('utf-8') if raw_body is not None else (
            json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None)
        if raw_body is not None:
            headers['Content-Type'] = 'application/x-ndjson'
        resp = self.session.request(method, url, data=data, headers=headers,
                                    auth=self.auth, timeout=self.timeout)
        try:
            payload = resp.json()
        except ValueError:
            payload = {'raw': resp.text}
        return resp.status_code, payload

    def search(self, index: str, body: Dict[str, Any],
               allow_partial: bool = False,
               retries: int = SHARD_RETRY_TIMES) -> Dict[str, Any]:
        """
        _search。默认**不接受部分分片失败**：命中 `_shards.failed>0` / `timed_out`
        就重试整页，重试用尽抛 PartialShardFailure。
        allow_partial=True 只给「少几条也无所谓」的场景。
        """
        reason = None
        for attempt in range(retries + 1):
            status, payload = self._request('POST', f'/{index}/_search', body)
            if status != 200:
                raise RuntimeError(f'ES search 失败 status={status} payload={payload}')
            reason = shard_failure_reason(payload)
            if reason is None or allow_partial:
                return payload
            logging.warning('%s search 结果不全(第%d次): %s', index, attempt + 1, reason)
            if attempt < retries:
                time.sleep(SHARD_RETRY_BACKOFF * (attempt + 1))
        raise PartialShardFailure(f'{index} search 结果不全且重试用尽: {reason}')

    def count(self, index: str, query: Dict[str, Any],
              retries: int = SHARD_RETRY_TIMES) -> int:
        """_count。同样要查 _shards——分片被取消时 count 会偏小，用它对账就白对了。"""
        reason = None
        for attempt in range(retries + 1):
            status, payload = self._request('POST', f'/{index}/_count', {'query': query})
            if status != 200:
                raise RuntimeError(f'ES count 失败 status={status} payload={payload}')
            reason = shard_failure_reason(payload)
            if reason is None:
                return int(payload.get('count', 0))
            logging.warning('%s count 结果不全(第%d次): %s', index, attempt + 1, reason)
            if attempt < retries:
                time.sleep(SHARD_RETRY_BACKOFF * (attempt + 1))
        raise PartialShardFailure(f'{index} count 结果不全且重试用尽: {reason}')

    def iter_search_after(self, index: str, query: Dict[str, Any],
                          source_fields: List[str], page_size: int = 1000,
                          limit: Optional[int] = None) -> Iterator[Tuple[str, Dict[str, Any]]]:
        """
        search_after 分页遍历，yield (_id, _source)。

        用 search_after 而不是 scroll：阿里云 ES Serverless 对 scroll 返回
        serverless_unsupported_exception（见 backup_es_data._backup_with_search_after）。
        """
        search_after = None
        yielded = 0
        cur_page_size = page_size
        while True:
            size = cur_page_size if limit is None else min(cur_page_size, limit - yielded)
            if size <= 0:
                return
            body = {
                'query': query,
                'size': size,
                '_source': source_fields,
                'sort': [{'_id': {'order': 'asc'}}],
            }
            if search_after:
                body['search_after'] = search_after
            try:
                hits = self.search(index, body)['hits']['hits']
            except PartialShardFailure:
                # 重试还被取消，多半是这一页太重；折半再来，游标不动所以不会跳过文档
                if size <= MIN_PAGE_SIZE:
                    raise
                cur_page_size = max(MIN_PAGE_SIZE, size // 2)
                logging.warning('%s 分片持续被取消，页大小 %d -> %d 重试',
                                index, size, cur_page_size)
                continue
            if not hits:
                return
            for hit in hits:
                yield hit['_id'], (hit.get('_source') or {})
                yielded += 1
            search_after = hits[-1]['sort']

    def terms_agg(self, index: str, query: Dict[str, Any], field: str) -> Dict[str, int]:
        body = {'size': 0, 'query': query,
                'aggs': {'agg': {'terms': {'field': field, 'size': 50}}}}
        buckets = self.search(index, body)['aggregations']['agg']['buckets']
        return {b['key']: b['doc_count'] for b in buckets}

    def bulk_update_doc(self, index: str, updates: List[Tuple[str, Dict[str, Any]]],
                        batch_size: int = DEFAULT_BULK_BATCH) -> Dict[str, Any]:
        """
        多字段 partial update。updates: [(_id, {field: value, ...}), ...]

        bulk_update_field 只能写一个字段，软删要同时写 del_flag 和 flag，故有此方法。

        Returns: {'updated': n, 'failed': [{'_id':..., 'error':...}]}
        """
        updated = 0
        failures: List[Dict[str, Any]] = []
        start = 0
        while start < len(updates):
            batch = updates[start:start + batch_size]
            lines = []
            for doc_id, doc in batch:
                lines.append(json.dumps({'update': {'_index': index, '_id': doc_id}},
                                        ensure_ascii=False))
                lines.append(json.dumps({'doc': doc}, ensure_ascii=False))
            status, payload = self._request('POST', '/_bulk', raw_body='\n'.join(lines) + '\n')

            if status == 413 and batch_size > 10:
                batch_size = max(10, batch_size // 2)
                logging.warning('bulk 触发 413，batch_size 降为 %d 重试', batch_size)
                continue
            if status != 200:
                raise RuntimeError(f'ES bulk 失败 status={status} payload={payload}')

            # Serverless 返回 200 不代表成功，错误藏在 items 里，必须逐条查
            for item in payload.get('items', []):
                res = item.get('update', {})
                if res.get('error'):
                    failures.append({'_id': res.get('_id'), 'error': res['error']})
                else:
                    updated += 1
            start += len(batch)
            logging.info('bulk 进度 %d/%d，成功 %d，失败 %d',
                         start, len(updates), updated, len(failures))
        return {'updated': updated, 'failed': failures}

    def bulk_update_field(self, index: str, updates: List[Tuple[str, str]], field: str,
                          batch_size: int = DEFAULT_BULK_BATCH) -> Dict[str, Any]:
        """
        updates: [(_id, new_value), ...]，只更新 field 一个字段。

        Returns: {'updated': n, 'failed': [{'_id':..., 'error':...}]}
        """
        updated = 0
        failures: List[Dict[str, Any]] = []
        start = 0
        while start < len(updates):
            batch = updates[start:start + batch_size]
            lines = []
            for doc_id, value in batch:
                lines.append(json.dumps({'update': {'_index': index, '_id': doc_id}},
                                        ensure_ascii=False))
                lines.append(json.dumps({'doc': {field: value}}, ensure_ascii=False))
            status, payload = self._request('POST', '/_bulk', raw_body='\n'.join(lines) + '\n')

            if status == 413 and batch_size > 10:
                batch_size = max(10, batch_size // 2)
                logging.warning('bulk 触发 413，batch_size 降为 %d 重试', batch_size)
                continue
            if status != 200:
                raise RuntimeError(f'ES bulk 失败 status={status} payload={payload}')

            for item in payload.get('items', []):
                res = item.get('update', {})
                if res.get('error'):
                    failures.append({'_id': res.get('_id'), 'error': res['error']})
                else:
                    updated += 1
            start += len(batch)
            logging.info('bulk 进度 %d/%d，成功 %d，失败 %d',
                         start, len(updates), updated, len(failures))
        return {'updated': updated, 'failed': failures}
