"""One small, readonly main/sg native-query observation; no remote deployment."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/main_es817_latency_20261008.py')
import copy
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from commons.embedding_tools import AliEmbedding
from es817_independent_query_compare_20261005 import make_clients, read_es
from knowledge_interface_tools.es8_search_interface import EsSearchInterfaceES8

ROOT = Path(__legacy_source_file__).resolve().parents[1]
OUT = ROOT / "docs/reviews/main_es817_latency_20261008"

PROBE = r'''
import base64,hashlib,http.client,json,os,ssl,sys,time,urllib.parse
from pathlib import Path

def snapshot():
    processes=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            args=(p/'cmdline').read_bytes().split(b'\0')
            if not any(a.endswith(b'/knowledge_database_search_es.py') or a==b'knowledge_database_search_es.py' or a==b'kdb.api.retrieval_app:app' for a in args):continue
            processes.append({'pid':int(p.name),'start_ticks':(p/'stat').read_text().rsplit(') ',1)[1].split()[19],
                              'cwd':os.readlink(str(p/'cwd'))})
        except (OSError,ValueError):pass
    hashes={}
    for name in ('/root/knowledge_database_builder/knowledge_database_search_service/src/knowledge_database_search_es.py',
                 '/root/knowledge_database_builder/knowledge_interface_tools/es_search_interface.py',
                 '/root/knowledge_database_builder/knowledge_interface_tools/es8_search_interface.py'):
        p=Path(name)
        if p.exists():hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    available=next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
    return {'processes':sorted(processes,key=lambda p:p['pid']),'source_sha256':hashes,
            'load1':os.getloadavg()[0],'cpus':os.cpu_count(),'available_memory':available}

def probe_request(provider, method, path, body=None):
    global calls
    allowed=(method=='GET' and path=='/') or (method=='HEAD' and path in ('/mercado_local','/payoneer_olive'))
    allowed=allowed or (method=='POST' and path.split('?')[0] in ('/mercado_local/_search','/payoneer_olive/_search')
        and isinstance(body,dict) and body.get('size')==5 and not body.get('profile') and '_source' not in body)
    if not allowed or calls>=8:raise RuntimeError('readonly_budget_or_scope')
    calls+=1
    state=snapshot()
    if state['load1']>state['cpus']*.75 or state['available_memory']<1024**3:raise RuntimeError('host_busy_stop')
    cfg=payload['providers'][provider]
    headers={'Content-Type':'application/json','Accept-Encoding':'identity'}
    if cfg.get('username'):
        headers['Authorization']='Basic '+base64.b64encode((cfg['username']+':'+cfg.get('password','')).encode()).decode()
    data=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode() if body is not None else None
    start=time.perf_counter()
    connections[provider].request(method,path,body=data,headers=headers)
    response=connections[provider].getresponse()
    raw=response.read(16*1024**2+1)
    elapsed=(time.perf_counter()-start)*1000
    if response.status!=200 or len(raw)>16*1024**2:raise RuntimeError('http_status_'+str(response.status))
    decode_start=time.perf_counter()
    result=json.loads(raw) if raw else {}
    decode_ms=(time.perf_counter()-decode_start)*1000
    if result.get('error') or result.get('timed_out') or result.get('_shards',{}).get('failed',0):raise RuntimeError('partial_or_failed_search')
    return result,{'http_ms':elapsed,'json_parse_ms':decode_ms,'response_bytes':len(raw),'es_took_ms':result.get('took'),'status':response.status}

payload=json.load(sys.stdin)
connections={};calls=0
report={'hostname':os.uname().nodename,'rows':[],'before':snapshot(),'writes':0,'online_api_requests':0,'versions':{}}
try:
    for provider,cfg in payload['providers'].items():
        hosts=cfg['hosts'];url=urllib.parse.urlsplit(hosts[0] if isinstance(hosts,list) else hosts)
        if url.scheme=='https':
            context=ssl.create_default_context() if cfg.get('verify_certs',True) else ssl._create_unverified_context()
            connections[provider]=http.client.HTTPSConnection(url.hostname,url.port or 443,timeout=15,context=context)
        else:connections[provider]=http.client.HTTPConnection(url.hostname,url.port or 80,timeout=15)
        version=probe_request(provider,'GET','/')[0]['version']['number']
        if not version.startswith('8.17.'):raise RuntimeError('unexpected_version')
        report['versions'][provider]=version
    for provider,index in [('serverless','mercado_local'),('paas','payoneer_olive')]:probe_request(provider,'HEAD','/'+index)
    for task in payload['tasks']:
        response,metrics=probe_request(task['provider'],'POST','/'+task['index']+'/_search?ignore_unavailable=true&allow_no_indices=true',task['body'])
        hits=response['hits']['hits']
        metrics.update({'case':task['case'],'index':task['index'],'provider':task['provider'],'route':task['route'],
                        'hits':len(hits),'ids':[h['_id'] for h in hits],
                        'body_sha256':hashlib.sha256(json.dumps(response,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                        'shards':response.get('_shards'),'full_source':True,
                        'documents_with_nested_vector':sum(any(isinstance(x,dict) and x.get('embedding') for x in h.get('_source',{}).get('indexes',[]) if isinstance(h.get('_source',{}).get('indexes'),list)) for h in hits)})
        report['rows'].append(metrics)
        if len(report['rows'])<len(payload['tasks']):time.sleep(5)
    report['passed']=len(report['rows'])==4 and all(r['hits']>0 for r in report['rows'])
except Exception as exc:
    report['passed']=False;report['error_type']=type(exc).__name__
    if isinstance(exc,RuntimeError):report['failure_reason']=str(exc)
finally:
    for connection in connections.values():connection.close()
    report['calls']=calls;report['after']=snapshot()
    report['online_processes_unchanged']=report['before']['processes']==report['after']['processes']
    report['online_source_unchanged']=report['before']['source_sha256']==report['after']['source_sha256']
    print(json.dumps(report,ensure_ascii=False))
'''


def prepare():
    matrix = json.loads((ROOT / "docs/reviews/es817_category_filter_continue_20261008/matrix.json").read_text())
    providers = json.loads((ROOT / "config/config_es_engine_es817.old.local.json").read_text())["providers"]
    cfg = json.loads((ROOT / "config/config_for_search_index_es817.local.json").read_text())
    embedding = AliEmbedding(cfg["embedding_config_path"])
    builder = EsSearchInterfaceES8.__new__(EsSearchInterfaceES8)
    builder.vector_fields = {"indexes_embedding": 1024}
    tasks, metadata = [], []
    clients = make_clients()
    try:
        for index, provider in (("mercado_local", "serverless"), ("payoneer_olive", "paas")):
            read_es(clients[provider], "HEAD", "/" + index)
            row = next(r for r in matrix if r["platform"] == index and r["endpoint"] == "search" and r["variant"] == "parent_and_child")
            request = row["request"]
            start = time.perf_counter()
            vector = embedding.text2embedding(request["text"]).tolist()
            query = {"query": request["text"], "vector": {"value": vector},
                     "attribute": copy.deepcopy(request["condition_dicts"])}
            metadata.append({"index": index, "provider": provider, "query_origin": row["case"],
                "embedding_ms": (time.perf_counter() - start) * 1000, "dims": len(vector),
                "query_sha256": hashlib.sha256(request["text"].encode()).hexdigest(),
                "vector_sha256": hashlib.sha256(json.dumps(vector).encode()).hexdigest(),
                "attributes": query["attribute"], "scope": "public existing physical index only"})
            for route in ("bm25", "vector"):
                body = {"query": builder._build_search_query(query, include_text=route == "bm25",
                    include_vector=route == "vector", vector_k=5, with_inner_hits=route == "vector"), "size": 5}
                tasks.append({"provider": provider, "index": index, "route": route,
                              "case": row["case"] + ":" + route, "body": body})
    finally:
        for client in clients.values():
            client.session.close()
    return {"providers": providers, "tasks": tasks}, metadata


def run_location(label, payload):
    if label == "main":
        command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "shenzhen-120",
                   "nice -n 15 python3 -c " + shlex.quote(PROBE)]
    else:
        command = ["nice", "-n", "15", sys.executable, "-c", PROBE]
    result = subprocess.run(command, input=json.dumps(payload, ensure_ascii=False),
                            capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(label + " probe process failed; diagnostic stdout not printed")
    evidence = json.loads(result.stdout)
    evidence["location"] = label
    return evidence


def main():
    OUT.mkdir(mode=0o700, exist_ok=False)
    payload, metadata = prepare()
    evidence = {"captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "single-pass native BM25/KNN from main and sg; excludes embedding/API/rerank",
        "metadata": metadata, "locations": [], "implementation_sha256": hashlib.sha256(
            (ROOT / "knowledge_interface_tools/es8_search_interface.py").read_bytes()).hexdigest(),
        "same_dsl_vector_endpoint": True, "credentials_vectors_saved": False}
    for label in ("main", "sg"):
        current = run_location(label, payload)
        evidence["locations"].append(current)
        (OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
        os.chmod(OUT / "evidence.json", 0o600)
        if not current["passed"]:
            print(json.dumps({"location": label, "passed": False, "failure_reason": current.get("failure_reason"), "evidence": str(OUT / "evidence.json")}))
            raise SystemExit(1)
    print(json.dumps({"passed": True, "locations": [{"location": r["location"], "calls": r["calls"],
        "rows": r["rows"], "online_processes_unchanged": r["online_processes_unchanged"]}
        for r in evidence["locations"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
