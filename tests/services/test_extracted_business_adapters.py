"""Preserve language rule priority and model fallback after extraction."""
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize('rule', [('__label__ja', 1.0), None])
def test_language_rule_precedes_unchanged_model_fallback(monkeypatch, rule):
    from kdb.multilingual import detection
    from kdb.multilingual import runtime
    model = Mock()
    model.predict.return_value = (['__label__en'], [0.75])
    monkeypatch.setattr(runtime, 'model', model)
    monkeypatch.setattr(detection, 'rule_based_language_detection', lambda text: rule)
    result = detection.detect_language('sample')
    if rule:
        assert result == {'lang': 'japanese', 'confidence': 1.0, 'label': '__label__ja'}
        model.predict.assert_not_called()
    else:
        assert result == {'lang': 'english', 'confidence': 0.75, 'label': '__label__en'}
        model.predict.assert_called_once_with('sample', k=1)
