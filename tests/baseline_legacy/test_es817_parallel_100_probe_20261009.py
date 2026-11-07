"""Verify strict audit comparison without importing/executing the remote probe."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_es817_parallel_100_probe_20261009.py')
import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest


def load_comparator():
    path = Path(__legacy_source_file__).with_name('es817_parallel_100_20261009.py')
    tree = ast.parse(path.read_text())
    remote = next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'REMOTE' for target in node.targets))
    helpers = ast.Module(body=[node for node in ast.parse(remote).body
                              if isinstance(node, ast.FunctionDef) and node.name in {'sha', 'compare'}], type_ignores=[])
    namespace = {'hashlib': hashlib, 'json': json}
    exec(compile(helpers, '<audit-helpers-only>', 'exec'), namespace)
    return namespace


@pytest.mark.parametrize('change', ['score', 'embedding', 'metadata', 'total', 'request', 'identity'])
def test_exact_comparison_rejects_small_or_hidden_changes(change):
    helpers = load_comparator()
    sha, compare = helpers['sha'], helpers['compare']
    doc = {'_index': 'a', '_id': 'same', 'score': 1.0, 'title': 'question',
           'indexes': [{'text': 'synonym', 'embedding': [1.0, 0.0, 0.0]}],
           'ext_info': {'from_file_name': 'old.txt'}, 'similarity': 0.8}
    private_a = {'engine_docs': [copy.deepcopy(doc)], 'business_docs': [copy.deepcopy(doc)]}
    private_b = copy.deepcopy(private_a)
    fields = ['requests_sha256', 'identities_sha256', 'full_engine_docs_sha256', 'complete_source_sha256',
              'recall_scores_sha256', 'similarity_sha256', 'business_docs_sha256', 'final_response_sha256']
    a = {field: sha(doc) for field in fields}
    a.update(total=1, docs=1, final_results=1, vectors={'hash': sha(doc['indexes'])}, invalid_subsearches=0)
    assert compare(a, copy.deepcopy(a), private_a, private_b)['exact'] is True
    b = copy.deepcopy(a)
    if change == 'score':
        private_b['engine_docs'][0]['score'] += 1e-14
        b['recall_scores_sha256'] = sha(private_b['engine_docs'][0]['score'])
    elif change == 'embedding':
        private_b['engine_docs'][0]['indexes'][0]['embedding'][0] += 1e-14
        b['vectors'] = {'hash': sha(private_b['engine_docs'][0]['indexes'])}
    elif change == 'metadata':
        private_b['engine_docs'][0]['ext_info']['from_file_name'] = 'new.txt'
        b['complete_source_sha256'] = sha(private_b['engine_docs'][0])
    elif change == 'total':
        b['total'] = 2
    elif change == 'request':
        b['requests_sha256'] = sha({'size': 50})
    elif change == 'identity':
        private_b['engine_docs'][0]['_index'] = 'different-index'
        b['identities_sha256'] = sha(['different-index', 'same'])
    result = compare(a, b, private_a, private_b)
    assert result['exact'] is False
    if change == 'score':
        assert 0 < result['max_common_recall_score_delta'] < 1e-12
    elif change == 'identity':
        assert result['old_only'] == result['new_only'] == 1
    with pytest.raises(ValueError):
        sha({'score': float('nan')})
