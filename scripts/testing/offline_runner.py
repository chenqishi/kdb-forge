"""Safe selected tests; all historical files stay available by explicit selection."""
import json
import os
from pathlib import Path
import sys
from offline_guard import install,prepare_paths
ROOT=Path(__file__).resolve().parents[2]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
os.chdir(ROOT);install(ROOT)
try:metadata=prepare_paths(ROOT)
except Exception as exc:raise SystemExit('Offline preflight failed: '+str(exc))
print('[offline] '+json.dumps(metadata,ensure_ascii=False),flush=True)
GROUPS={
 'smoke':['tests/entry_smoke','tests/offline'],
 'retrieval':['tests/baseline_legacy/'+x+'.py' for x in ['test_list_file_names_source','test_from_type_count_api_20261008','test_es8_native_batch_20261009','test_es8_source_compat_20261009','test_default_category','test_delete_by_file','test_multimodal_url_filename']],
 'mining':['tests/baseline_legacy/'+x+'.py' for x in ['test_segment_generation_chunking','test_pdf_rendered_image_extraction','test_knowledge_clear_longcontent','test_html_insert_llm_override','test_html_text_only_pipeline','test_insert_check_duplicate_arg','test_chat_batch_watermark_safety','test_chat_group_failure_isolation','test_excel_qa_segment_upload_control','test_file_access_service_timeout','test_generic_mining_context']],
 'audit':['tests/baseline_legacy/'+x+'.py' for x in ['test_auto_audit_time_threshold','test_auto_audit_unified_20261019','test_auto_audit_update_by_query']],
}
args=sys.argv[1:];group='smoke'
if '--group' in args:
 i=args.index('--group')
 if i+1>=len(args):raise SystemExit('--group requires a name')
 group=args[i+1];del args[i:i+2]
if group=='all':paths=[p for values in GROUPS.values() for p in values]
elif group=='history':
 if not args:raise SystemExit('--group history requires explicit test file paths')
 paths=[]
elif group in GROUPS:paths=GROUPS[group]
else:raise SystemExit('Unknown group; choose smoke,retrieval,mining,audit,all,history')
process_tests={
 'mining':'tests/baseline_legacy/test_excel_qa_segment_upload_control.py::test_run_command_list_preserves_space_containing_argument',
 'audit':'tests/baseline_legacy/test_auto_audit_unified_20261019.py::test_shell_wrapper_preserves_status_logs_and_lock',
}
excluded=[node for name,node in process_tests.items() if group==name or group=='all']
for node in excluded:print('[offline] explicitly deselected (requires real subprocess): '+node,flush=True)
selection=[value for node in excluded for value in ['--deselect',node]]
print('[offline] group='+group+'; historical tests are not the default suite',flush=True)
import pytest
raise SystemExit(pytest.main(['--import-mode=importlib','-p','no:cacheprovider',*selection,*paths,*args]))
