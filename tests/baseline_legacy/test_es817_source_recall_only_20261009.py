"""Ensure the same-ES8 recall comparator detects changes instead of passing by hit count."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_es817_source_recall_only_20261009.py')
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def load_comparator():
    path=Path(__legacy_source_file__).with_name('es817_source_recall_only_20261009.py')
    spec=importlib.util.spec_from_file_location('_source_recall_harness_offline',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    parsed=ast.parse(module.REMOTE)
    selected=[node for node in parsed.body if isinstance(node,ast.FunctionDef) and node.name in {'sha','normalize_request','compare_recall'}]
    namespace={'copy':copy,'hashlib':hashlib,'json':json}
    exec(compile(ast.Module(body=selected,type_ignores=[]),'<actual-harness-functions-only>','exec'),namespace)
    return namespace


def test_projection_normalization_preserves_query_controls():
    normalize=load_comparator()['normalize_request']
    body={'_source':{'excludes':['indexes.embedding']},'size':40,'sort':[{'rank':'desc'}],
        'query':{'bool':{'filter':[{'term':{'_source':'business_field'}}],
            'must':[{'nested':{'path':'indexes','query':{'knn':{'field':'indexes.embedding','k':40,'num_candidates':400}},
                'inner_hits':{'name':'best_index','size':3,'_source':{'includes':['indexes.embedding']}}}}]}}}
    original=copy.deepcopy(body);expected=copy.deepcopy(body)
    expected.pop('_source');expected['query']['bool']['must'][0]['nested']['inner_hits'].pop('_source')
    assert normalize(body)==expected
    assert body==original
    changed=copy.deepcopy(body);changed['query']['bool']['must'][0]['nested']['query']['knn']['k']=10
    assert normalize(changed)!=expected


@pytest.mark.parametrize('change',['id','index','order','score','total','query','raw_ids','raw_score','raw_total'])
def test_recall_comparison_rejects_changed_candidates(change):
    compare=load_comparator()['compare_recall']
    docs=[{'_index':'a','_id':'1','score':.9},{'_index':'a','_id':'2','score':.8}]
    altered=copy.deepcopy(docs);stats={'total':2};altered_stats=copy.deepcopy(stats)
    route={'index':'a','query_and_options_sha256':'q','ordered_ids_sha256':'ids','scores_sha256':'scores','total':{'value':2,'relation':'eq'}}
    changed_route=copy.deepcopy(route)
    if change=='id':altered[0]['_id']='3'
    elif change=='index':altered[0]['_index']='b'
    elif change=='order':altered.reverse()
    elif change=='score':altered[0]['score']=.1
    elif change=='total':altered_stats['total']=3
    elif change=='query':changed_route['query_and_options_sha256']='changed_budget'
    elif change=='raw_ids':changed_route['ordered_ids_sha256']='different_ids'
    elif change=='raw_score':changed_route['scores_sha256']='different_scores'
    elif change=='raw_total':changed_route['total']['relation']='gte'
    result=compare(stats,altered_stats,{'engine_docs':docs},{'engine_docs':altered},[route],[changed_route])
    assert not result['recall_passed']


def test_recall_comparison_checks_vector_preservation():
    compare=load_comparator()['compare_recall']
    doc={'_index':'a','_id':'1','score':.9,'title_embedding':[1.,2.],'audit_result':1,
        'indexes':[{'text':'one','embedding':[1.,2.]},{'text':'two','embedding':[2.,1.]}],
        'image_indexes':[{'text':'image','embedding':[3.,1.]}]}
    lean=copy.deepcopy(doc);lean['indexes'][1].pop('embedding');lean['image_indexes'][0].pop('embedding')
    route={'index':'a','query_and_options_sha256':'q','ordered_ids_sha256':'ids','scores_sha256':'scores','total':{'value':1,'relation':'eq'}}
    arguments=({'total':1},{'total':1},{'engine_docs':[doc]},{'engine_docs':[lean]},[route],[route])
    result=compare(*arguments)
    assert result['recall_passed'] and result['other_source_and_root_vectors_equal'] and result['returned_nested_vectors_match_full_source']
    lean['indexes'][0]['embedding']=[9.,9.]
    assert not compare(*arguments)['returned_nested_vectors_match_full_source']
    lean['title_embedding']=[8.,8.]
    assert not compare(*arguments)['other_source_and_root_vectors_equal']
