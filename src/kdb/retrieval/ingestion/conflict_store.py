"""Index-scoped storage boundary for deduplication jobs (Elasticsearch 8.17)."""
import copy
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from elasticsearch import NotFoundError


def validate_index(index):
    if not isinstance(index, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*', index):
        raise ValueError('one explicit index is required; wildcards and index lists are forbidden')
    return index


def fingerprint(record):
    fields = {key: record.get(key) for key in ('data_type', 'title', 'content', 'keywords', 'ext_info', 'task_id')}
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class KnowledgeStore:
    def __init__(self, interface, index, journal=None):
        self.interface = interface
        self.index = validate_index(index)
        self.journal = Path(journal) if journal else None

    def scan(self, kind, *, since=None, until=None, unaudited=False, task_id=None, only_unchecked=True):
        if kind not in {'qa', 'segment'}:
            raise ValueError('data_type must be qa or segment')
        query = {'attribute': {'data_type': kind, 'del_flag': 0}}
        if unaudited:
            query['attribute']['audit_result'] = -1
        if task_id:
            query['attribute']['task_id'] = task_id
        if since or until:
            query['insert_time'] = [since, until]
        rows = self.interface.engine.scroll_search(query, index_names=self.index, batch_size=200)
        try:
            for row in rows:
                if row.get('data_type') != kind or row.get('del_flag', 0) != 0:
                    raise ValueError('scan returned an out-of-scope record')
                previous = row.get('dedup_check') or {}
                if only_unchecked and previous.get('status') == 'complete' and previous.get('fingerprint') == fingerprint(row):
                    continue
                yield row
        finally:
            if hasattr(rows, 'close'):
                rows.close()

    def recall(self, record, limit=60):
        kind = record.get('data_type')
        if kind not in {'qa', 'segment'}:
            raise ValueError('data_type must be qa or segment')
        query = {'query': str(record.get('title') or '') + '\n' + str(record.get('content') or ''),
                 'attribute': {'data_type': kind, 'del_flag': 0}}
        vector = self.interface.embedding_tools.text2embedding(query['query'])
        if vector is None:
            raise RuntimeError('embedding unavailable for candidate recall')
        query['vector'] = {'value': vector.tolist() if hasattr(vector, 'tolist') else list(vector)}
        rows = self.interface.search_data(query, size=limit + 1, index_names=self.index)
        eligible = []
        for row in rows:
            if row.get('data_type') != kind or row.get('_index', self.index) != self.index:
                raise ValueError('recall returned an out-of-scope candidate')
            if row.get('_id') != record.get('_id') and row.get('del_flag', 0) == 0:
                eligible.append(row)
        return eligible[:limit]

    def read(self, identifier):
        client = self.interface.engine.get_client_by_index(self.index)
        try:
            raw = client.get(index=self.index, id=str(identifier))
        except NotFoundError:
            return None
        return {**raw['_source'], '_id': raw['_id'], '_seq_no': raw['_seq_no'],
                '_primary_term': raw['_primary_term']}

    def patch(self, expected, fields):
        identifier = expected['_id']
        fresh = self.read(identifier)
        if (not fresh or fresh.get('del_flag', 0) != 0 or fingerprint(fresh) != fingerprint(expected)
                or fresh.get('audit_result') != expected.get('audit_result')):
            raise RuntimeError('knowledge changed since comparison; rerun required: ' + str(identifier))
        destructive = any(key in fields for key in ('title', 'content', 'del_flag'))
        if destructive and not self.journal:
            raise ValueError('a journal path is required for content changes')
        if self.journal:
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            with self.journal.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(), 'index': self.index,
                    'id': identifier, 'before': fresh, 'patch': fields}, ensure_ascii=False) + '\n')
                handle.flush()
                os.fsync(handle.fileno())
        client = self.interface.engine.get_client_by_index(self.index)
        result = client.update(index=self.index, id=identifier, doc=fields,
            if_seq_no=fresh['_seq_no'], if_primary_term=fresh['_primary_term'], refresh='wait_for')
        if result.get('result') not in {'updated', 'noop'}:
            raise RuntimeError('ES did not confirm the update')
        return {**fresh, **fields}

    def insert(self, record):
        data = copy.deepcopy(record)
        for key in ('_offline', '_id', '_seq_no', '_primary_term', '_index', 'score', 'dedup_action', 'dedup_plan'):
            data.pop(key, None)
        if not self.interface.process_one_data(data, index_name=self.index):
            raise RuntimeError('knowledge preparation failed')
        if not self.interface.engine.insert(data, index_names=self.index, refresh_imm=True):
            raise RuntimeError('new knowledge insertion failed; old records were preserved')
        return data

    def file_names(self):
        query = {'attribute': {'from_type_norm': ['document', 'html', 'manual'], 'del_flag': 0}}
        names = set()
        for row in self.interface.engine.scroll_search(query, batch_size=200, index_names=self.index):
            name = (row.get('ext_info') or {}).get('from_file_name')
            if name:
                names.add(name)
        return sorted(names)

    def file_records(self, name):
        if not name or len(name) > 256:
            raise ValueError('file name cannot be matched by keyword (empty or over 256 characters)')
        query = {'attribute': {'ext_info.from_file_name.keyword': name,
                 'from_type_norm': ['document', 'html', 'manual'], 'data_type': ['qa', 'segment'], 'del_flag': 0}}
        return list(self.interface.engine.scroll_search(query, batch_size=200, index_names=self.index))
