"""200 distinct read-only cases comparing frozen serial ES8 with native batching.

No deployment, service restart, persistent ES change, or remote file write.
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/es817_parallel_100_20261009.py')
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

BASELINE = 'c51f0d0f649b7b751c2522d9e6006e900debeb20'
BASELINE_SHA = 'd9a30277f6464d639a9255800506f8bc9fffeff062834e10cd1839d1df4cd9fc'
CANDIDATE_SHA = '9ed795c5b837e8f6b46360ca46e0181feb67b08a288362275efe985111bba223'

REMOTE = r'''
import asyncio,base64,copy,hashlib,importlib.util,json,logging,math,os,sys,time,types
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
import numpy as np
import psutil
from knowledge_interface_tools.search_index_data_interface import SearchDataInterface
root=Path('/root/knowledge_database_builder')
groups=[('paas','payoneer_olive','payoneer_olive_payoneer_olive'),
        ('paas','payoneer','payoneer_payoneer'),
        ('serverless','mercado','mercado_mercado_janice'),
        ('serverless','mercado_local','mercado_local_mercado_local_admin')]
allowed={name for provider,public,private in groups for name in [public,private]}
calls=0;violations=0;last_start=0;deadline=time.monotonic()+1800
events=[];requests=[];native_errors=[];engine=None;initial=None;guard_checked=0

def sha(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def snapshot():
    services=[]
    for p in psutil.process_iter(['pid','cmdline','create_time']):
        try:
            if any(str(a).endswith('knowledge_database_search_es.py') or str(a).endswith('off_task_control_service.py') for a in (p.info['cmdline'] or [])):
                services.append({'pid':p.pid,'created':p.create_time(),'cwd':p.cwd()})
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    paths=['knowledge_interface_tools/es8_search_interface.py','knowledge_interface_tools/search_index_data_interface.py',
        'knowledge_interface_tools/es8_client_router.py','knowledge_database_search_service/src/knowledge_database_search_es.py',
        'config/config_es_engine.json','config/config_es_engine_es817.online.json','config/config_for_search_index.json',
        'config/config_for_search_index_no_dup_payoneer.json']
    return {'services':sorted(services,key=lambda p:p['pid']),
        'file_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths},
        'load1':os.getloadavg()[0],'cpus':os.cpu_count(),'mem_available':psutil.virtual_memory().available}

def guard():
    global guard_checked,violations
    if violations:raise RuntimeError('probe_already_aborting')
    if calls>=1400 or time.monotonic()>deadline:raise RuntimeError('read_budget_or_deadline')
    if time.monotonic()-guard_checked<5:return
    state=snapshot();guard_checked=time.monotonic()
    if state['services']!=initial['services'] or state['file_sha256']!=initial['file_sha256']:
        violations+=1;raise RuntimeError('online_state_changed_abort_probe')
    if state['mem_available']<4*1024**3 or psutil.Process().memory_info().rss>768*1024**2:
        violations+=1;raise RuntimeError('probe_memory_guard')
    for pause in range(6):
        if os.getloadavg()[0]<state['cpus']*.5:return
        print(json.dumps({'event':'paused','reason':'host_load','seconds':10}),flush=True)
        time.sleep(10)
    violations+=1;raise RuntimeError('host_busy_abort_probe')

def trace_node(client):
    for node in client.transport.node_pool.all():
        original=node.perform_request
        def wrapped(method,target,*args,_original=original,**kwargs):
            global calls,last_start,violations
            try:
                guard()
                url=urlsplit(target);path=url.path
                body=kwargs.get('body',args[0] if args else None)
                plan=[]
                ok=(method=='GET' and path=='/') or (method=='HEAD' and path[1:] in allowed)
                if method=='POST' and path=='/_msearch':
                    if parse_qs(url.query).get('max_concurrent_searches')!=['2']:raise RuntimeError('unbounded_batch')
                    items=[json.loads(line) for line in body.splitlines() if line.strip()]
                    if len(items)%2:raise RuntimeError('odd_batch')
                    for header,entry in zip(items[::2],items[1::2]):
                        if header.get('index') not in allowed or not 0<=entry.get('size',10)<=150:raise RuntimeError('bad_batch_scope')
                        plan.append([header['index'],sha(entry)])
                    ok=True
                elif method=='POST' and any(path=='/'+name+'/_search' for name in allowed):
                    entry=json.loads(body)
                    if not 0<=entry.get('size',10)<=150:raise RuntimeError('bad_search_size')
                    plan.append([path.strip('/').split('/')[0],sha(entry)]);ok=True
                if not ok:raise RuntimeError('outside_exact_read_scope')
                time.sleep(max(0,0.5-(time.monotonic()-last_start)))
                last_start=time.monotonic();calls+=1
                response=_original(method,target,*args,**kwargs)
                if len(response.body)>64*1024**2:raise RuntimeError('response_size_guard')
                payload=json.loads(response.body) if response.body else {}
                subs=payload.get('responses',[payload]) if method=='POST' else []
                invalid=sum(bool(s.get('error') or s.get('timed_out') or (s.get('_shards') or {}).get('failed')) for s in subs)
                if path=='/_msearch' and len(subs)!=len(plan):invalid+=1
                events.append({'method':method,'path':path,'status':response.meta.status,'network_ms':response.meta.duration*1000,
                    'decoded_bytes':len(response.body),'subsearches':len(subs),'invalid_subsearches':invalid,
                    'took_ms':[s.get('took') for s in subs]})
                requests.extend(plan)
                return response
            except Exception as exc:
                native_errors.append({'type':type(exc).__name__,
                    'reason':str(exc) if isinstance(exc,RuntimeError) else None,
                    'status':getattr(getattr(exc,'meta',None),'status',None)})
                violations+=1;raise
        node.perform_request=wrapped
    return client

def prepare_cases():
    cases=[];seen={'paas':set(),'serverless':set()};preflight=[]
    for provider,public,private in groups:
        client=engine.get_client_by_index(public)
        if not client.indices.exists(index=public):raise RuntimeError('public_index_missing:'+public)
        private_exists=bool(client.indices.exists(index=private))
        response=client.search(index=public,size=150,sort=['_doc'],
            source_includes=['title','title_embedding','primary_category'],
            query={'bool':{'filter':[{'term':{'data_type':'qa'}},{'terms':{'audit_result':[1,2]}}],
                           'must_not':[{'term':{'del_flag':1}}]}}).body
        if response.get('timed_out') or (response.get('_shards') or {}).get('failed'):raise RuntimeError('incomplete_sample')
        valid=[]
        for hit in response.get('hits',{}).get('hits',[]):
            source=hit.get('_source') or {};text=source.get('title');vector=source.get('title_embedding')
            if not isinstance(text,str) or not 4<=len(text)<=300 or not isinstance(vector,list) or len(vector)!=1024:
                continue
            if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in vector) or not any(vector):continue
            if text in seen[provider]:continue
            seen[provider].add(text);valid.append((hit,text,vector))
        valid.sort(key=lambda row:sha(row[1]))
        if len(valid)<50:raise RuntimeError('insufficient_distinct_valid_queries:'+public)
        preflight.append({'provider':provider,'public':public,'private':private,'private_exists':private_exists,
            'sampling_limit':150,'sampled_hits':len(response['hits']['hits']),'eligible_queries':len(valid)})
        for i,(hit,text,vector) in enumerate(valid[:50]):
            kind='segment' if i%10 in [1,7] else 'qa'
            condition=None if i%4==0 and kind=='qa' else [{'data_type':[kind],'audit_result':[1,2,-1]}]
            category=(hit.get('_source') or {}).get('primary_category') or {}
            category_field=None
            if i%5==2:
                for field in ['category_ids','category_path']:
                    if category.get(field):category_field=field;break
                if category_field:
                    if condition is None:condition=[{'data_type':[kind],'audit_result':[1,2,-1]}]
                    condition[0][category_field]=copy.deepcopy(category[category_field])
            names=[public] if i%4==0 or not private_exists else ([public,private] if i%2==0 else [private,public])
            cases.append({'case':provider+'-'+str(sum(c['provider']==provider for c in cases)+1).zfill(3),
                'provider':provider,'public':public,'query':text,'query_sha256':sha(text),'vector':vector,
                'vector_sha256':sha(vector),'source_id_sha256':sha(hit['_id']),
                'indexes':names,'top_k':[2,5,10,20,40][i%5], 'search_type':kind,
                'condition':condition,'category_field':category_field,'use_synonyms':i%3!=1,
                'score_threshold':0.4 if i%2==0 else 0.6})
    for provider in ['paas','serverless']:
        subset=[c for c in cases if c['provider']==provider]
        if len(subset)!=100 or len({c['query_sha256'] for c in subset})!=100:raise RuntimeError('case_cardinality')
    return cases,preflight

class FixedEmbedding:
    def text2embedding(self,text):
        if text!=self.text:raise RuntimeError('embedding_input_changed')
        return np.asarray(self.vector,dtype=float).copy()

class CaptureEngine:
    def search_multi(self,*args,**kwargs):
        docs,total=self.actual.search_multi(*args,**kwargs)
        self.raw_docs=copy.deepcopy(docs);self.total=total;self.business_docs=docs
        return docs,total

def run_variant(actual,case,label):
    events.clear();requests.clear();start=time.perf_counter();before_violations=violations
    capture=CaptureEngine();capture.actual=actual;capture.raw_docs=None;capture.total=None
    embedding=FixedEmbedding();embedding.text=case['query'];embedding.vector=case['vector']
    business=SearchDataInterface.__new__(SearchDataInterface)
    business.engine=capture;business.embedding_tools=embedding;business.multimodal_prefix=business_config.get('multimodal_prefix','')
    service.SEARCH_DATA_INTERFACE=business
    request_kwargs={'text':case['query'],'index_names':','.join(case['indexes']),
        'top_k':case['top_k'],'search_type':case['search_type'],'data_type':'text',
        'use_synonyms':case['use_synonyms'],'score_threshold':case['score_threshold']}
    if case['condition'] is not None:request_kwargs['condition_dicts']=copy.deepcopy(case['condition'])
    request=service.SearchRequest(**request_kwargs)
    result=asyncio.run(service.search(request)).model_dump(mode='json')
    elapsed=(time.perf_counter()-start)*1000
    if capture.raw_docs is None or any(r.get('q')=='检索结果错误' for r in result['results']):raise RuntimeError('handler_failed')
    if violations!=before_violations:raise RuntimeError('read_guard_or_transport_failure')
    for doc in capture.business_docs:
        if not math.isfinite(float(doc.get('similarity',0))):raise RuntimeError('nonfinite_similarity')
    raw=capture.raw_docs
    identities=[(d.get('_index'),d.get('_id')) for d in raw]
    source=[{k:v for k,v in d.items() if k not in ['_index','_id','score']} for d in raw]
    vectors={}
    for field in ['title_embedding','content_embedding','indexes','image_indexes']:
        values=[d.get(field) for d in raw]
        count=sum(len(d.get(field) or [])==1024 for d in raw) if field.endswith('_embedding') else sum(
            len(item.get('embedding') or [])==1024 for d in raw for item in (d.get(field) or []) if isinstance(item,dict))
        vectors[field]={'sha256':sha(values),'instances':count}
    row={'label':label,'wall_ms_instrumented':elapsed,'native_reads':len(events),'http':copy.deepcopy(events),
        'requests':copy.deepcopy(requests),'requests_sha256':sha(requests),'docs':len(raw),'total':capture.total,
        'identities_sha256':sha(identities),'full_engine_docs_sha256':sha(raw),'complete_source_sha256':sha(source),
        'recall_scores_sha256':sha([d.get('score') for d in raw]),'vectors':vectors,
        'similarity_sha256':sha([d.get('similarity') for d in capture.business_docs]),
        'business_docs_sha256':sha(capture.business_docs),'final_response_sha256':sha(result),
        'final_results':len(result['results']),'invalid_subsearches':sum(e['invalid_subsearches'] for e in events)}
    private={'engine_docs':raw,'business_docs':capture.business_docs,'response':result}
    return row,private

def compare(a,b,private_a,private_b):
    fields=['requests_sha256','identities_sha256','full_engine_docs_sha256','complete_source_sha256',
        'recall_scores_sha256','similarity_sha256','business_docs_sha256','final_response_sha256','total','docs','final_results','vectors']
    equality={key:a[key]==b[key] for key in fields}
    details=[]
    before={(d.get('_index'),d.get('_id')):d for d in private_a['engine_docs']}
    after={(d.get('_index'),d.get('_id')):d for d in private_b['engine_docs']}
    for identity in before.keys()&after.keys():
        changed=[field for field in sorted(before[identity].keys()|after[identity].keys())
                 if before[identity].get(field)!=after[identity].get(field)]
        if changed:details.append({'identity_sha256':sha(identity),'changed_fields':changed})
    score_deltas=[abs(float(x.get('score') or 0)-float(after[key].get('score') or 0)) for key,x in before.items() if key in after]
    similarity_a={(d.get('_index'),d.get('_id')):d.get('similarity') for d in private_a['business_docs']}
    similarity_b={(d.get('_index'),d.get('_id')):d.get('similarity') for d in private_b['business_docs']}
    similarity_deltas=[abs(float(value)-float(similarity_b[key])) for key,value in similarity_a.items() if key in similarity_b]
    return {'exact':all(equality.values()) and a['invalid_subsearches']==b['invalid_subsearches']==0,
        'equality':equality,'max_common_recall_score_delta':max(score_deltas,default=0),
        'max_common_similarity_delta':max(similarity_deltas,default=0),'changed_common_docs':details[:10],
        'old_only':len(before.keys()-after.keys()),'new_only':len(after.keys()-before.keys())}

def remote_main():
    global engine,initial,service,business_config
    bundle=json.load(sys.stdin);report={'rows':[],'persistent_ES_writes':0,'remote_file_writes':0,
        'embedding_calls':0,'service_HTTP_calls':0,'retries':0}
    engines={}
    try:
        classes={}
        for label in ['serial','parallel']:
            source=base64.b64decode(bundle[label])
            if hashlib.sha256(source).hexdigest()!=bundle[label+'_sha256']:raise RuntimeError('source_sha_mismatch')
            module=types.ModuleType('knowledge_interface_tools._paired_'+label);module.__package__='knowledge_interface_tools'
            exec(compile(source,'<isolated-'+label+'>','exec'),module.__dict__);classes[label]=module.EsSearchInterfaceES8
        spec=importlib.util.spec_from_file_location('_isolated_actual_old_search_service',root/'knowledge_database_search_service/src/knowledge_database_search_es.py')
        service=importlib.util.module_from_spec(spec);sys.modules[spec.name]=service;spec.loader.exec_module(service)
        logging.disable(logging.CRITICAL)
        initial=snapshot();report['before']=initial
        if initial['file_sha256']['knowledge_interface_tools/es8_search_interface.py']!=bundle['parallel_sha256']:
            raise RuntimeError('production_candidate_different')
        business_config=json.loads((root/'config/config_for_search_index.json').read_text())
        cfg=json.loads((root/'config/config_es_engine_es817.online.json').read_text())
        cfg['extra_params'].update(ensure_index_on_init=False,auto_update_mapping=False)
        for p in cfg['providers'].values():p.update(max_retries=0,retry_on_timeout=False,request_timeout=15)
        engine=classes['parallel'](config=cfg,ensure_index=False);engines['parallel']=engine
        engines['serial']=classes['serial'](config=cfg,router=engine.router,ensure_index=False)
        report['source_hashes']={label:bundle[label+'_sha256'] for label in ['serial','parallel']}
        for provider,public,private in groups:
            if provider in report.get('versions',{}):continue
            client=trace_node(engine.get_client_by_index(public));info=client.info()
            version=info['version']['number']
            if not version.startswith('8.17.'):raise RuntimeError('wrong_deployment_version')
            report.setdefault('versions',{})[provider]=version
        cases,preflight=prepare_cases();report['preflight']=preflight
        print(json.dumps({'event':'prepared','cases':len(cases),'preflight':preflight}),flush=True)
        mismatch_retries=0
        for n,case in enumerate(cases):
            report['current_case']={k:v for k,v in case.items() if k not in ['query','vector','condition']}
            guard()
            results={};private={}
            order=['serial','parallel'] if n%2==0 else ['parallel','serial']
            for label in order:results[label],private[label]=run_variant(engines[label],case,label)
            comparison=compare(results['serial'],results['parallel'],private['serial'],private['parallel'])
            public_case={k:v for k,v in case.items() if k not in ['query','vector','condition']}
            public_case['condition_sha256']=sha(case['condition']);public_case['condition_fields']=sorted({k for c in (case['condition'] or []) for k in c})
            row={**public_case,'order':order,'runs':results,'comparison':comparison}
            if not comparison['exact']:
                print(json.dumps({'event':'private_failure','case':case['case'],'payload':{'input':case,'runs':private}},allow_nan=False),flush=True)
                if mismatch_retries<10:
                    mismatch_retries+=1;again={};private_again={}
                    for label in reversed(order):again[label],private_again[label]=run_variant(engines[label],case,label)
                    row['repeat_runs']=again
                    row['repeat_comparison']=compare(again['serial'],again['parallel'],private_again['serial'],private_again['parallel'])
                    row['within_serial_repeat_exact']=results['serial']['full_engine_docs_sha256']==again['serial']['full_engine_docs_sha256']
                    row['within_parallel_repeat_exact']=results['parallel']['full_engine_docs_sha256']==again['parallel']['full_engine_docs_sha256']
                    print(json.dumps({'event':'private_failure','case':case['case']+'-repeat','payload':{'input':case,'runs':private_again}},allow_nan=False),flush=True)
                del private
            report['rows'].append(row)
            print(json.dumps({'event':'case','row':row},allow_nan=False),flush=True)
            if (n+1)%10==0:
                print(json.dumps({'event':'progress','completed':n+1,'exact':sum(r['comparison']['exact'] for r in report['rows']),
                    'native_reads':calls,'provider':case['provider']}),flush=True)
            if violations:raise RuntimeError('native_scope_or_transport_violations')
        report['retries']=mismatch_retries
        report['passed']=len(report['rows'])==200 and all(r['comparison']['exact'] for r in report['rows'])
    except Exception as exc:
        report['passed']=False;report['error_type']=type(exc).__name__
        if isinstance(exc,RuntimeError):report['reason']=str(exc)
        if type(exc).__name__=='ValidationError':report['error_fields']=[{'loc':list(e['loc']),'type':e['type']} for e in exc.errors()]
    finally:
        if engine is not None:engine.router.close()
        report['native_http_reads']=calls;report['violations']=violations;report['native_errors']=native_errors[:20];report['after']=snapshot()
        report['online_state_unchanged']=initial is not None and initial['services']==report['after']['services'] and initial['file_sha256']==report['after']['file_sha256']
        report['provider_counts']={p:{'completed':sum(r['provider']==p for r in report['rows']),
            'first_pair_exact':sum(r['provider']==p and r['comparison']['exact'] for r in report['rows']),
            'repeat_exact':sum(r['provider']==p and r.get('repeat_comparison',{}).get('exact',False) for r in report['rows'])}
            for p in ['paas','serverless']}
        print(json.dumps({'event':'final','report':report},allow_nan=False),flush=True)

remote_main()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    args.private_output.mkdir(parents=True, mode=0o700, exist_ok=False)
    root = Path(__legacy_source_file__).resolve().parents[1]
    serial = subprocess.check_output(['git', 'show', BASELINE + ':knowledge_interface_tools/es8_search_interface.py'], cwd=root)
    parallel = (root / 'knowledge_interface_tools/es8_search_interface.py').read_bytes()
    if hashlib.sha256(serial).hexdigest() != BASELINE_SHA or hashlib.sha256(parallel).hexdigest() != CANDIDATE_SHA:
        raise RuntimeError('local engine baseline changed; review before testing')
    bundle = {'serial': base64.b64encode(serial).decode(), 'serial_sha256': BASELINE_SHA,
              'parallel': base64.b64encode(parallel).decode(), 'parallel_sha256': CANDIDATE_SHA}
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'shenzhen-120',
               'cd /root/knowledge_database_builder && nice -n 15 .venv-es817/bin/python -u -c ' + shlex.quote(REMOTE)]
    report = None
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as process:
        process.stdin.write(json.dumps(bundle)); process.stdin.close()
        with (args.output / 'cases.jsonl').open('x') as cases:
            for line in process.stdout:
                if not line.startswith('{'):
                    continue
                event = json.loads(line)
                if event['event'] == 'private_failure':
                    path = args.private_output / (event['case'] + '.json')
                    with path.open('x') as handle:
                        handle.write(json.dumps(event['payload'], ensure_ascii=False, allow_nan=False))
                    path.chmod(0o600)
                elif event['event'] == 'case':
                    cases.write(json.dumps(event['row'], ensure_ascii=False) + '\n'); cases.flush()
                elif event['event'] == 'final':
                    report = event['report']
                else:
                    print(json.dumps(event, ensure_ascii=False), flush=True)
        code = process.wait(timeout=30)
    if report is None:
        report = {'passed': False, 'returncode': code, 'final_evidence_missing': True}
    report['tool_sha256'] = hashlib.sha256(Path(__legacy_source_file__).read_bytes()).hexdigest()
    report['baseline_commit'] = BASELINE
    path = args.output / 'evidence.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'); path.chmod(0o600)
    print(json.dumps({'event': 'saved', 'passed': report['passed'], 'path': str(path),
                      'provider_counts': report.get('provider_counts'), 'reason': report.get('reason'),
                      'online_state_unchanged': report.get('online_state_unchanged')}, ensure_ascii=False), flush=True)
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
