"""Bounded native-client ES8 read experiment; never patches running services."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/es817_online_latency_diagnostic_20261009.py')
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

REMOTE = r'''
import copy,hashlib,json,logging,math,os,sys,time
from pathlib import Path
import psutil
from commons.embedding_tools import AliEmbedding
from knowledge_interface_tools.es8_search_interface import EsSearchInterfaceES8
from knowledge_interface_tools.search_index_data_interface import SearchDataInterface

logging.disable(logging.CRITICAL)
root=Path('/root/knowledge_database_builder')
allowed={'payoneer_olive','mercado','mercado_mercado_janice'}
calls=0
deadline=time.monotonic()+240
rows=[]
clients=[]
engines=[]
report={'writes':0,'service_api_calls':0,'embedding_calls':0,'rows':rows}

def snapshot():
    services=[]
    for p in psutil.process_iter(['pid','create_time','cmdline']):
        try:
            args=p.info['cmdline'] or []
            if any(a.endswith('knowledge_database_search_es.py') or a.endswith('off_task_control_service.py') for a in args):
                services.append({'pid':p.pid,'created':p.create_time(),'cwd':p.cwd()})
        except(psutil.NoSuchProcess,psutil.AccessDenied):pass
    return {'services':sorted(services,key=lambda p:p['pid']),'engine_sha256':hashlib.sha256(
        (root/'knowledge_interface_tools/es8_search_interface.py').read_bytes()).hexdigest(),
        'load1':os.getloadavg()[0],'cpus':os.cpu_count(),'memory_available':psutil.virtual_memory().available}

def trace_node(client,events):
    for node in client.transport.node_pool.all():
        original=node.perform_request
        def wrapped(method,target,*args,_original=original,**kwargs):
            global calls
            path=target.split('?',1)[0]
            approved=(method=='GET' and path=='/') or (method=='HEAD' and path[1:] in allowed)
            approved=approved or (method=='POST' and (path=='/_msearch' or any(path=='/'+i+'/_search' for i in allowed)))
            state=snapshot()
            if not approved or calls>=48 or time.monotonic()>deadline or state['load1']>=state['cpus']*.5 or state['memory_available']<4*1024**3 or state['services']!=initial['services'] or state['engine_sha256']!=initial['engine_sha256']:
                raise RuntimeError('scope_budget_or_host_guard')
            calls+=1
            response=_original(method,target,*args,**kwargs)
            if len(response.body)>64*1024**2:raise RuntimeError('response_size_guard')
            events.append({'method':method,'path':path,'network_ms':response.meta.duration*1000,
                'decoded_bytes':len(response.body),'content_length':response.meta.headers.get('content-length'),
                'content_encoding':response.meta.headers.get('content-encoding'),'status':response.meta.status})
            return response
        node.perform_request=wrapped
    return client

def metric(response,index,route,vector):
    shards=response.get('_shards') or {}
    if response.get('error') or response.get('timed_out') or shards.get('failed',0) or shards.get('successful',0)!=shards.get('total',0):
        raise RuntimeError('incomplete_native_response')
    hits=response.get('hits',{}).get('hits',[])
    identities=[(h.get('_index'),h.get('_id')) for h in hits]
    scores=[]
    vectors={'title':0,'content':0,'nested':0,'image':0}
    for hit in hits:
        source=hit.get('_source')
        if isinstance(source,dict):
            for field,label in [('title_embedding','title'),('content_embedding','content')]:
                vectors[label]+=int(len(source.get(field) or [])==1024)
            for field,label in [('indexes','nested'),('image_indexes','image')]:
                vectors[label]+=sum(len(e.get('embedding') or [])==1024 for e in (source.get(field) or []) if isinstance(e,dict))
            score=reranker._cal_similarity('',vector,source,search_type='qa',data_type='text',use_synonyms=True)
            if not math.isfinite(score):raise RuntimeError('nonfinite_rerank_score')
            scores.append([hit.get('_id'),round(score,12)])
    inner=[h for hit in hits for section in (hit.get('inner_hits') or {}).values() for h in section.get('hits',{}).get('hits',[])]
    return {'index':index,'route':route,'took_ms':response.get('took'),'hits':len(hits),'shards':shards,
        'identity_order_sha256':hashlib.sha256(json.dumps(identities).encode()).hexdigest(),
        'complete_source_sha256':hashlib.sha256(json.dumps([h.get('_source') for h in hits],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'rerank_score_sha256':hashlib.sha256(json.dumps(scores).encode()).hexdigest() if scores else None,
        'vector_instances':vectors,'empty_inner_sources':sum(not h.get('_source') for h in inner),'inner_hits':len(inner)}

def run_plan(client,events,plan,vector,label,batched=False):
    events.clear()
    start=time.perf_counter()
    if batched:
        searches=[]
        for index,route,body in plan:searches.extend([{'index':index},body])
        response=client.msearch(searches=searches,max_concurrent_searches=2)
        values=response.body.get('responses',[])
        if len(values)!=len(plan):raise RuntimeError('msearch_cardinality')
    else:
        values=[client.search(index=index,body=body).body for index,route,body in plan]
    elapsed=(time.perf_counter()-start)*1000
    metrics=[metric(value,index,route,vector) for value,(index,route,body) in zip(values,plan)]
    row={'variant':label,'wall_ms':elapsed,'native_requests':len(events),'network_ms_sum':sum(e['network_ms'] for e in events),
        'decoded_bytes':sum(e['decoded_bytes'] for e in events),'http':copy.deepcopy(events),'routes':metrics}
    rows.append(row)
    print(json.dumps({'event':'progress','variant':label,'wall_ms':elapsed,'decoded_bytes':row['decoded_bytes']}),flush=True)
    time.sleep(3)

initial=snapshot()
report['before']=initial
reranker=SearchDataInterface.__new__(SearchDataInterface)
try:
    cfg=json.loads((root/'config/config_es_engine_es817.online.json').read_text())
    cfg['extra_params'].update(ensure_index_on_init=False,auto_update_mapping=False)
    for provider in cfg['providers'].values():provider.update(max_retries=0,retry_on_timeout=False,request_timeout=15)
    engine=EsSearchInterfaceES8(config=cfg,ensure_index=False)
    engines.append(engine)
    events_by_provider={}
    for provider,index in [('paas','payoneer_olive'),('serverless','mercado')]:
        events=[]
        client=trace_node(engine.get_client_by_index(index),events)
        clients.append(client);events_by_provider[provider]=events
        if not client.info()['version']['number'].startswith('8.17.'):raise RuntimeError('wrong_es_version')
    for index in sorted(allowed):
        if not engine.get_client_by_index(index).indices.exists(index=index):raise RuntimeError('missing_existing_index')
    business=json.loads((root/'config/config_for_search_index.json').read_text())
    embedding=AliEmbedding(business['embedding_config_path'])
    attributes=[{'quality_level':['high'],'data_type':['qa'],'audit_result':[1,2,-1]},
                {'audit_result':[1,2],'data_type':['qa']}]
    cases=[('paas',['payoneer_olive'],2,'TikTok墨西哥保证金'),
           ('serverless',['mercado','mercado_mercado_janice'],40,'墨西哥怎么入驻')]
    for provider,indexes,size,text in cases:
        vector=embedding.text2embedding(text).tolist();report['embedding_calls']+=1
        if len(vector)!=1024 or not all(math.isfinite(v) for v in vector):raise RuntimeError('invalid_query_vector')
        query={'query':text,'vector':{'value':vector},'attribute':attributes}
        client=engine.get_client_by_index(indexes[0]);events=events_by_provider[provider]
        plan=[(index,route,{'query':engine._build_search_query(query,include_text=route=='bm25',
            include_vector=route=='vector',vector_k=size,with_inner_hits=route=='vector'),'size':size})
            for index in indexes for route in ['bm25','vector']]
        for variant,batched in [('seq1',False),('batch1',True),('batch2',True),('seq2',False)]:
            run_plan(client,events,plan,vector,provider+':'+variant,batched)
        if provider=='serverless':
            small=[(index,route,{'query':engine._build_search_query(query,include_text=route=='bm25',
                include_vector=route=='vector',vector_k=5,with_inner_hits=route=='vector'),'size':5})
                for index in indexes for route in ['bm25','vector']]
            run_plan(client,events,small,vector,provider+':small5')
        only_vector=[copy.deepcopy(plan[1])]
        only_vector[0][2]['_source']=False
        run_plan(client,events,only_vector,vector,provider+':diagnostic_source_false')
        gzipcfg=copy.deepcopy(cfg);gzipcfg['providers'][provider]['http_compress']=True
        gzipengine=EsSearchInterfaceES8(config=gzipcfg,ensure_index=False)
        engines.append(gzipengine)
        gzip_events=[]
        gzipclient=trace_node(gzipengine.get_client_by_index(indexes[0]),gzip_events);clients.append(gzipclient)
        run_plan(gzipclient,gzip_events,[plan[1]],vector,provider+':diagnostic_gzip_full_source')
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
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'shenzhen-120',
               'cd /root/knowledge_database_builder && nice -n 15 .venv-es817/bin/python -c ' + shlex.quote(REMOTE)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=280)
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    report = next((e['report'] for e in reversed(events) if e.get('event') == 'final'), None)
    if report is None:
        report = {'passed': False, 'process_returncode': result.returncode, 'final_evidence_missing': True}
    report['tool_sha256'] = hashlib.sha256(Path(__legacy_source_file__).read_bytes()).hexdigest()
    target = args.output / 'evidence.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    target.chmod(0o600)
    print(json.dumps({'passed': report['passed'], 'native_http_reads': report.get('native_http_reads'),
                     'rows': [{k: r[k] for k in ('variant','wall_ms','decoded_bytes')} for r in report.get('rows',[])],
                     'path': str(target)}, ensure_ascii=False), flush=True)
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
