import json
from types import SimpleNamespace
from kdb.entrypoints.cli import knowledge_dedup as cli
from kdb.retrieval.ingestion.conflict_jobs import DedupJob
from .test_conflict_jobs import Store, Models, row


def test_cli_offline_output_and_real_failure_exit(tmp_path, monkeypatch):
    source = tmp_path / 'new.jsonl'
    source.write_text(json.dumps(row('new', 2)) + '\n')
    output = tmp_path / 'report.jsonl'
    store = Store([row('old')])
    monkeypatch.setattr(cli, 'build_job', lambda *a, **kw: DedupJob(store, Models()))
    args = ['knowledge', '--index', 'kb', '--data-type', 'qa', '--input', str(source), '--output', str(output)]
    assert cli.main(args) == 0
    exported = json.loads((tmp_path / 'report.jsonl.knowledge.jsonl').read_text())
    assert exported['similarity_info'][0]['relation'] == 'duplicate'
    assert store.changes == []
    def failed(*args):
        raise RuntimeError('model unavailable')
    models = Models()
    models.rerank = failed
    monkeypatch.setattr(cli, 'build_job', lambda *a, **kw: DedupJob(store, models))
    assert cli.main(args) == 2
    assert json.loads(output.read_text())['status'] == 'failed'


def test_cli_estimate_does_not_call_models(tmp_path, monkeypatch):
    source = tmp_path / 'new.jsonl'
    source.write_text(json.dumps(row('new')) + '\n')
    monkeypatch.setattr(cli, 'build_job', lambda *a, **kw: SimpleNamespace(limit=60))
    output = tmp_path / 'cost.json'
    assert cli.main(['knowledge', '--index', 'kb', '--data-type', 'qa', '--input', str(source),
                     '--output', str(output), '--estimate-only']) == 0
    assert json.loads(output.read_text())['estimated'] is True


def test_cli_never_overwrites_input_with_generated_sidecar(tmp_path, monkeypatch):
    import pytest
    output = tmp_path / 'result.jsonl'
    source = tmp_path / 'result.jsonl.knowledge.jsonl'
    source.write_text('original data')
    monkeypatch.setattr(cli, 'build_job', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('must validate before init')))
    with pytest.raises(SystemExit):
        cli.main(['knowledge', '--index', 'kb', '--data-type', 'qa', '--input', str(source), '--output', str(output)])
    assert source.read_text() == 'original data'
