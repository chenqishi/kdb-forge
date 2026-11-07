"""Bounded new-ES8-only main experiment, using actual in-memory engine source.

No remote files, service requests, installed dependencies or ES mutations.
The readonly standard-library HTTP adapter substitutes only the client boundary.
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/main_es817_expanded_20261008.py')
import ast
import copy
import hashlib
import json
import math
import os
import shlex
import subprocess
import textwrap
import time
from pathlib import Path

from commons.embedding_tools import AliEmbedding

ROOT = Path(__legacy_source_file__).resolve().parents[1]
OUT = Path(os.environ.get("KDB_ES8_PROBE_OUTPUT", str(ROOT / "docs/reviews/main_es817_expanded_20261008")))
INDICES = {
    "mercado_local": ["mercado_local_mercado_local_admin", "mercado_local"],
    "payoneer_olive": ["payoneer_olive_payoneer_olive", "payoneer_olive"],
}

REMOTE = r'''
import base64,copy,hashlib,http.client,json,logging,math,os,ssl,sys,threading,time,types,urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from types import SimpleNamespace
from typing import Any,Dict,List

logging.disable(logging.CRITICAL)
payload=json.load(sys.stdin)
deadline=time.monotonic()+480
stop=threading.Event()
lock=threading.Lock()
local=threading.local()
contexts=[]
read_count=0
search_count=0
allowed={name: provider for group in payload['cases'] for name in group['indices'] for provider in [group['provider']]}

def cosine_similarity(a,b):
    if len(a)!=len(b) or not all(math.isfinite(x) for x in a+b):
        raise ValueError('invalid_rerank_vector')
    norm=math.sqrt(sum(x*x for x in a))*math.sqrt(sum(x*x for x in b))
    return sum(x*y for x,y in zip(a,b))/norm if norm else 0.0

def load_sources():
    package=types.ModuleType('knowledge_interface_tools')
    package.__path__=[]
    sys.modules[package.__name__]=package
    for short,source in payload['sources'].items():
        name='knowledge_interface_tools.'+short
        module=types.ModuleType(name)
        module.__package__=package.__name__
        sys.modules[name]=module
        exec(compile(source,'<isolated:'+name+'>','exec'),module.__dict__)
    exec(payload['helpers'],globals())
    exec(payload['reranker'],globals())

class ReadClient:
    def __init__(self,cfg,provider):
        self.provider=provider
        self.metrics=[]
        hosts=cfg['hosts']
        url=urllib.parse.urlsplit(hosts[0] if isinstance(hosts,list) else hosts)
        self.headers={'Content-Type':'application/json','Accept-Encoding':'identity'}
        if cfg.get('username'):
            self.headers['Authorization']='Basic '+base64.b64encode((cfg['username']+':'+cfg.get('password','')).encode()).decode()
        if url.scheme=='https':
            context=ssl.create_default_context() if cfg.get('verify_certs',True) else ssl._create_unverified_context()
            self.connection=http.client.HTTPSConnection(url.hostname,url.port or 443,timeout=15,context=context)
        else:
            self.connection=http.client.HTTPConnection(url.hostname,url.port or 80,timeout=15)

    def request(self,method,path,body=None):
        global read_count,search_count
        approved=method=='GET' and path=='/'
        approved=approved or method=='HEAD' and path[1:] in allowed and allowed[path[1:]]==self.provider
        is_search=method=='POST' and path.endswith('/_search')
        if is_search:
            index=path[1:-len('/_search')]
            approved=index in allowed and allowed[index]==self.provider and isinstance(body,dict) and set(body)=={'query','size'} and body['size']==5
            # Current builder emits no script/PIT/scroll/profile/source filter.
            def_keys=json.dumps(body,separators=(',',':'))
            approved=approved and not any('"'+key+'":' in def_keys for key in ('script_score','script','profile','pit','scroll'))
        if not approved:
            stop.set()
            raise RuntimeError('scope_rejected')
        with lock:
            if stop.is_set() or read_count>=680 or search_count>=650 or time.monotonic()>deadline:
                raise RuntimeError('stopped_or_budget')
            read_count+=1
            search_count+=int(is_search)
        metric={'provider':self.provider,'method':method,'index':path.split('/')[1],'ok':False}
        if is_search:
            metric['route']='vector' if '"knn":' in def_keys else 'bm25'
        data=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode() if body is not None else None
        try:
            start=time.perf_counter()
            self.connection.request(method,path,body=data,headers=self.headers)
            response=self.connection.getresponse()
            raw=response.read(16*1024**2+1)
            metric.update({'http_ms':(time.perf_counter()-start)*1000,'status':response.status,'response_bytes':len(raw)})
            if response.status!=200 or len(raw)>16*1024**2:
                raise RuntimeError('http_or_response_bound')
            start=time.perf_counter()
            result=json.loads(raw) if raw else {}
            metric['parse_ms']=(time.perf_counter()-start)*1000
            metric['took_ms']=result.get('took')
            metric['shards']=result.get('_shards')
            shards=result.get('_shards') or {}
            if result.get('error') or result.get('timed_out') or shards.get('failed',0) or shards.get('total',0)>shards.get('successful',0):
                raise RuntimeError('partial_or_timeout')
            if is_search:
                hits=result['hits']['hits']
                nested=[h for hit in hits for section in (hit.get('inner_hits') or {}).values() for h in section.get('hits',{}).get('hits',[])]
                metric.update({'hits':len(hits),'inner_hits':len(nested),'empty_inner_source':sum(not h.get('_source') for h in nested),
                    'inner_with_1024_vector':sum(len((h.get('_source') or {}).get('embedding') or [])==1024 for h in nested),
                    'ids':[h['_index']+':'+h['_id'] for h in hits]})
            metric['ok']=True
            return result
        except Exception as exc:
            stop.set()
            metric['error_type']=type(exc).__name__
            if isinstance(exc,RuntimeError):metric['reason']=str(exc)
            raise
        finally:
            if is_search:self.metrics.append(metric)

    def search(self,**kwargs):
        if set(kwargs)!={'index','query','size'}:
            stop.set()
            raise RuntimeError('unexpected_engine_client_parameter')
        return self.request('POST','/'+kwargs['index']+'/_search',{'query':kwargs['query'],'size':kwargs['size']})

    def close(self):
        self.connection.close()

def make_context():
    router_cls=sys.modules['knowledge_interface_tools.es8_client_router'].IndexClientRouter
    engine_cls=sys.modules['knowledge_interface_tools.es8_search_interface'].EsSearchInterfaceES8
    clients={}
    for provider,cfg in payload['config']['providers'].items():
        client=ReadClient(cfg,provider)
        clients[provider]=client
        version=client.request('GET','/')['version']['number']
        if not version.startswith('8.17.'):
            stop.set()
            raise RuntimeError('unexpected_version')
    cfg=copy.deepcopy(payload['config'])
    cfg['extra_params']['ensure_index_on_init']=False
    cfg['extra_params']['auto_update_mapping']=False
    # Injection at the existing client factory boundary only.
    router=router_cls(config=cfg,client_factory=lambda c: next(clients[p] for p in clients if c==cfg['providers'][p]))
    engine=engine_cls(config=cfg,router=router,index_name='mercado_local',ensure_index=False)
    context={'engine':engine,'router':router,'clients':clients,'reranker':Reranker()}
    with lock:contexts.append(context)
    return context

def run_case(case,stage,sequence):
    state=snapshot()
    if state['load1']>state['cpus']*.5 or state['available_memory']<4*1024**3 or state['processes']!=initial['processes']:
        stop.set()
        raise RuntimeError('host_or_online_process_guard')
    if stop.is_set():raise RuntimeError('stopped')
    if not hasattr(local,'context'):local.context=make_context()
    context=local.context
    for client in context['clients'].values():client.metrics=[]
    vector=payload['vectors'][case['text']]
    query={'query':case['text'],'vector':{'value':vector},'attribute':copy.deepcopy(case['groups'])}
    start=time.perf_counter()
    docs,total=context['engine'].search_multi(query,index_names=case['indices'],size=10,recall_mode='dual')
    engine_ms=(time.perf_counter()-start)*1000
    routes=[item for client in context['clients'].values() for item in client.metrics]
    if len(routes)!=4 or any(not item['ok'] for item in routes) or stop.is_set():
        raise RuntimeError('route_failure_or_missing_route')
    start=time.perf_counter()
    scored=[(doc,float(context['reranker']._cal_similarity(case['text'],vector,doc,search_type='qa',data_type='text',use_synonyms=True))) for doc in docs]
    rerank_ms=(time.perf_counter()-start)*1000
    scored.sort(key=lambda item:item[1],reverse=True)
    field_issues=[]
    source_counts=Counter()
    for doc,_ in scored:
        for field in ('title_embedding','content_embedding'):
            value=doc.get(field)
            if value:
                source_counts[field]+=1
                if len(value)!=1024:field_issues.append(doc['_id']+':'+field)
        entries=doc.get('indexes') or []
        if not isinstance(entries,list):
            field_issues.append(doc['_id']+':indexes_shape')
            entries=[]
        if any(isinstance(entry,dict) and len(entry.get('embedding') or [])==1024 for entry in entries):source_counts['nested_vectors']+=1
        wanted=set(doc.get('synonyms_title') or [])
        if wanted:
            source_counts['synonym_documents']+=1
            if any(entry.get('text') in wanted and len(entry.get('embedding') or [])==1024 for entry in entries if isinstance(entry,dict)):
                source_counts['synonym_rerank_input']+=1
            else:source_counts['missing_synonym_rerank_input']+=1
    violations=[doc['_id'] for doc in docs if not matches(doc,case['groups'],'search')]
    row={'case':case['case'],'platform':case['platform'],'kind':case['kind'],'stage':stage,'sequence':sequence,
        'engine_ms':engine_ms,'rerank_python_ms':rerank_ms,'engine_plus_rerank_ms':engine_ms+rerank_ms,
        'route_count':len(routes),'routes':routes,'total':total,'candidates':len(docs),
        'candidate_ids':sorted(doc['_index']+':'+doc['_id'] for doc in docs),
        'final_top5':[{'id':doc['_index']+':'+doc['_id'],'similarity':score} for doc,score in scored[:5]],
        'source_counts':dict(source_counts),'field_issues':field_issues,'condition_violations':violations,
        'negative':case['negative'],'negative_ok':not docs if case['negative'] else None,
        'empty_positive':not docs and not case['negative'],'main_load1':state['load1'],'main_available_memory':state['available_memory']}
    if violations or field_issues or row['negative_ok'] is False or not all(math.isfinite(score) for _,score in scored):
        stop.set()
        row['failed_checks']=True
    return row

def run_probe():
    global initial
    load_sources()
    initial=snapshot()
    result={'before':initial,'hostname':os.uname().nodename,'stages':[],'rows':[],
        'online_api_requests':0,'remote_file_writes':0,'es_writes':0,'versions':{},'errors':[]}
    try:
        for provider,cfg in payload['config']['providers'].items():
            client=ReadClient(cfg,provider)
            try:
                version=client.request('GET','/')['version']['number']
                if not version.startswith('8.17.'):raise RuntimeError('unexpected_version')
                result['versions'][provider]=version
                for index,route in allowed.items():
                    if route==provider:client.request('HEAD','/'+index)
            finally:client.close()
        print(json.dumps({'event':'preflight','versions':result['versions'],'indices':list(allowed),'load1':initial['load1']}),flush=True)
        for workers,repeats in [(1,1),(2,1),(4,2)]:
            if stop.is_set():break
            start=time.perf_counter()
            cpu_start=time.process_time()
            batch=payload['cases']*repeats
            completed=0
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures={executor.submit(run_case,case,workers,n):case['case'] for n,case in enumerate(batch)}
                for future in as_completed(futures):
                    try:
                        row=future.result()
                        result['rows'].append(row)
                        completed+=1
                    except Exception as exc:
                        stop.set()
                        result['errors'].append({'case':futures[future],'stage':workers,'error_type':type(exc).__name__,
                            'reason':str(exc) if isinstance(exc,RuntimeError) else 'sanitized'})
                        for pending in futures:pending.cancel()
                    if completed and completed%10==0:
                        print(json.dumps({'event':'progress','workers':workers,'completed':completed,'planned':len(batch),'search_reads':search_count}),flush=True)
            elapsed=time.perf_counter()-start
            result['stages'].append({'workers':workers,'planned':len(batch),'completed':completed,'wall_s':elapsed,
                'process_cpu_s':time.process_time()-cpu_start,'logical_qps':completed/elapsed,'after':snapshot()})
            print(json.dumps({'event':'stage_done',**{k:v for k,v in result['stages'][-1].items() if k!='after'}}),flush=True)
            if not stop.is_set():time.sleep(5)
    except Exception as exc:
        stop.set()
        result['errors'].append({'error_type':type(exc).__name__,'reason':str(exc) if isinstance(exc,RuntimeError) else 'sanitized'})
    finally:
        result['failed_native_requests']=[metric for context in contexts for client in context['clients'].values() for metric in client.metrics if not metric['ok']]
        for context in contexts:
            for client in context['clients'].values():client.close()
        result['after']=snapshot()
        result['online_processes_unchanged']=result['before']['processes']==result['after']['processes']
        result['online_source_unchanged']=result['before']['source_sha256']==result['after']['source_sha256']
        result['search_reads']=search_count
        result['total_es_reads']=read_count
        result['passed']=len(result['rows'])==148 and not stop.is_set() and not result['errors'] and result['online_processes_unchanged'] and result['online_source_unchanged']
        print(json.dumps({'event':'final','result':result},ensure_ascii=False),flush=True)

run_probe()
'''


def extract_functions(source, names):
    tree = ast.parse(source)
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if set(names) - functions.keys():
        raise ValueError("missing source functions")
    return "\n\n".join(ast.unparse(functions[name]) for name in names)


def prepare():
    cfg = json.loads((ROOT / "config/config_es_engine_es817.old.local.json").read_text())
    cfg["extra_params"]["ensure_index_on_init"] = False
    cfg["extra_params"]["auto_update_mapping"] = False
    samples = json.loads((ROOT / "docs/reviews/es817_independent_query_compare_20261005/samples.json").read_text())
    matrix = json.loads((ROOT / "docs/reviews/es817_category_filter_continue_20261008/matrix.json").read_text())
    cases = []
    for item in samples:
        if item["platform"] not in INDICES:
            continue
        cases.append({"case": item["case"], "platform": item["platform"], "text": item["query"],
            "kind": item["sample_kind"], "negative": False,
            "groups": [{"quality_level": ["high"], "data_type": ["qa"], "audit_result": [1, 2, -1]},
                       {"audit_result": [1, 2], "data_type": ["qa"]}]})
    for item in matrix:
        if item["endpoint"] != "search" or item["platform"] not in INDICES:
            continue
        cases.append({"case": item["case"], "platform": item["platform"], "text": item["request"]["text"],
            "kind": "category", "negative": "negative" in item["variant"], "groups": copy.deepcopy(item["expected_groups"])})
    assert len(cases) == 37 and len({c["case"] for c in cases}) == 37
    for case in cases:
        case["provider"] = "serverless" if case["platform"] == "mercado_local" else "paas"
        case["indices"] = INDICES[case["platform"]]
    texts = list(dict.fromkeys(c["text"] for c in cases))
    embedding_cfg = json.loads((ROOT / "config/config_for_search_index_es817.local.json").read_text())
    embedding = AliEmbedding(embedding_cfg["embedding_config_path"])
    vectors = {}
    for offset in range(0, len(texts), 8):
        batch = texts[offset:offset+8]
        result = embedding.text2embedding(batch).tolist()
        assert len(result) == len(batch)
        for text, vector in zip(batch, result):
            assert len(vector) == 1024 and all(math.isfinite(x) for x in vector)
            vectors[text] = vector
        print(json.dumps({"event": "embedding_prepared", "unique_texts": len(vectors), "planned": len(texts)}), flush=True)
    sources = {name: (ROOT / "knowledge_interface_tools" / (name + ".py")).read_text()
        for name in ("es_count_utils", "es8_client_router", "es8_search_interface")}
    prior = ast.parse((ROOT / "tests/main_es817_latency_20261008.py").read_text())
    probe = next(node.value.value for node in prior.body if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "PROBE" for target in node.targets))
    oracle = (ROOT / "tests/es817_category_filter_compare_20261008.py").read_text()
    category_fields = {"category_path", "category_ids", "cate_name"} | {f"cate{level}_{kind}" for level in range(1, 5) for kind in ("name", "id")}
    helpers = "CATEGORY_FIELDS=" + repr(category_fields) + "\n" + extract_functions(oracle, ["field_values", "matches"]) + "\n" + extract_functions(probe, ["snapshot"])
    business = (ROOT / "knowledge_interface_tools/search_index_data_interface.py").read_text()
    reranker = "class Reranker:\n" + textwrap.indent(extract_functions(business, ["_cal_title_similarity", "_cal_similarity"]), "    ")
    reranker = "logger=logging.getLogger('isolated_reranker')\n" + reranker
    metadata = [{k: copy.deepcopy(v) for k, v in c.items() if k != "text"} | {
        "query_sha256": hashlib.sha256(c["text"].encode()).hexdigest(),
        "vector_sha256": hashlib.sha256(json.dumps(vectors[c["text"]]).encode()).hexdigest()} for c in cases]
    return {"config": cfg, "cases": cases, "vectors": vectors, "sources": sources, "helpers": helpers, "reranker": reranker}, metadata


def summarize(evidence):
    summary = {"passed": evidence["passed"], "logical_requests": len(evidence["rows"]),
        "unique_cases": len({r["case"] for r in evidence["rows"]}), "search_reads": evidence["search_reads"],
        "total_es_reads": evidence["total_es_reads"], "stages": [], "errors": evidence["errors"]}
    baseline = {r["case"]: r for r in evidence["rows"] if r["stage"] == 1}
    for stage in evidence["stages"]:
        rows = [r for r in evidence["rows"] if r["stage"] == stage["workers"]]
        by_provider = {}
        for platform in INDICES:
            group = [r for r in rows if r["platform"] == platform]
            values = sorted(r["engine_ms"] for r in group)
            if not values:
                continue
            routes = [q for r in group for q in r["routes"]]
            by_provider[platform] = {"logical_requests": len(group), "engine_p50_ms": values[math.ceil(len(values)*.5)-1],
                "engine_p95_ms": values[math.ceil(len(values)*.95)-1], "engine_max_ms": values[-1],
                "response_bytes": sum(q["response_bytes"] for q in routes), "search_requests": len(routes),
                "took_p50_ms": sorted(q["took_ms"] for q in routes)[math.ceil(len(routes)*.5)-1],
                "rerank_python_p50_ms": sorted(r["rerank_python_ms"] for r in group)[math.ceil(len(group)*.5)-1]}
        summary["stages"].append({**{k:v for k,v in stage.items() if k!="after"},"providers":by_provider})
    comparisons = [r for r in evidence["rows"] if r["stage"] != 1 and r["case"] in baseline]
    summary["consistency"] = {"comparisons":len(comparisons),
        "same_candidates":sum(r["candidate_ids"]==baseline[r["case"]]["candidate_ids"] for r in comparisons),
        "same_top5_order":sum([d["id"] for d in r["final_top5"]]==[d["id"] for d in baseline[r["case"]]["final_top5"]] for r in comparisons),
        "changed_cases":[{"case":r["case"],"stage":r["stage"],"sequence":r["sequence"]} for r in comparisons
            if r["candidate_ids"]!=baseline[r["case"]]["candidate_ids"] or [d["id"] for d in r["final_top5"]]!=[d["id"] for d in baseline[r["case"]]["final_top5"]]]}
    summary["checks"] = {"condition_violations":sum(len(r["condition_violations"]) for r in evidence["rows"]),
        "field_issues":sum(len(r["field_issues"]) for r in evidence["rows"]),
        "negative_runs":sum(r["negative"] for r in evidence["rows"]),
        "negative_failures":sum(r["negative_ok"] is False for r in evidence["rows"]),
        "empty_positive_cases":sorted({r["case"] for r in evidence["rows"] if r["empty_positive"]}),
        "missing_synonym_rerank_inputs":sum(r["source_counts"].get("missing_synonym_rerank_input",0) for r in evidence["rows"]),
        "empty_inner_sources":sum(q["empty_inner_source"] for r in evidence["rows"] for q in r["routes"]),
        "inner_hits":sum(q["inner_hits"] for r in evidence["rows"] for q in r["routes"])}
    return summary


def main():
    OUT.mkdir(mode=0o700, exist_ok=False)
    payload, metadata = prepare()
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "shenzhen-120", "nice -n 15 python3 -c " + shlex.quote(REMOTE)]
    start = time.monotonic()
    evidence = None
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as process:
        process.stdin.write(json.dumps(payload, ensure_ascii=False))
        process.stdin.close()
        for line in process.stdout:
            if time.monotonic()-start > 480:
                process.terminate()
                raise RuntimeError("bounded main probe exceeded time limit")
            event = json.loads(line)
            if event["event"] == "final":
                evidence = event["result"]
            else:
                print(json.dumps(event, ensure_ascii=False), flush=True)
        process.wait(timeout=20)
        if process.returncode or evidence is None:
            raise RuntimeError("main probe exited before final sanitized evidence")
    evidence["metadata"] = metadata
    evidence["captured_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    evidence["source_hashes"] = {name: hashlib.sha256(source.encode()).hexdigest() for name,source in payload["sources"].items()}
    evidence["business_rerank_sha256"] = hashlib.sha256(payload["reranker"].encode()).hexdigest()
    evidence["scope"] = "actual new ES8 engine/router/dual merge and extracted unchanged QA rerank; readonly HTTP client substitute, stdlib cosine; cached embeddings; excludes full API/URL rendering/embedding timing"
    summary = summarize(evidence)
    for name, value in (("evidence.json",evidence),("summary.json",summary)):
        path = OUT / name
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
        path.chmod(0o600)
    print(json.dumps(summary,ensure_ascii=False,indent=2), flush=True)
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
