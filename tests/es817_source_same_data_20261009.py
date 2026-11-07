"""Read-only ES7/8 comparison on a verified identical-source document subset."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/es817_source_same_data_20261009.py')
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from es817_source_fix_validation_20261009 import OLD as OLD_BASE, REMOTE as NEW_BASE

OLD = OLD_BASE[:OLD_BASE.index('def old_main():')] + r'''
def same_old_main():
    global initial
    logging.disable(logging.CRITICAL);initial=snapshot();client=None
    try:
        incoming=json.loads(sys.stdin.readline());source=base64.b64decode(incoming['source'])
        if hashlib.sha256(source).hexdigest()!=incoming['sha256']:raise RuntimeError('old_source_hash')
        module=types.ModuleType('knowledge_interface_tools._same_data_old');module.__package__='knowledge_interface_tools'
        exec(compile(source,'<real-f873-same-data>','exec'),module.__dict__)
        cfg=json.loads(Path('/root/dify/knowledge_database_builder/config/config_es_engine.json').read_text())
        client=Elasticsearch(cfg['hosts'],http_auth=(cfg['username'],cfg['password']),timeout=15,max_retries=0,retry_on_timeout=False)
        for c in client.transport.connection_pool.connections:trace_old(c)
        if not client.info()['version']['number'].startswith('7.10.'):raise RuntimeError('old_version')
        for name in sorted(allowed):
            if not client.indices.exists(index=name):raise RuntimeError('old_name_missing:'+name)
        engine=module.EsSearchInterfaceOri.__new__(module.EsSearchInterfaceOri)
        engine.es=client;engine.index_name='mercado';engine.has_build_index={name:True for name in allowed}
        engine.vector_fields=cfg.get('vector_fields') or {'indexes_embedding':1024};engine.recall_mode='dual';engine.auto_update_mapping=False
        native_msearch=client.msearch
        def bounded_old_msearch(*args,**kwargs):
            params=dict(kwargs.pop('params',{}) or {});params['max_concurrent_searches']=2
            return native_msearch(*args,params=params,**kwargs)
        client.msearch=bounded_old_msearch
        print(json.dumps({'kind':'ready','reads':old_reads}),flush=True)
        for line in sys.stdin:
            message=json.loads(line)
            if message.get('stop'):break
            old_events.clear();old_requests.clear();before_errors=old_errors
            if 'read_ids' in message:
                if len(message['read_ids'])>40 or message['index'] not in allowed:raise RuntimeError('id_source_read_budget')
                raw=client.search(index=message['index'],body={'query':{'ids':{'values':message['read_ids']}},'size':40})
                docs=raw.get('hits',{}).get('hits',[]);total=raw.get('hits',{}).get('total',{})
            else:docs,total=engine.search_multi(message['query'],index_names=message['indexes'],size=message['size'],recall_mode='dual')
            if old_errors!=before_errors or not any(e['method']=='POST' for e in old_events):raise RuntimeError('old_read_not_successful')
            print(json.dumps({'kind':'result','docs':docs,'total':total,'events':old_events,'requests':old_requests,'reads':old_reads},allow_nan=False),flush=True)
    except Exception as exc:
        print(json.dumps({'kind':'error','type':type(exc).__name__,'reason':str(exc) if isinstance(exc,RuntimeError) else None}),flush=True)
    finally:
        if client is not None:client.close()

same_old_main()
'''

REMOTE = NEW_BASE[:NEW_BASE.index('def source_fix_main():')] + r'''
def read_old(index,ids):
    global old_read_total
    old_process.stdin.write(json.dumps({'index':index,'read_ids':ids})+'\n');old_process.stdin.flush()
    message=json.loads(old_process.stdout.readline())
    if message.get('kind')!='result':raise RuntimeError('old_source_read_error:'+str(message.get('reason') or message.get('type')))
    old_read_total=message['reads'];return message['docs']

def controlled_main():
    global engine,initial,service,business_config,old_process,old_read_total
    logging.disable(logging.CRITICAL);bundle=json.load(sys.stdin);initial=snapshot()
    report={'before':initial,'pools':[],'rows':[],'persistent_ES_writes':0,'embedding_calls':0,'service_HTTP_calls':0}
    try:
        if initial['file_sha256']['knowledge_interface_tools/es8_search_interface.py']!=bundle['online_sha256']:raise RuntimeError('online_baseline_changed')
        source=base64.b64decode(bundle['fixed']);module=types.ModuleType('knowledge_interface_tools._same_data_fixed');module.__package__='knowledge_interface_tools'
        if hashlib.sha256(source).hexdigest()!=bundle['fixed_sha256']:raise RuntimeError('fixed_hash')
        exec(compile(source,'<actual-same-data-fixed>','exec'),module.__dict__)
        spec=importlib.util.spec_from_file_location('_same_data_actual_service',root/'knowledge_database_search_service/src/knowledge_database_search_es.py')
        service=importlib.util.module_from_spec(spec);sys.modules[spec.name]=service;spec.loader.exec_module(service);logging.disable(logging.CRITICAL)
        business_config=json.loads((root/'config/config_for_search_index.json').read_text())
        cfg=json.loads((root/'config/config_es_engine_es817.online.json').read_text());cfg['extra_params'].update(ensure_index_on_init=False,auto_update_mapping=False)
        for p in cfg['providers'].values():p.update(max_retries=0,retry_on_timeout=False,request_timeout=15)
        engine=module.EsSearchInterfaceES8(config=cfg,ensure_index=False)
        old_process=subprocess.Popen(['/root/miniconda3/envs/py38/bin/python','-u','-c',base64.b64decode(bundle['old_tool']).decode()],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        old_process.stdin.write(json.dumps({'source':bundle['legacy'],'sha256':bundle['legacy_sha256']})+'\n');old_process.stdin.flush()
        ready=json.loads(old_process.stdout.readline())
        if ready.get('kind')!='ready':raise RuntimeError('old_preflight:'+str(ready.get('reason') or ready.get('type')))
        old_read_total=ready['reads'];old=OldProxy();providers=set()
        for public in ['payoneer_olive','payoneer','mercado','mercado_local']:
            cases=[copy.deepcopy(c) for c in bundle['cases'] if c['public']==public and c['search_type']=='qa' and not c['category_field']][:5]
            provider=cases[0]['provider'];client=engine.get_client_by_index(public)
            if provider not in providers:
                trace_node(client);providers.add(provider)
                if not client.info()['version']['number'].startswith('8.17.'):raise RuntimeError('new_version')
            if not client.indices.exists(index=public):raise RuntimeError('new_name_missing')
            seed=copy.deepcopy(cases[0]);seed['indexes']=[public];seed['top_k']=20
            _,a=run_variant(old,seed,'old_seed');_,b=run_variant(engine,seed,'new_seed')
            ids=sorted({d['_id'] for d in a['engine_docs']} & {d['_id'] for d in b['engine_docs']})[:40]
            if not ids:raise RuntimeError('no_comparable_candidates')
            old_sources={h['_id']:h['_source'] for h in read_old(public,ids)}
            response=client.search(index=public,query={'ids':{'values':ids}},size=40).body
            new_sources={h['_id']:h['_source'] for h in response.get('hits',{}).get('hits',[])}
            identical=[key for key in ids if key in old_sources and key in new_sources and sha(old_sources[key])==sha(new_sources[key])]
            if len(identical)<5:raise RuntimeError('insufficient_identical_whole_source_documents:'+public)
            pool=identical[:10]
            report['pools'].append({'provider':provider,'public':public,'examined_ids':len(ids),'identical_whole_source':len(identical),
                'selected':len(pool),'selected_identity_sha256':sha(pool),'complete_source_sha256':sha([old_sources[k] for k in pool])})
            for case in cases:
                case['indexes']=[public];case['top_k']=10;case['use_synonyms']=True
                if case['condition'] is None:case['condition']=[{'quality_level':['high'],'data_type':['qa'],'audit_result':[1,2,-1]},{'audit_result':[1,2],'data_type':['qa']}]
                for group in case['condition']:group['_id']=pool
                rows={};private={}
                for label,actual in [('old7',old),('fixed',engine)]:rows[label],private[label]=run_variant(actual,case,label)
                comparison=knowledge_compare(private['old7'],private['fixed'])
                row={'case':case['case'],'provider':provider,'public':public,'query_sha256':case['query_sha256'],'pool_size':len(pool),
                    'id_filter_sha256':sha(pool),'runs':rows,'comparison':comparison}
                report['rows'].append(row)
                print(json.dumps({'event':'progress','completed':len(report['rows']),'complete_final_equal':sum(r['comparison']['complete_final_response_equal'] for r in report['rows'])}),flush=True)
                if not comparison['complete_final_response_equal']:
                    print(json.dumps({'event':'private_failure','case':case['case'],'payload':{'input':case,'runs':private}},allow_nan=False),flush=True)
        report['completed']=len(report['rows'])==20
    except Exception as exc:
        report['completed']=False;report['error_type']=type(exc).__name__
        if isinstance(exc,RuntimeError):report['reason']=str(exc)
    finally:
        if old_process is not None:
            try:
                if old_process.poll() is None:
                    old_process.stdin.write('{"stop":true}\n');old_process.stdin.flush();old_process.stdin.close();old_process.wait(timeout=20)
            except (BrokenPipeError,subprocess.TimeoutExpired):old_process.terminate();old_process.wait(timeout=10)
        if engine is not None:engine.router.close()
        report['after']=snapshot();report['online_state_unchanged']=all(initial[k]==report['after'][k] for k in ['services','file_sha256'])
        report['native8_reads']=calls;report['native7_reads']=old_read_total;report['violations']=violations;report['native_errors']=native_errors[:10]
        report['implementation_hashes']={k:bundle[k+'_sha256'] for k in ['online','fixed','legacy']}
        print(json.dumps({'event':'final','report':report},allow_nan=False),flush=True)

controlled_main()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    args = parser.parse_args()
    if args.fixture.stat().st_size > 8 * 1024 ** 2:
        raise ValueError('fixture exceeds budget')
    with args.fixture.open() as handle:
        cases = json.load(handle)
    root = Path(__legacy_source_file__).resolve().parents[1]
    fixed = (root / 'knowledge_interface_tools/es8_search_interface.py').read_bytes()
    legacy = subprocess.check_output(['git', 'show', 'f873a593:knowledge_interface_tools/es_search_interface.py'], cwd=root)
    bundle = {'cases': cases, 'fixed': base64.b64encode(fixed).decode(), 'fixed_sha256': hashlib.sha256(fixed).hexdigest(),
        'legacy': base64.b64encode(legacy).decode(), 'legacy_sha256': hashlib.sha256(legacy).hexdigest(),
        'old_tool': base64.b64encode(OLD.encode()).decode(), 'online_sha256': '9ed795c5b837e8f6b46360ca46e0181feb67b08a288362275efe985111bba223'}
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    args.private_output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (args.private_output / '.gitignore').write_text('*\n')
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'shenzhen-120',
        'cd /root/knowledge_database_builder && PYTHONDONTWRITEBYTECODE=1 nice -n 15 .venv-es817/bin/python -u -c ' + shlex.quote(REMOTE)]
    result = subprocess.run(command, input=json.dumps(bundle), text=True, capture_output=True, timeout=240)
    report = None
    for line in result.stdout.splitlines():
        if not line.startswith('{'):
            continue
        event = json.loads(line)
        if event['event'] == 'final':report = event['report']
        elif event['event'] == 'private_failure':
            target = args.private_output / (event['case'] + '.json')
            with target.open('x') as handle:handle.write(json.dumps(event['payload'], ensure_ascii=False, allow_nan=False))
            target.chmod(0o600)
        else:print(json.dumps(event), flush=True)
    if report is None:report = {'completed': False, 'returncode': result.returncode}
    report['tool_sha256'] = hashlib.sha256(Path(__legacy_source_file__).read_bytes()).hexdigest()
    (args.output / 'evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: report.get(k) for k in ['completed','reason','native8_reads','native7_reads','online_state_unchanged']}))
    if not report['completed']:raise SystemExit(1)


if __name__ == '__main__':main()
