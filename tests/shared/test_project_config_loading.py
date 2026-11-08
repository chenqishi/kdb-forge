"""The shared loader retains fallback, shallow overlay and per-project isolation."""
import json
import pytest

from kdb.shared.config.loading import load_global_config


@pytest.mark.parametrize('content', [None, '{invalid', json.dumps({'nested': {'override': 2}, 'new': 3})])
def test_project_config_overlay_and_isolated_fallback(tmp_path, content):
    defaults = {'nested': {'original': 1}, 'unchanged': 4}
    project_a = tmp_path / 'a'
    project_b = tmp_path / 'b'
    (project_a / 'config').mkdir(parents=True)
    if content is not None:
        (project_a / 'config/global_config.json').write_text(content)
    loaded = load_global_config(defaults, project_a)
    expected = {'nested': {'override': 2}, 'unchanged': 4, 'new': 3} if content and content.startswith('{"') else defaults
    assert loaded == expected
    loaded['nested']['mutation'] = True
    assert defaults == {'nested': {'original': 1}, 'unchanged': 4}
    assert load_global_config(defaults, project_b) == defaults
