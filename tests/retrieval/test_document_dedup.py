from types import SimpleNamespace
import json
import pytest
from kdb.retrieval.ingestion.document_dedup import coverage, check_document, apply_document_matches, parsed_text
from kdb.mining.document.workflows import deduplication as workflow


def segment(identifier, text, name):
    return {'_id': identifier, 'data_type': 'segment', 'content': text, 'ext_info': {'from_file_name': name}}


def test_coverage_threshold_union_and_no_cross_document_accumulation():
    sample = ''.join(chr(0x4e00 + i) for i in range(450))
    segments = [segment('a', sample[:180], 'a'), segment('b', sample[180:315], 'a'),
                segment('c', sample[315:], 'b')]
    assert coverage(sample, segments[:2])['coverage'] == .7
    assert coverage(sample, [segments[0], segments[0]])['coverage'] == .4
    store = SimpleNamespace(index='kb', recall=lambda r, n: segments, file_records=lambda name: [s for s in segments if s['ext_info']['from_file_name'] == name])
    result = check_document(store, SimpleNamespace(usage={}), 'new', sample, name_check=False)
    assert [r['from_file_name'] for r in result['matches']] == ['a']
    assert result['matches'][0]['coverage'] == .7


def test_name_or_content_and_qa_forbidden():
    store = SimpleNamespace(index='kb', file_names=lambda: ['退款说明v1'], file_records=lambda n: [], recall=lambda r, n: [])
    models = SimpleNamespace(usage={}, names=lambda a, b: {'same_document': True, 'reason': '同主体新版本'})
    result = check_document(store, models, '退款说明v2', '解析文本内容')
    assert result['matches'][0]['by_name']
    assert apply_document_matches(store, result, 'skip_new')['skip_new']
    store.recall = lambda *a: [{'data_type': 'qa'}]
    with pytest.raises(ValueError, match='segments'):
        check_document(store, models, 'new', '解析文本内容', name_check=False)


def test_parser_and_optional_workflow_skip(tmp_path, monkeypatch):
    parsed = {'1': [{'type': 'text', 'text_content': '文本内容'}, {'type': 'image', 'image_path': '/secret'}]}
    assert parsed_text(parsed) == '文本内容\n'
    document = tmp_path / 'content.json'
    document.write_text(json.dumps(parsed))
    mapping = tmp_path / 'mapping.txt'
    mapping.write_text(f'c\t文档\ttxt\tsource.txt\t{tmp_path}\t{document}\n')
    c = SimpleNamespace(task_info={'document_dedup': {'enabled': True, 'policy': 'skip_new'}}, index_name='kb', data_dir=str(tmp_path), content_mapping_path=str(mapping))
    monkeypatch.setattr(workflow, 'build_dedup_job', lambda *a, **kw: object())
    monkeypatch.setattr(workflow, 'check_document_duplicate', lambda *a, **kw: {'matches': [{'from_file_name': 'old'}]})
    assert workflow.prepare_document_dedup(c)
    assert c._dedup_all_skipped
    assert open(c.content_mapping_path).read() == ''
    assert mapping.read_text()  # original parsed mapping preserved


def test_replace_defers_delete_and_checks_new_insert_count(tmp_path, monkeypatch):
    path = tmp_path / 'new.jsonl'
    path.write_text(json.dumps({'data_type': 'qa', 'ext_info': {'from_file_name': 'new'}}) + '\n')
    store = SimpleNamespace(scan=lambda *a, **kw: [])
    c = SimpleNamespace(data_dir=str(tmp_path), task_id='task', search_data_file_path=str(path),
        _document_dedup={'policy': 'replace_old', 'job': SimpleNamespace(store=store),
                        'reports': [{'from_file_name': 'new', 'matches': [{'records': [{'_id': 'old'}]}]}]})
    calls = []
    monkeypatch.setattr(workflow, 'apply_document_duplicates', lambda *a: calls.append(a) or {'deleted': ['old']})
    with pytest.raises(RuntimeError, match='incomplete'):
        workflow.finish_document_dedup(c)
    assert calls == []
    store.scan = lambda kind, **kw: [{'_id': 'new-id', 'data_type': 'qa', 'ext_info': {'from_file_name': 'new'}}] if kind == 'qa' else []
    assert workflow.finish_document_dedup(c)
    assert len(calls) == 1
