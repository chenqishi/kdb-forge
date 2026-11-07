"""Read-only baseline/candidate/old-ES7 batch comparison on 120; no deployment."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/es817_native_batch_validation_20261009.py')
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from es817_online_latency_diagnostic_20261009 import REMOTE as DIAGNOSTIC


OLD = r'''
import hashlib,json,logging,sys,time
from pathlib import Path
from elasticsearch import Elasticsearch
from knowledge_interface_tools.es_search_interface import EsSearchInterfaceOri
from knowledge_interface_tools.search_index_data_interface import SearchDataInterface
logging.disable(logging.CRITICAL)
incoming=json.load(sys.stdin)
names=incoming['indexes'];query=incoming['query'];size=incoming['size']
allowed=set(names);events=[];counter=0
cfg=json.loads(Path('/root/dify/knowledge_database_builder/config/config_es_engine.json').read_text())
client=Elasticsearch(cfg['hosts'],http_auth=(cfg['username'],cfg['password']),timeout=15,max_retries=0,retry_on_timeout=False)

def trace_connection(connection):
    original=connection.perform_request
    def wrapped(method,url,*args,**kwargs):
        global counter
        path=url.split('?',1)[0]
        ok=(method=='GET' and path=='/') or (method=='HEAD' and path[1:] in allowed)
        ok=ok or (method=='POST' and (path=='/_msearch' or any(path=='/'+i+'/_search' for i in allowed)))
        if not ok or counter>=12:raise RuntimeError('old_read_scope')
        counter+=1
        start=time.perf_counter();response=original(method,url,*args,**kwargs)
        data=response[2];decoded=json.loads(data) if data else {}
        subs=decoded.get('responses',[decoded]) if method=='POST' else []
        for sub in subs:
            if sub.get('error') or sub.get('timed_out') or (sub.get('_shards') or {}).get('failed'):
                raise RuntimeError('old_incomplete_response')
        events.append({'method':method,'path':path,'network_ms':(time.perf_counter()-start)*1000,
            'decoded_bytes':len(data.encode() if isinstance(data,str) else data),
            'took_ms':[sub.get('took') for sub in subs],
            'nested_vector_instances':sum(len(item.get('embedding') or [])==1024 for sub in subs
                for hit in sub.get('hits',{}).get('hits',[]) for item in hit.get('_source',{}).get('indexes',[])),
            'inner_vector_instances':sum(len(item.get('_source',{}).get('embedding') or [])==1024 for sub in subs
                for hit in sub.get('hits',{}).get('hits',[]) for section in hit.get('inner_hits',{}).values()
                for item in section.get('hits',{}).get('hits',[]))})
        return response
    connection.perform_request=wrapped

try:
    for c in client.transport.connection_pool.connections:trace_connection(c)
    if not client.info()['version']['number'].startswith('7.10'):raise RuntimeError('wrong_old_version')
    for name in names:
        if not client.indices.exists(index=name):raise RuntimeError('old_index_missing')
    engine=EsSearchInterfaceOri.__new__(EsSearchInterfaceOri)
    engine.es=client;engine.index_name=names[0];engine.vector_fields={'indexes_embedding':1024}
    engine.has_build_index={name:True for name in names};engine.auto_update_mapping=False;engine.recall_mode='dual'
    reranker=SearchDataInterface.__new__(SearchDataInterface)
    rows=[]
    for round_no in range(3):
        events.clear();start=time.perf_counter()
        docs,total=engine.search_multi(query,index_names=names,size=size,recall_mode='dual')
        wall=(time.perf_counter()-start)*1000
        identities=[(d.get('_index'),d.get('_id')) for d in docs]
        scores=[(d.get('_index'),d.get('_id'),reranker._cal_similarity('',query['vector']['value'],d,
            search_type='qa',data_type='text',use_synonyms=True)) for d in docs]
        scores.sort(key=lambda row:row[2],reverse=True)
        rows.append({'round':round_no,'wall_ms':wall,'native_requests':len(events),'http':list(events),
            'decoded_bytes':sum(e['decoded_bytes'] for e in events),'docs':len(docs),'total':total,
            'identity_order_sha256':hashlib.sha256(json.dumps(identities).encode()).hexdigest(),
            'top10_identity_sha256':hashlib.sha256(json.dumps([s[:2] for s in scores[:10]]).encode()).hexdigest()})
        time.sleep(3)
    print(json.dumps({'rows':rows,'reads':counter,'writes':0,'client_version':'7.10.0'}))
finally:client.close()
'''

REMOTE = DIAGNOSTIC[:DIAGNOSTIC.index('initial=snapshot()')] + r'''
import base64,subprocess,types
bundle=json.load(sys.stdin)
candidate=base64.b64decode(bundle['candidate'])
if hashlib.sha256(candidate).hexdigest()!=bundle['candidate_sha256']:raise RuntimeError('candidate_hash')
module=types.ModuleType('knowledge_interface_tools._es817_batch_candidate')
module.__package__='knowledge_interface_tools'
exec(compile(candidate,'<isolated-es817-native-batch>','exec'),module.__dict__)

def run_engine(impl,events,query,indexes,size,vector,label):
    events.clear();start=time.perf_counter()
    docs,total=impl.search_multi(copy.deepcopy(query),index_names=indexes,size=size,recall_mode='dual')
    elapsed=(time.perf_counter()-start)*1000
    identities=[(d.get('_index'),d.get('_id')) for d in docs]
    scores=[(d.get('_index'),d.get('_id'),reranker._cal_similarity('',vector,d,
        search_type='qa',data_type='text',use_synonyms=True)) for d in docs]
    scores.sort(key=lambda row:row[2],reverse=True)
    row={'variant':label,'wall_ms':elapsed,'native_requests':len(events),'total':total,'docs':len(docs),
        'decoded_bytes':sum(e['decoded_bytes'] for e in events),'http':copy.deepcopy(events),
        'identity_order_sha256':hashlib.sha256(json.dumps(identities).encode()).hexdigest(),
        'complete_source_sha256':hashlib.sha256(json.dumps(docs,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'rerank_score_sha256':hashlib.sha256(json.dumps(scores).encode()).hexdigest(),
        'top10_identity_sha256':hashlib.sha256(json.dumps([s[:2] for s in scores[:10]]).encode()).hexdigest(),
        'vector_instances':{field:sum(len(d.get(field) or [])==1024 for d in docs)
            for field in ['title_embedding','content_embedding']},
        'nested_vector_instances':sum(len(item.get('embedding') or [])==1024 for d in docs for item in d.get('indexes',[]))}
    rows.append(row)
    print(json.dumps({'event':'progress','variant':label,'wall_ms':elapsed,'decoded_bytes':row['decoded_bytes']}),flush=True)
    time.sleep(3)

initial=snapshot();report['before']=initial;report['candidate_sha256']=bundle['candidate_sha256']
reranker=SearchDataInterface.__new__(SearchDataInterface)
try:
    cfg=json.loads((root/'config/config_es_engine_es817.online.json').read_text())
    cfg['extra_params'].update(ensure_index_on_init=False,auto_update_mapping=False)
    for provider in cfg['providers'].values():provider.update(max_retries=0,retry_on_timeout=False,request_timeout=15)
    baseline=EsSearchInterfaceES8(config=cfg,ensure_index=False);engines.append(baseline)
    candidate=module.EsSearchInterfaceES8(config=cfg,router=baseline.router,ensure_index=False)
    embedding=AliEmbedding(json.loads((root/'config/config_for_search_index.json').read_text())['embedding_config_path'])
    attributes=[{'quality_level':['high'],'data_type':['qa'],'audit_result':[1,2,-1]},
                {'audit_result':[1,2],'data_type':['qa']}]
    for provider,indexes,budget,text in [('paas',['payoneer_olive'],2,'TikTok墨西哥保证金'),
        ('serverless',['mercado','mercado_mercado_janice'],40,'墨西哥怎么入驻')]:
        events=[];client=trace_node(baseline.get_client_by_index(indexes[0]),events)
        if not client.info()['version']['number'].startswith('8.17'):raise RuntimeError('new_version')
        for index in indexes:
            if not client.indices.exists(index=index):raise RuntimeError('existing_index_missing')
        vector=embedding.text2embedding(text).tolist();report['embedding_calls']+=1
        if len(vector)!=1024 or not all(math.isfinite(v) for v in vector):raise RuntimeError('invalid_vector')
        query={'query':text,'vector':{'value':vector},'attribute':attributes}
        for impl,label in [(baseline,'sequential1'),(candidate,'batch1'),(candidate,'batch2'),(baseline,'sequential2')]:
            run_engine(impl,events,query,indexes,budget*2,vector,provider+':'+label)
        group=rows[-4:]
        report.setdefault('equivalence',{})[provider]={k:len({row[k] for row in group})==1
            for k in ['identity_order_sha256','complete_source_sha256','rerank_score_sha256','top10_identity_sha256','total','docs']}
        if not all(report['equivalence'][provider].values()):raise RuntimeError('candidate_result_difference')
        if provider=='serverless':
            old=subprocess.run(['/root/miniconda3/envs/py38/bin/python','-c',base64.b64decode(bundle['old']).decode()],
                input=json.dumps({'query':query,'indexes':indexes,'size':budget*2}),text=True,capture_output=True,timeout=90)
            if old.returncode:raise RuntimeError('old_read_comparison_failed')
            report['old_serverless']=json.loads(old.stdout)
    report['passed']=True
except Exception as exc:
    report['passed']=False;report['error_type']=type(exc).__name__
    if isinstance(exc,RuntimeError):report['reason']=str(exc)
finally:
    for engine in engines:engine.router.close()
    report['native_http_reads']=calls;report['after']=snapshot()
    report['online_processes_unchanged']=initial['services']==report['after']['services']
    report['online_engine_unchanged']=initial['engine_sha256']==report['after']['engine_sha256']
    print(json.dumps({'event':'final','report':report},ensure_ascii=False),flush=True)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    source = (Path(__legacy_source_file__).resolve().parents[1] / 'knowledge_interface_tools/es8_search_interface.py').read_bytes()
    bundle = {'candidate': base64.b64encode(source).decode(), 'candidate_sha256': hashlib.sha256(source).hexdigest(),
              'old': base64.b64encode(OLD.encode()).decode()}
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'shenzhen-120',
               'cd /root/knowledge_database_builder && nice -n 15 .venv-es817/bin/python -c ' + shlex.quote(REMOTE)]
    result = subprocess.run(command, input=json.dumps(bundle), capture_output=True, text=True, timeout=280)
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    report = next((e['report'] for e in reversed(events) if e.get('event') == 'final'), None)
    if report is None:
        report = {'passed': False, 'returncode': result.returncode, 'final_evidence_missing': True}
    report['tool_sha256'] = hashlib.sha256(Path(__legacy_source_file__).read_bytes()).hexdigest()
    target = args.output / 'evidence.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    target.chmod(0o600)
    print(json.dumps({'passed': report['passed'], 'path': str(target), 'equivalence': report.get('equivalence'),
        'reason': report.get('reason'), 'rows': [{k: r[k] for k in ['variant','wall_ms','decoded_bytes','native_requests']}
            for r in report.get('rows',[])], 'old_serverless': report.get('old_serverless')}, ensure_ascii=False))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
