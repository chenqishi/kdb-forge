"""Actual ES7/ES8 knowledge comparison and strict source-policy oracle; read-only."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/es817_source_fix_validation_20261009.py')
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from es817_parallel_100_20261009 import REMOTE as ORIGINAL

PREFIX = ORIGINAL.rsplit('\nremote_main()', 1)[0]
OLD = PREFIX + r'''
import inspect
from elasticsearch import Elasticsearch
old_events=[];old_requests=[];old_reads=0;old_last=0;old_errors=0

def trace_old(connection):
    original=connection.perform_request;signature=inspect.signature(original)
    def wrapped(method,url,*args,**kwargs):
        global old_reads,old_last,old_errors
        try:
            guard()
            if old_reads>=450:raise RuntimeError('legacy_read_budget')
            bound=signature.bind(method,url,*args,**kwargs).arguments
            path=urlsplit(url).path;body=bound.get('body') or b'';plan=[]
            ok=(method=='GET' and path=='/') or (method=='HEAD' and path[1:] in allowed)
            if method=='POST' and path=='/_msearch':
                parts=[json.loads(line) for line in body.splitlines() if line.strip()]
                if len(parts)%2:raise RuntimeError('odd_old_batch')
                for h,b in zip(parts[::2],parts[1::2]):
                    if h.get('index') not in allowed or not 0<=b.get('size',10)<=80:raise RuntimeError('old_batch_scope')
                    plan.append([h['index'],sha(b)])
                ok=True
            if method=='POST' and path in {'/'+name+'/_search' for name in allowed}:
                b=json.loads(body)
                if not 0<=b.get('size',10)<=80:raise RuntimeError('old_search_budget')
                plan.append([path.split('/')[1],sha(b)]);ok=True
            if not ok:raise RuntimeError('old_persistent_or_outside_scope')
            time.sleep(max(0,.5-(time.monotonic()-old_last)));old_last=time.monotonic();old_reads+=1
            response=original(method,url,*args,**kwargs)
            data=response[2];raw=data.encode() if isinstance(data,str) else data
            if len(raw)>64*1024**2:raise RuntimeError('old_response_size')
            payload=json.loads(raw) if raw else {};subs=payload.get('responses',[payload]) if method=='POST' else []
            invalid=sum(bool(s.get('error') or s.get('timed_out') or (s.get('_shards') or {}).get('failed')) for s in subs)
            old_events.append({'method':method,'path':path,'status':response[0],'decoded_bytes':len(raw),'invalid_subsearches':invalid})
            old_requests.extend(plan)
            if invalid:raise RuntimeError('old_incomplete_search')
            return response
        except Exception:
            old_errors+=1;raise
    connection.perform_request=wrapped

def old_main():
    global initial
    logging.disable(logging.CRITICAL);initial=snapshot();client=None
    try:
        incoming=json.loads(sys.stdin.readline());source=base64.b64decode(incoming['source'])
        if hashlib.sha256(source).hexdigest()!=incoming['sha256']:raise RuntimeError('old_source_hash')
        module=types.ModuleType('knowledge_interface_tools._actual_f873_legacy');module.__package__='knowledge_interface_tools'
        exec(compile(source,'<f873a593-real-old-engine>','exec'),module.__dict__)
        cfg=json.loads(Path('/root/dify/knowledge_database_builder/config/config_es_engine.json').read_text())
        client=Elasticsearch(cfg['hosts'],http_auth=(cfg['username'],cfg['password']),timeout=15,max_retries=0,retry_on_timeout=False)
        for c in client.transport.connection_pool.connections:trace_old(c)
        if not client.info()['version']['number'].startswith('7.10.'):raise RuntimeError('old_version_mismatch')
        for name in sorted(allowed):
            if not client.indices.exists(index=name):raise RuntimeError('old_index_missing:'+name)
        engine=module.EsSearchInterfaceOri.__new__(module.EsSearchInterfaceOri)
        engine.es=client;engine.index_name='mercado';engine.has_build_index={name:True for name in allowed}
        engine.vector_fields=cfg.get('vector_fields') or {'indexes_embedding':1024};engine.recall_mode='dual';engine.auto_update_mapping=False
        native_msearch=client.msearch
        def bounded_old_msearch(*args,**kwargs):
            params=dict(kwargs.pop('params',{}) or {});params['max_concurrent_searches']=2
            return native_msearch(*args,params=params,**kwargs)
        client.msearch=bounded_old_msearch
        includes=engine._build_nested_vector_clause([.1]*1024,with_inner_hits=True)['nested']['inner_hits']['_source']['includes']
        print(json.dumps({'kind':'ready','policy':{'excludes':module._LEAN_SOURCE_EXCLUDES,'includes':includes},'preflight_reads':old_reads}),flush=True)
        for line in sys.stdin:
            message=json.loads(line)
            if message.get('stop'):break
            old_events.clear();old_requests.clear();before_errors=old_errors
            docs,total=engine.search_multi(message['query'],index_names=message['indexes'],size=message['size'],recall_mode='dual')
            if old_errors!=before_errors:raise RuntimeError('legacy_query_error_not_empty_success')
            print(json.dumps({'kind':'result','docs':docs,'total':total,'events':old_events,'requests':old_requests,'reads':old_reads},allow_nan=False),flush=True)
    except Exception as exc:
        print(json.dumps({'kind':'error','type':type(exc).__name__,'reason':str(exc) if isinstance(exc,RuntimeError) else None}),flush=True)
    finally:
        if client is not None:client.close()

old_main()
'''

REMOTE = PREFIX + r'''
import subprocess
oracle_enabled=False;policy=None;old_process=None;old_read_total=0

def qualify_inner(value):
    if isinstance(value,dict):
        nested=value.get('nested')
        if isinstance(nested,dict) and nested.get('inner_hits'):
            path=nested['path']
            nested['inner_hits']['_source']={'includes':policy['includes'] if path=='indexes' else [path+'.text',path+'.embedding']}
        for child in value.values():qualify_inner(child)
    elif isinstance(value,list):
        for child in value:qualify_inner(child)

class OldProxy:
    def search_multi(self,query,index_names=None,size=10,**kwargs):
        global old_read_total
        data=copy.deepcopy(query)
        if isinstance((data.get('vector') or {}).get('value'),np.ndarray):data['vector']['value']=data['vector']['value'].tolist()
        old_process.stdin.write(json.dumps({'query':data,'indexes':index_names,'size':size},allow_nan=False)+'\n');old_process.stdin.flush()
        while True:
            line=old_process.stdout.readline()
            if not line:raise RuntimeError('legacy_child_closed')
            message=json.loads(line)
            if message.get('kind')=='result':break
            if message.get('event')=='paused':
                print(json.dumps({'event':'old_paused','reason':'host_load'}),flush=True);continue
            raise RuntimeError('legacy_child_error:'+str(message.get('reason') or message.get('type')))
        old_read_total=message['reads'];events.extend(message['events']);requests.extend(message['requests'])
        return message['docs'],message['total']

def knowledge_compare(old,new):
    a=old['response']['results'];b=new['response']['results']
    ids_a=[(d.get('dataset'),d.get('id')) for d in a];ids_b=[(d.get('dataset'),d.get('id')) for d in b]
    map_a={key:d for key,d in zip(ids_a,a)};map_b={key:d for key,d in zip(ids_b,b)}
    changed=[]
    for key in map_a.keys()&map_b.keys():
        fields=[field for field in sorted(map_a[key].keys()|map_b[key].keys()) if field!='score' and map_a[key].get(field)!=map_b[key].get(field)]
        if fields:changed.append({'id_sha256':sha(key),'fields':fields})
    raw_a={(d.get('_index'),d.get('_id')):d for d in old['engine_docs']};raw_b={(d.get('_index'),d.get('_id')):d for d in new['engine_docs']}
    common=raw_a.keys()&raw_b.keys();content_changes=[];root_changes=[]
    for key in common:
        left=copy.deepcopy(raw_a[key]);right=copy.deepcopy(raw_b[key])
        for doc in [left,right]:
            for field in ['_id','_index','score','title_embedding','content_embedding']:doc.pop(field,None)
            for path in ['indexes','image_indexes']:
                for item in doc.get(path,[]) or []:
                    if isinstance(item,dict):item.pop('embedding',None)
        if sha(left)!=sha(right):content_changes.append({'id_sha256':sha(key),'fields':[f for f in sorted(left.keys()|right.keys()) if left.get(f)!=right.get(f)]})
        if any(sha(raw_a[key].get(f))!=sha(raw_b[key].get(f)) for f in ['title_embedding','content_embedding']):root_changes.append(sha(key))
    score_delta=max((abs(map_a[key]['score']-map_b[key]['score']) for key in map_a.keys()&map_b.keys()),default=0)
    return {'ordered_knowledge_equal':ids_a==ids_b,'knowledge_set_equal':set(ids_a)==set(ids_b),'complete_final_response_equal':sha(old['response'])==sha(new['response']),
        'top1_equal':ids_a[:1]==ids_b[:1],'old_results':len(a),'new_results':len(b),'common_final_results':len(map_a.keys()&map_b.keys()),
        'old_only_final_ids_sha256':[sha(k) for k in ids_a if k not in map_b],'new_only_final_ids_sha256':[sha(k) for k in ids_b if k not in map_a],
        'changed_common_final_knowledge':changed,'max_common_final_score_delta':score_delta,
        'common_candidates':len(common),'changed_common_candidate_content':content_changes,'changed_root_vector_ids_sha256':root_changes,
        'old_candidate_count':len(raw_a),'new_candidate_count':len(raw_b),
        'old_only_candidate_ids_sha256':sorted(sha(k) for k in raw_a.keys()-raw_b.keys()),
        'new_only_candidate_ids_sha256':sorted(sha(k) for k in raw_b.keys()-raw_a.keys()),
        'old_only_final_in_new_candidates':[{'id_sha256':sha(k),'present':k in raw_b} for k in ids_a if k not in map_b],
        'new_only_final_in_old_candidates':[{'id_sha256':sha(k),'present':k in raw_a} for k in ids_b if k not in map_a]}

def source_fix_main():
    global engine,initial,service,business_config,oracle_enabled,policy,old_process,old_read_total
    logging.disable(logging.CRITICAL);bundle=json.load(sys.stdin);report={'rows':[],'persistent_ES_writes':0,'embedding_calls':0,'service_HTTP_calls':0}
    initial=snapshot();report['before']=initial;private_count=0
    try:
        if initial['file_sha256']['knowledge_interface_tools/es8_search_interface.py']!=bundle['pre_sha256']:raise RuntimeError('online_engine_changed')
        classes={}
        for label in ['pre','fixed']:
            source=base64.b64decode(bundle[label]);
            if hashlib.sha256(source).hexdigest()!=bundle[label+'_sha256']:raise RuntimeError('implementation_bundle_hash')
            module=types.ModuleType('knowledge_interface_tools._source_fix_'+label);module.__package__='knowledge_interface_tools'
            exec(compile(source,'<isolated-source-fix-'+label+'>','exec'),module.__dict__);classes[label]=module.EsSearchInterfaceES8
        spec=importlib.util.spec_from_file_location('_isolated_source_fix_service',root/'knowledge_database_search_service/src/knowledge_database_search_es.py')
        service=importlib.util.module_from_spec(spec);sys.modules[spec.name]=service;spec.loader.exec_module(service);logging.disable(logging.CRITICAL)
        business_config=json.loads((root/'config/config_for_search_index.json').read_text())
        cfg=json.loads((root/'config/config_es_engine_es817.online.json').read_text());cfg['extra_params'].update(ensure_index_on_init=False,auto_update_mapping=False)
        for p in cfg['providers'].values():p.update(max_retries=0,retry_on_timeout=False,request_timeout=15)
        engine=classes['fixed'](config=cfg,ensure_index=False);reference=classes['pre'](config=cfg,router=engine.router,ensure_index=False)
        old_process=subprocess.Popen(['/root/miniconda3/envs/py38/bin/python','-u','-c',base64.b64decode(bundle['old_tool']).decode()],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        old_process.stdin.write(json.dumps({'source':bundle['legacy'],'sha256':bundle['legacy_sha256']})+'\n');old_process.stdin.flush()
        ready=json.loads(old_process.stdout.readline())
        if ready.get('kind')!='ready':raise RuntimeError('legacy_preflight_failed:'+str(ready.get('reason') or ready.get('type')))
        policy=ready['policy'];old_read_total=ready['preflight_reads'];report['legacy_policy']=policy
        for provider,public,private in groups:
            client=engine.get_client_by_index(public)
            if provider not in report.get('versions',{}):
                trace_node(client);version=client.info()['version']['number']
                if not version.startswith('8.17.'):raise RuntimeError('new_version_mismatch')
                report.setdefault('versions',{})[provider]=version
                native=client.msearch
                def policy_msearch(*,searches,_native=native,**kwargs):
                    if oracle_enabled:
                        searches=copy.deepcopy(searches)
                        for body in searches[1::2]:
                            body['_source']={'excludes':list(policy['excludes'])};qualify_inner(body)
                    return _native(searches=searches,**kwargs)
                client.msearch=policy_msearch
            for name in [public,private]:
                if not client.indices.exists(index=name):raise RuntimeError('new_index_missing:'+name)
        print(json.dumps({'event':'prepared','cases':len(bundle['cases']),'old_sdk':'7.10.0','new_versions':report['versions']}),flush=True)
        old_proxy=OldProxy()
        for n,case in enumerate(bundle['cases']):
            report['current_case']=case['case'];guard();results={};private={}
            for label in (['oracle','fixed','old7'] if n%2==0 else ['old7','fixed','oracle']):
                oracle_enabled=label=='oracle'
                actual=reference if label=='oracle' else (engine if label=='fixed' else old_proxy)
                results[label],private[label]=run_variant(actual,case,label)
            oracle=compare(results['oracle'],results['fixed'],private['oracle'],private['fixed'])
            knowledge=knowledge_compare(private['old7'],private['fixed'])
            public_case={k:v for k,v in case.items() if k not in ['query','vector','condition']}
            row={**public_case,'condition_sha256':sha(case['condition']),'runs':results,'source_policy_oracle':oracle,'actual_es7_vs_es8':knowledge}
            if (not oracle['exact'] or not knowledge['ordered_knowledge_equal'] or knowledge['changed_common_final_knowledge']) and private_count<12:
                private_count+=1
                print(json.dumps({'event':'private_failure','case':case['case'],'payload':{'input':case,'old7':private['old7'],'fixed':private['fixed'],'oracle':private['oracle']}},allow_nan=False),flush=True)
            report['rows'].append(row);print(json.dumps({'event':'case','row':row},allow_nan=False),flush=True)
            if not oracle['exact']:raise RuntimeError('fixed_differs_from_actual_old_source_policy_oracle')
            if (n+1)%10==0:
                print(json.dumps({'event':'progress','completed':n+1,'source_policy_exact':sum(r['source_policy_oracle']['exact'] for r in report['rows']),
                    'old_new_order_equal':sum(r['actual_es7_vs_es8']['ordered_knowledge_equal'] for r in report['rows']),
                    'old_new_top1_equal':sum(r['actual_es7_vs_es8']['top1_equal'] for r in report['rows']),
                    'native8_reads':calls,'native7_reads':old_read_total}),flush=True)
        report['completed']=len(report['rows'])==len(bundle['cases'])
    except Exception as exc:
        report['completed']=False;report['error_type']=type(exc).__name__
        if isinstance(exc,RuntimeError):report['reason']=str(exc)
    finally:
        if old_process is not None:
            try:
                if old_process.poll() is None:
                    old_process.stdin.write('{"stop":true}\n');old_process.stdin.flush();old_process.stdin.close();old_process.wait(timeout=20)
            except (BrokenPipeError,subprocess.TimeoutExpired):
                old_process.terminate();old_process.wait(timeout=10)
        if engine is not None:engine.router.close()
        report['native8_reads']=calls;report['native7_reads']=old_read_total;report['native_errors']=native_errors[:10];report['violations']=violations
        report['after']=snapshot();report['online_state_unchanged']=all(initial[k]==report['after'][k] for k in ['services','file_sha256'])
        report['implementation_hashes']={k:bundle[k+'_sha256'] for k in ['pre','fixed','legacy']}
        report['private_example_count']=private_count
        report['provider_counts']={p:{'completed':sum(r['provider']==p for r in report['rows']),
            'source_policy_exact':sum(r['provider']==p and r['source_policy_oracle']['exact'] for r in report['rows']),
            'old_new_order_equal':sum(r['provider']==p and r['actual_es7_vs_es8']['ordered_knowledge_equal'] for r in report['rows']),
            'old_new_set_equal':sum(r['provider']==p and r['actual_es7_vs_es8']['knowledge_set_equal'] for r in report['rows']),
            'old_new_top1_equal':sum(r['provider']==p and r['actual_es7_vs_es8']['top1_equal'] for r in report['rows'])} for p in ['paas','serverless']}
        print(json.dumps({'event':'final','report':report},allow_nan=False),flush=True)

source_fix_main()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--case', action='append', default=[], help='Rerun at most three existing counterexamples')
    args = parser.parse_args()
    if args.fixture.stat().st_size > 8 * 1024 ** 2:
        raise ValueError('unexpectedly large fixture; use bounded workflow')
    with args.fixture.open() as handle:
        cases = json.load(handle)
    if len(cases) != 200:
        raise ValueError('verified 200-case fixture required')
    if args.case:
        if len(args.case) > 3 or len(set(args.case)) != len(args.case):
            raise ValueError('at most three unique counterexamples allowed')
        selected = [case for case in cases if case['case'] in args.case]
        if len(selected) != len(args.case):
            raise ValueError('counterexample not found in verified fixture')
        cases = selected
    root = Path(__legacy_source_file__).resolve().parents[1]
    pre = subprocess.check_output(['git', 'show', '12a86da7163c5136524a60730c6af476788933c5:knowledge_interface_tools/es8_search_interface.py'], cwd=root)
    fixed = (root / 'knowledge_interface_tools/es8_search_interface.py').read_bytes()
    legacy = subprocess.check_output(['git', 'show', 'f873a593:knowledge_interface_tools/es_search_interface.py'], cwd=root)
    bundle = {'cases': cases, 'old_tool': base64.b64encode(OLD.encode()).decode()}
    for label, source in [('pre', pre), ('fixed', fixed), ('legacy', legacy)]:
        bundle[label] = base64.b64encode(source).decode(); bundle[label + '_sha256'] = hashlib.sha256(source).hexdigest()
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    args.private_output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (args.private_output / '.gitignore').write_text('*\n')
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'shenzhen-120',
        'cd /root/knowledge_database_builder && PYTHONDONTWRITEBYTECODE=1 nice -n 15 .venv-es817/bin/python -u -c ' + shlex.quote(REMOTE)]
    report = None; private_bytes = 0
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as process:
        process.stdin.write(json.dumps(bundle, allow_nan=False)); process.stdin.close()
        with (args.output / 'cases.jsonl').open('x') as case_file:
            for line in process.stdout:
                if not line.startswith('{'):
                    continue
                event = json.loads(line)
                if event['event'] == 'private_failure':
                    data = json.dumps(event['payload'], ensure_ascii=False, allow_nan=False)
                    if private_bytes + len(data.encode()) <= 64 * 1024 ** 2:
                        target = args.private_output / (event['case'] + '.json')
                        with target.open('x') as handle:
                            handle.write(data)
                        target.chmod(0o600); private_bytes += len(data.encode())
                elif event['event'] == 'case':
                    case_file.write(json.dumps(event['row'], ensure_ascii=False, allow_nan=False) + '\n'); case_file.flush()
                elif event['event'] == 'final':
                    report = event['report']
                else:
                    print(json.dumps(event, ensure_ascii=False), flush=True)
        code = process.wait(timeout=30)
    if report is None:
        report = {'completed': False, 'returncode': code, 'final_evidence_missing': True}
    report['tool_sha256'] = hashlib.sha256(Path(__legacy_source_file__).read_bytes()).hexdigest()
    report['private_saved_bytes'] = private_bytes
    (args.output / 'evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: report.get(k) for k in ['completed', 'reason', 'provider_counts', 'native8_reads', 'native7_reads', 'online_state_unchanged']}, ensure_ascii=False))
    if not report['completed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
