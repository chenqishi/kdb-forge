"""Run the candidate in a separate main process, in memory, with a write gate.

No remote code/config installation. Uses main's existing ES8 interpreter and
config files. The only allowed HTTP operations are index HEAD, count, search
aggregations and cat inventory. No audit mutations or service HTTP requests.
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/auto_audit_readonly_20261019.py')
import json
import shlex
import subprocess
from pathlib import Path


def main():
    root = Path(__legacy_source_file__).resolve().parents[1]
    names = ["knowledge_interface_tools.es_maintenance", "knowledge_interface_tools.es8_client_router",
             "knowledge_interface_tools.es8_search_interface", "knowledge_interface_tools.es_search_interface",
             "control_script.timing_auto_audit_kg"]
    sources = {}
    for name in names:
        path = root / (name.replace(".", "/") + ".py")
        if path.stat().st_size > 2 * 1024 * 1024:
            raise RuntimeError("Unexpected large candidate source")
        sources[name] = path.read_text()
    remote = r'''
import sys, json, types, hashlib, contextlib, io, logging
from pathlib import Path
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch
logging.disable(logging.CRITICAL)
root = Path('/root/knowledge_database_builder')
sys.path.insert(0, str(root))
requests = []
original = Elasticsearch.perform_request
def readonly_request(self, method, path, *args, **kwargs):
    allowed = (method == 'HEAD' or (method == 'GET' and (path == '/' or path.startswith('/_cat/indices')))
               or (method == 'POST' and path.endswith(('/_count', '/_search'))))
    if not allowed:
        raise AssertionError('Persistent mutation/unsupported request blocked by readonly guard')
    requests.append({'method': method, 'path': path})
    return original(self, method, path, *args, **kwargs)
Elasticsearch.perform_request = readonly_request
sources = json.load(sys.stdin)
for name, source in sources.items():
    module = types.ModuleType(name)
    module.__file__ = str(root / (name.replace('.', '/') + '.py'))
    module.__package__ = name.rsplit('.', 1)[0]
    sys.modules[name] = module
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
audit = sys.modules['control_script.timing_auto_audit_kg']
processor = audit.AutoAuditProcessor(search_config_path=str(root / 'config/config_for_search_index.json'))
try:
    result = processor.auto_audit_for_indexes(['payoneer_olive', 'mercado_local'], ['document', 'html'], dry_run=True)
    direct = {}
    cutoff = (processor.started_at - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    for index, expected_provider in [('payoneer_olive', 'paas'), ('mercado_local', 'serverless')]:
        assert processor.engine.get_index_provider(index) == expected_provider
        entry = result['details'][index]
        assert entry['status'] == 'dry_run'
        conditions = [{'terms': {'from_type_norm': ['document','html']}}, {'term': {'audit_result': -1}},
                      {'range': {'insert_time': {'lte': cutoff}}}]
        client = processor.engine.get_client_by_index(index)
        totals = {}
        for label, query in [('total_count', {'bool': {'filter': conditions}}),
                             ('high_count', {'bool': {'filter': conditions + [{'term': {'quality_level': 'high'}}]}}),
                             ('other_count', {'bool': {'filter': conditions, 'must_not': [
                                  {'term': {'quality_level': 'high'}}, {'term': {'data_type': 'segment'}}]}})]:
            response = client.count(index=index, query=query)
            assert response['_shards']['failed'] == 0
            totals[label] = response['count']
            assert entry['result']['stats'][label] == totals[label]
        direct[index] = totals
    assert result['summary']['failed_count'] == 0
    inventory = processor.get_all_indexes()
    assert all(index in inventory for index in ['payoneer_olive', 'mercado_local'])
    report = {'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
              'mode': 'candidate_in_memory_real_main_readonly', 'result': result, 'independent_counts': direct,
              'inventory_count': len(inventory), 'inventory': inventory, 'requests': requests,
              'persistent_writes': 0, 'services_restarted': 0,
              'source_sha256': {name: hashlib.sha256(text.encode()).hexdigest() for name,text in sources.items()}}
finally:
    processor.close()
print(json.dumps(report, ensure_ascii=False, indent=2))
'''
    command = "cd /root/knowledge_database_builder && PYTHONDONTWRITEBYTECODE=1 .venv-es817/bin/python -c " + shlex.quote(remote)
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "shenzhen-120", command],
                            input=json.dumps(sources), text=True, capture_output=True, timeout=60)
    if result.returncode:
        # Candidate tracebacks have no config contents. Keep output bounded.
        raise RuntimeError("Readonly candidate failed: " + result.stderr[-4000:])
    report = json.loads(result.stdout)
    destination = root / "docs/reviews/auto_audit_unified_20261019"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "main_readonly.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"report": str(destination / "main_readonly.json"),
                      "independent_counts": report["independent_counts"],
                      "inventory_count": report["inventory_count"], "requests": len(report["requests"]),
                      "persistent_writes": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
