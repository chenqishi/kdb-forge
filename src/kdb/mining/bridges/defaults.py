from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
import os

PROJECT_ROOT = str(_PROJECT_ROOT)


DEFAULT_SEARCH_CONFIG = os.path.join(PROJECT_ROOT, 'config', 'config_for_search_index.json')


DEFAULT_CONDITION_DICTS = [{'audit_result': [1, 2], 'data_type': ['qa']}]
