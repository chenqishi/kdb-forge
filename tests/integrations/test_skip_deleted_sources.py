# -*- coding: utf-8 -*-
"""skip_deleted_sources 的离线单测：verdict 判定与拆分，ES 请求打桩。"""

import json

import pytest

from kdb.integrations.data_control import skip_deleted_sources as guard


def _agg(alive, deleted, flags=()):
    buckets = []
    if alive:
        buckets.append({'key': 0, 'doc_count': alive, 'f': {'buckets': []}})
    if deleted:
        buckets.append({'key': 1, 'doc_count': deleted,
                        'f': {'buckets': [{'key': f} for f in flags]}})
    return {'aggregations': {'d': {'buckets': buckets}}}


@pytest.fixture
def es(monkeypatch, tmp_path):
    cfg = tmp_path / 'es.json'
    cfg.write_text(json.dumps({'hosts': ['http://es:9200'], 'username': 'u', 'password': 'p'}),
                   encoding='utf-8')
    table = {}

    class _Resp:
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            pass
        def json(self):
            return self.payload

    def fake_post(url, auth=None, json=None, timeout=None):
        name = json['query']['bool']['filter'][0]['term']['ext_info.from_file_name.keyword']
        return _Resp(table.get(name, _agg(0, 0)))

    monkeypatch.setattr(guard.requests, 'post', fake_post)
    return str(cfg), table


class TestVerdict:
    def test_all_deleted_when_no_alive_left(self, es):
        cfg, table = es
        table['下架.docx'] = _agg(0, 33, flags=['20260730'])
        st = guard.fetch_source_file_status(['下架.docx'], es_config=cfg)
        assert st['下架.docx']['verdict'] == 'all_deleted'
        assert st['下架.docx']['flags'] == ['20260730']

    def test_partial_deleted_is_not_takedown(self, es):
        """入库去重会打掉零星重复条目，不能当成下架。"""
        cfg, table = es
        table['正常.docx'] = _agg(92, 7)
        assert guard.fetch_source_file_status(['正常.docx'], es_config=cfg)['正常.docx']['verdict'] \
            == 'partial_deleted'

    def test_never_indexed(self, es):
        cfg, table = es
        assert guard.fetch_source_file_status(['新的.docx'], es_config=cfg)['新的.docx']['verdict'] \
            == 'never_indexed'

    def test_all_alive(self, es):
        cfg, table = es
        table['干净.docx'] = _agg(20, 0)
        assert guard.fetch_source_file_status(['干净.docx'], es_config=cfg)['干净.docx']['verdict'] == 'ok'


class TestSplit:
    def _write(self, tmp_path, rows):
        p = tmp_path / 'in.txt'
        p.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n',
                     encoding='utf-8')
        return str(p)

    def test_skips_only_taken_down_files(self, es, tmp_path):
        cfg, table = es
        table['下架.docx'] = _agg(0, 33)
        table['正常.docx'] = _agg(92, 7)
        src = self._write(tmp_path, [
            {'ext_info': {'from_file_name': '下架.docx'}, 'content': 'a'},
            {'ext_info': {'from_file_name': '正常.docx'}, 'content': 'b'},
            {'ext_info': {'from_file_name': '正常.docx'}, 'content': 'c'},
        ])
        guard.split_by_source_status(src, es_config=cfg, output_dir=str(tmp_path / 'out'))
        keep = open(src + '.keep', encoding='utf-8').read()
        skip = open(src + '.skipped', encoding='utf-8').read()
        assert '下架.docx' in skip and '下架.docx' not in keep
        assert keep.count('正常.docx') == 2

    def test_reads_segment_style_from_file_name(self, es, tmp_path):
        """segment_knowledge 产物是顶层 from_file_name，不是 ext_info 里的。"""
        cfg, table = es
        table['下架.docx'] = _agg(0, 5)
        src = self._write(tmp_path, [{'from_file_name': '下架.docx', 'content': {}}])
        guard.split_by_source_status(src, es_config=cfg, output_dir=str(tmp_path / 'out'))
        assert '下架.docx' in open(src + '.skipped', encoding='utf-8').read()

    def test_unparsable_line_is_kept_not_dropped(self, es, tmp_path):
        cfg, _ = es
        p = tmp_path / 'in.txt'
        p.write_text('这不是JSON\n', encoding='utf-8')
        guard.split_by_source_status(str(p), es_config=cfg, output_dir=str(tmp_path / 'out'))
        assert open(str(p) + '.keep', encoding='utf-8').read().strip() == '这不是JSON'

    def test_name_field_num_reads_plain_mapping_list(self, es, tmp_path):
        """QA 的映射清单（qa_regen_*.txt）没有逐条 JSON，文件名在第 1 列。"""
        cfg, table = es
        table['下架.docx'] = _agg(0, 5)
        table['正常.docx'] = _agg(9, 0)
        p = tmp_path / 'mapping.txt'
        p.write_text('wayfair\t下架.docx\tdocx\t/a/b.json\n'
                     'wayfair\t正常.docx\tdocx\t/a/c.json\n', encoding='utf-8')
        guard.split_by_source_status(str(p), es_config=cfg, output_dir=str(tmp_path / 'out'),
                                     name_field_num=1)
        keep = open(str(p) + '.keep', encoding='utf-8').read()
        skip = open(str(p) + '.skipped', encoding='utf-8').read()
        assert '下架.docx' in skip and '下架.docx' not in keep
        assert '正常.docx' in keep

    def test_name_field_num_keeps_short_line(self, es, tmp_path):
        """列数不够的行原样保留，不能悄悄丢。"""
        cfg, _ = es
        p = tmp_path / 'mapping.txt'
        p.write_text('只有一列\n', encoding='utf-8')
        guard.split_by_source_status(str(p), es_config=cfg, output_dir=str(tmp_path / 'out'),
                                     name_field_num=1)
        assert open(str(p) + '.keep', encoding='utf-8').read().strip() == '只有一列'
