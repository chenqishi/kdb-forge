"""Leader-only knowledge tools; orchestration remains in sell_agents skill_agent."""
import copy
from itertools import islice
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from kdb.retrieval.ingestion.conflict_jobs import estimate_tokens
from kdb.retrieval.ingestion.conflict_check import compare_candidates
from kdb.retrieval.ingestion.conflict_store import validate_index
from kdb.retrieval.ingestion.document_dedup import check_document, apply_document_matches


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    index: str
    data_type: Literal['qa', 'segment']
    since: Optional[str] = None
    until: Optional[str] = None
    unaudited: bool = False
    task_id: Optional[str] = None
    only_unchecked: bool = True
    max_records: int = Field(default=50, ge=1, le=500)


class RunArguments(Selection):
    policy: Literal['record_only', 'keep_new', 'keep_old'] = 'record_only'
    dry_run: bool = True
    ids: Optional[list[str]] = Field(default=None, min_length=1, max_length=500)
    threshold: Optional[float] = Field(default=None, ge=0, le=1)
    min_shared_topics: Optional[int] = Field(default=None, ge=0, le=2)


class RecallArguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    index: str
    data_type: Literal['qa', 'segment']
    id: Optional[str] = None
    query: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    limit: int = Field(default=60, ge=1, le=60)


class FastArguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    index: str
    data_type: Literal['qa', 'segment']
    title: str = Field(default='', max_length=4000)
    content: str = Field(min_length=1, max_length=20000)
    is_need_llm: bool = False


class CompareArguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    index: str
    data_type: Literal['qa', 'segment']
    id: str
    candidate_ids: list[str] = Field(min_length=1, max_length=60)
    threshold: float = Field(default=0, ge=0, le=1)
    min_shared_topics: int = Field(default=0, ge=0, le=2)
    policy: Literal['record_only', 'keep_new', 'keep_old'] = 'record_only'
    dry_run: bool = True


class DocumentArguments(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    index: str
    name: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=100000)
    seed: int = 0
    name_check: bool = True
    content_check: bool = True
    policy: Literal['record_only', 'skip_new', 'replace_old'] = 'record_only'
    dry_run: bool = True


TOOL_MODELS = {
    'knowledge_dedup_select': (Selection, '按index、类型、时间、未审核和未检查状态选取增量，返回token估算。'),
    'knowledge_dedup_recall': (RecallArguments, '只读召回同类型候选，可改写query进行下一轮召回。'),
    'knowledge_dedup_run': (RunArguments, 'Top60重排及LLM判重/冲突；dry_run默认true；按显式policy处理并返回证据和token。'),
    'knowledge_dedup_fast': (FastArguments, '快速少量候选查重，复用在线规则，不写入。'),
    'knowledge_dedup_compare': (CompareArguments, '精查额外召回得到的候选ID，支持Agent多轮查找；默认只预览。'),
    'knowledge_dedup_document': (DocumentArguments, '文档主体名或450字segment覆盖检测；replace_old会软删匹配的旧文档知识。'),
}


def compact_record(record):
    return {key: copy.deepcopy(record[key]) for key in ('_id', 'title', 'content', 'data_type',
        'insert_time', 'audit_result', 'dedup_check', 'ext_info') if key in record}


def collect(job, args):
    iterator = job.store.scan(args.data_type, since=args.since, until=args.until,
        unaudited=args.unaudited, task_id=args.task_id, only_unchecked=args.only_unchecked)
    try:
        rows = list(islice(iterator, args.max_records + 1))
    finally:
        if hasattr(iterator, 'close'):
            iterator.close()
    return rows[:args.max_records], len(rows) > args.max_records


class DedupHarness:
    def __init__(self, config, job_factory):
        self.config, self.job_factory = config, job_factory

    def authorize(self, principal, index=None, mutation=False):
        if self.config.get('enabled', False) is not True:
            raise PermissionError('knowledge dedup tools are disabled')
        if principal.get('is_admin') is not True or principal.get('role') != 'leader':
            raise PermissionError('admin leader access required')
        if index is not None and validate_index(index) not in principal.get('indices', []):
            raise PermissionError('index is not authorized')
        if mutation and principal.get('allow_mutations', False) is not True:
            raise PermissionError('this principal has no write permission')

    def list_tools(self, principal):
        self.authorize(principal)
        return [{'name': name, 'description': description, 'inputSchema': model.model_json_schema()}
                for name, (model, description) in TOOL_MODELS.items()]

    def call(self, name, arguments, principal):
        self.authorize(principal)
        if name not in TOOL_MODELS:
            raise ValueError('unknown knowledge tool')
        args = TOOL_MODELS[name][0].model_validate(arguments)
        mutation = (name in {'knowledge_dedup_run', 'knowledge_dedup_compare'} and not args.dry_run) or (
            name == 'knowledge_dedup_document' and args.policy == 'replace_old' and not args.dry_run)
        self.authorize(principal, args.index, mutation)
        job = self.job_factory(args.index)
        if name == 'knowledge_dedup_select':
            rows, truncated = collect(job, args)
            estimates = [estimate_tokens(r, job.limit) for r in rows]
            return {'index': args.index, 'records': [compact_record(r) for r in rows],
                    'selection_truncated': truncated, 'estimate': {'estimated': True,
                    'input_tokens': sum(e['input_tokens'] for e in estimates),
                    'output_tokens': sum(e['output_tokens'] for e in estimates)}}
        if name == 'knowledge_dedup_fast':
            rows = job.store.interface.find_duplicates({'title': args.title, 'content': args.content,
                'data_type': args.data_type}, index_name=args.index, topK=5, is_need_llm=args.is_need_llm, exclude_self=True)
            return {'duplicates': [compact_record(r) for r in rows]}
        if name == 'knowledge_dedup_recall':
            current = job.store.read(args.id) if args.id else {'data_type': args.data_type}
            if not current or current['data_type'] != args.data_type or current.get('del_flag', 0) != 0:
                raise ValueError('knowledge not found in the selected type')
            if args.query:
                current = {**current, 'title': '', 'content': args.query}
            if not args.id and not args.query:
                raise ValueError('id or query is required')
            return {'candidates': [compact_record(r) for r in job.store.recall(current, args.limit)]}
        if name == 'knowledge_dedup_document':
            report = check_document(job.store, job.models, args.name, args.text, seed=args.seed,
                name_check=args.name_check, content_check=args.content_check)
            report['actions'] = apply_document_matches(job.store, report, 'record_only' if args.dry_run else args.policy)
            for match in report['matches']:
                match['record_ids'] = [r['_id'] for r in match.pop('records')]
            return report
        if name == 'knowledge_dedup_compare':
            current = job.store.read(args.id)
            candidates = [job.store.read(identifier) for identifier in dict.fromkeys(args.candidate_ids)]
            if any(not r or r.get('data_type') != args.data_type or r.get('del_flag', 0) != 0 for r in [current] + candidates):
                raise ValueError('comparison requires existing, undeleted knowledge of the selected type')
            result = compare_candidates(current, candidates, job.models.rerank, job.models.judge,
                                        args.threshold, args.min_shared_topics, job.aliases)
            result.update({'current': current, 'candidates': candidates, 'index': args.index, 'scope': 'explicit_candidates'})
            result = job.apply(result, args.policy, dry_run=args.dry_run)
            result['current'] = compact_record(result['current'])
            result.pop('candidates')
            result['usage'] = job.models.usage
            return result
        if args.threshold is not None:
            job.threshold = args.threshold
        if args.min_shared_topics is not None:
            job.min_shared_topics = args.min_shared_topics
        truncated = False
        if args.ids:
            rows = [job.store.read(identifier) for identifier in args.ids]
            if any(not row or row.get('data_type') != args.data_type or row.get('del_flag', 0) != 0 for row in rows):
                raise ValueError('selected IDs must exist in the requested knowledge type')
        else:
            rows, truncated = collect(job, args)
        report = job.run(iter(rows), policy=args.policy, dry_run=args.dry_run, max_records=args.max_records)
        report['selection_truncated'] |= truncated
        report.pop('offline_records', None)
        for result in report['results']:
            result['current'] = compact_record(result['current'])
            result.pop('candidates', None)
        return report
