"""Run current selected tests behind the mandatory offline boundary."""
import json
import os
from pathlib import Path
import sys
from offline_guard import install
from offline_guard import prepare_paths

ROOT = Path(__file__).resolve().parents[2]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
os.chdir(ROOT)
install(ROOT)
try:
    metadata = prepare_paths(ROOT)
except Exception as exc:
    raise SystemExit('Offline preflight failed: ' + str(exc))
print('[offline] ' + json.dumps(metadata, ensure_ascii=False), flush=True)
GROUPS = {
    'smoke': ['tests/entry_smoke', 'tests/offline'],
    'retrieval': ['tests/retrieval/' + name + '.py' for name in [
        'test_list_file_names_source', 'test_from_type_count_api', 'test_es8_native_batch',
        'test_es8_source_compat', 'test_default_category', 'test_delete_by_file',
    ]] + ['tests/mining/test_multimodal_url_filename.py'],
    'mining': ['tests/mining/' + name + '.py' for name in [
        'test_segment_generation_chunking', 'test_pdf_rendered_image_extraction',
        'test_knowledge_clear_longcontent', 'test_html_insert_llm_override',
        'test_html_text_only_pipeline', 'test_chat_group_failure_isolation',
        'test_excel_qa_segment_upload_control', 'test_generic_mining_context',
    ]] + [
        'tests/retrieval/test_insert_check_duplicate_arg.py',
        'tests/mining/tasks/test_chat_batch_watermark_safety.py',
        'tests/services/test_file_access_service_timeout.py',
    ],
    'audit': ['tests/retrieval/maintenance/' + name + '.py' for name in [
        'test_auto_audit_time_threshold', 'test_auto_audit_unified', 'test_auto_audit_update_by_query',
    ]],
    'jobs': ['tests/mining/tasks'],
    'integrations': ['tests/mining/common', 'tests/mining/web', 'tests/retrieval/maintenance'],
    'shared': ['tests/shared'],
    'services': ['tests/services'],
}
args = sys.argv[1:]
group = 'all'
if '--group' in args:
    i = args.index('--group')
    if i + 1 >= len(args):
        raise SystemExit('--group requires a name')
    group = args[i + 1]
    del args[i:i + 2]
if group == 'all':
    paths = ['tests']
elif group == 'explicit':
    if not any(value.startswith('tests/') and (ROOT / value.split('::')[0]).exists() for value in args):
        raise SystemExit('--group explicit requires current test paths')
    paths = []
elif group in GROUPS:
    paths = GROUPS[group]
else:
    raise SystemExit('Unknown group; choose ' + ','.join([*GROUPS, 'all', 'explicit']))
excluded = [
    'tests/mining/test_excel_qa_segment_upload_control.py::test_run_command_list_preserves_space_containing_argument',
    'tests/retrieval/maintenance/test_auto_audit_unified.py::test_shell_wrapper_preserves_status_logs_and_lock',
]
for node in excluded:
    print('[offline] explicitly deselected (requires real subprocess): ' + node, flush=True)
selection = [value for node in excluded for value in ['--deselect', node]]
print('[offline] group=' + group + '; network and subprocess are blocked', flush=True)
import pytest
raise SystemExit(pytest.main([
    '--import-mode=importlib', '-p', 'no:cacheprovider', *selection, *paths, *args,
]))
