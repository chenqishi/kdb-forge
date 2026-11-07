"""Same ES8 data: frozen full-source engine vs actual source-filter fix, recall IDs only."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/es817_source_recall_only_20261009.py')
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from es817_parallel_100_20261009 import REMOTE as EXISTING

BASELINE = '12a86da7163c5136524a60730c6af476788933c5'
FIXTURE_SHA = '7b3d935deb8831885c2a993127217d3b0017eb8191aee5bb2d62257549212830'
REMOTE = EXISTING.rsplit('\nremote_main()', 1)[0] + r'''
stage_routes=[]

def normalize_request(body):
    normalized=copy.deepcopy(body);normalized.pop('_source',None)
    def walk(value):
        if isinstance(value,dict):
            inner=value.get('inner_hits')
            if isinstance(inner,dict):inner.pop('_source',None)
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(normalized)
    return normalized

def capture_msearch(client):
    original=client.msearch
    def wrapped(*args,**kwargs):
        response=original(*args,**kwargs)
        searches=kwargs['searches'];subresponses=response['responses']
        if len(subresponses)!=len(searches)//2:raise RuntimeError('subresponse_count')
        for header,body,sub in zip(searches[::2],searches[1::2],subresponses):
            if sub.get('error') or sub.get('timed_out') or (sub.get('_shards') or {}).get('failed'):
                raise RuntimeError('incomplete_native_subsearch')
            hits=sub.get('hits',{}).get('hits',[])
            identities=[(h.get('_index',header['index']),h['_id']) for h in hits]
            stage_routes.append({'index':header['index'],'query_and_options_sha256':sha(normalize_request(body)),
                'source_projection':body.get('_source'),'hits':len(hits),
                'ordered_ids_sha256':sha(identities),'ordered_id_hashes':[sha(key) for key in identities],
                'scores_sha256':sha([h.get('_score') for h in hits]),'total':sub.get('hits',{}).get('total')})
        return response
    client.msearch=wrapped

def compare_recall(before,after,raw_before,raw_after,routes_before,routes_after):
    a=raw_before['engine_docs'];b=raw_after['engine_docs']
    ids_a=[(d.get('_index'),d.get('_id')) for d in a];ids_b=[(d.get('_index'),d.get('_id')) for d in b]
    metadata=[]
    for docs in [a,b]:
        copied=copy.deepcopy(docs)
        for doc in copied:
            for path in ['indexes','image_indexes']:
                for item in doc.get(path,[]) or []:
                    if isinstance(item,dict):item.pop('embedding',None)
        metadata.append(sha(copied))
    base_by_id={key:doc for key,doc in zip(ids_a,a)};bad_vectors=[]
    for key,doc in zip(ids_b,b):
        base=base_by_id.get(key)
        if base is None:continue
        for path in ['indexes','image_indexes']:
            base_items=base.get(path) or []
            for offset,item in enumerate(doc.get(path,[]) or []):
                if isinstance(item,dict) and item.get('embedding') is not None:
                    if offset>=len(base_items) or not isinstance(base_items[offset],dict) or item['embedding']!=base_items[offset].get('embedding'):
                        bad_vectors.append({'id_sha256':sha(key),'path':path,'offset':offset})
    result={'normalized_requests_equal':[(r['index'],r['query_and_options_sha256']) for r in routes_before]==[(r['index'],r['query_and_options_sha256']) for r in routes_after],
        'raw_route_ids_and_order_equal':[(r['index'],r['ordered_ids_sha256']) for r in routes_before]==[(r['index'],r['ordered_ids_sha256']) for r in routes_after],
        'raw_route_scores_equal':[r['scores_sha256'] for r in routes_before]==[r['scores_sha256'] for r in routes_after],
        'raw_route_totals_equal':[r['total'] for r in routes_before]==[r['total'] for r in routes_after],
        'merged_ids_and_order_equal':ids_a==ids_b,'merged_id_sets_equal':set(ids_a)==set(ids_b),
        'merged_scores_equal':[d.get('score') for d in a]==[d.get('score') for d in b],
        'engine_total_equal':before['total']==after['total'],
        'other_source_and_root_vectors_equal':metadata[0]==metadata[1],
        'returned_nested_vectors_match_full_source':not bad_vectors,'bad_nested_vectors':bad_vectors,
        'old_only_id_hashes':[sha(key) for key in ids_a if key not in set(ids_b)],
        'new_only_id_hashes':[sha(key) for key in ids_b if key not in set(ids_a)],
        'before_candidate_count':len(a),'after_candidate_count':len(b)}
    result['recall_passed']=all(result[key] for key in ['normalized_requests_equal','raw_route_ids_and_order_equal',
        'raw_route_scores_equal','raw_route_totals_equal','merged_ids_and_order_equal','merged_scores_equal','engine_total_equal'])
    return result

def source_recall_main():
    global engine,initial,service,business_config
    bundle=json.load(sys.stdin);report={'rows':[],'persistent_ES_writes':0,'embedding_calls':0,'service_HTTP_calls':0,
        'comparison_scope':'Unmodified pre-fix ES8 versus actual local fixed ES8 on same current ES8 data; no ES7 or policy oracle'}
    engines={}
    try:
        initial=snapshot();report['before']=initial
        if initial['file_sha256']['knowledge_interface_tools/es8_search_interface.py']!=bundle['before_sha256']:
            raise RuntimeError('online_baseline_changed')
        classes={}
        for label in ['before','after']:
            source=base64.b64decode(bundle[label])
            if hashlib.sha256(source).hexdigest()!=bundle[label+'_sha256']:raise RuntimeError('source_hash')
            module=types.ModuleType('knowledge_interface_tools._source_recall_'+label);module.__package__='knowledge_interface_tools'
            exec(compile(source,'<isolated-es8-source-recall-'+label+'>','exec'),module.__dict__)
            classes[label]=module.EsSearchInterfaceES8
        spec=importlib.util.spec_from_file_location('_isolated_es8_recall_service',root/'knowledge_database_search_service/src/knowledge_database_search_es.py')
        service=importlib.util.module_from_spec(spec);sys.modules[spec.name]=service;spec.loader.exec_module(service)
        logging.disable(logging.CRITICAL)
        business_config=json.loads((root/'config/config_for_search_index.json').read_text())
        cfg=json.loads((root/'config/config_es_engine_es817.online.json').read_text())
        cfg['extra_params'].update(ensure_index_on_init=False,auto_update_mapping=False)
        for provider in cfg['providers'].values():provider.update(max_retries=0,retry_on_timeout=False,request_timeout=15)
        engine=classes['after'](config=cfg,ensure_index=False);engines['after']=engine
        engines['before']=classes['before'](config=cfg,router=engine.router,ensure_index=False)
        for provider,public,private in groups:
            client=engine.get_client_by_index(public)
            if provider not in report.get('versions',{}):
                trace_node(client);capture_msearch(client);version=client.info()['version']['number']
                if not version.startswith('8.17.'):raise RuntimeError('not_es8_17')
                report.setdefault('versions',{})[provider]=version
            for name in [public,private]:
                if not client.indices.exists(index=name):raise RuntimeError('missing_index:'+name)
        print(json.dumps({'event':'prepared','cases':len(bundle['cases']),'versions':report['versions']}),flush=True)
        for number,case in enumerate(bundle['cases']):
            report['current_case']=case['case'];guard();runs={};raw={};routes={}
            order=['before','after'] if number%2==0 else ['after','before']
            for label in order:
                stage_routes.clear();runs[label],raw[label]=run_variant(engines[label],case,label)
                if runs[label]['invalid_subsearches'] or not stage_routes:raise RuntimeError('not_complete_native_msearch')
                routes[label]=copy.deepcopy(stage_routes)
            comparison=compare_recall(runs['before'],runs['after'],raw['before'],raw['after'],routes['before'],routes['after'])
            row={**{k:v for k,v in case.items() if k not in ['query','vector','condition']},'order':order,
                'condition_sha256':sha(case['condition']),'routes':routes,'comparison':comparison,
                'response_bytes':{label:sum(event['decoded_bytes'] for event in run['http']) for label,run in runs.items()}}
            report['rows'].append(row);print(json.dumps({'event':'case','row':row},allow_nan=False),flush=True)
            del raw
            if (number+1)%10==0:
                print(json.dumps({'event':'progress','completed':number+1,'recall_equal':sum(r['comparison']['recall_passed'] for r in report['rows']),
                    'native_reads':calls,'provider':case['provider']}),flush=True)
        report['completed']=len(report['rows'])==200
        report['passed']=report['completed'] and all(r['comparison']['recall_passed'] and r['comparison']['other_source_and_root_vectors_equal']
            and r['comparison']['returned_nested_vectors_match_full_source'] for r in report['rows'])
    except Exception as exc:
        report['completed']=False;report['passed']=False;report['error_type']=type(exc).__name__
        if isinstance(exc,RuntimeError):report['reason']=str(exc)
    finally:
        if engine is not None:engine.router.close()
        report['after']=snapshot();report['online_state_unchanged']=initial is not None and all(initial[k]==report['after'][k] for k in ['services','file_sha256'])
        report['native_reads']=calls;report['violations']=violations;report['native_errors']=native_errors[:10]
        report['source_hashes']={label:bundle[label+'_sha256'] for label in ['before','after']}
        report['provider_counts']={p:{'completed':sum(r['provider']==p for r in report['rows']),
            'recall_equal':sum(r['provider']==p and r['comparison']['recall_passed'] for r in report['rows']),
            'metadata_and_root_vectors_equal':sum(r['provider']==p and r['comparison']['other_source_and_root_vectors_equal'] for r in report['rows']),
            'nested_vector_values_preserved':sum(r['provider']==p and r['comparison']['returned_nested_vectors_match_full_source'] for r in report['rows'])} for p in ['paas','serverless']}
        print(json.dumps({'event':'final','report':report},allow_nan=False),flush=True)

source_recall_main()
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.fixture.stat().st_size>8*1024**2:raise ValueError('fixture_size')
    fixture=args.fixture.read_bytes()
    if hashlib.sha256(fixture).hexdigest()!=FIXTURE_SHA:raise ValueError('fixture_hash')
    cases=json.loads(fixture)
    if len(cases)!=200:raise ValueError('200_cases_required')
    root=Path(__legacy_source_file__).resolve().parents[1]
    before=subprocess.check_output(['git','show',BASELINE+':knowledge_interface_tools/es8_search_interface.py'],cwd=root)
    after=(root/'knowledge_interface_tools/es8_search_interface.py').read_bytes()
    bundle={'cases':cases}
    for label,source in [('before',before),('after',after)]:
        bundle[label]=base64.b64encode(source).decode();bundle[label+'_sha256']=hashlib.sha256(source).hexdigest()
    args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    command=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','shenzhen-120',
        'cd /root/knowledge_database_builder && PYTHONDONTWRITEBYTECODE=1 nice -n 15 .venv-es817/bin/python -u -c '+shlex.quote(REMOTE)]
    report=None
    with subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True) as process:
        process.stdin.write(json.dumps(bundle,allow_nan=False));process.stdin.close()
        with (args.output/'cases.jsonl').open('x') as casefile:
            for line in process.stdout:
                if not line.startswith('{'):continue
                event=json.loads(line)
                if event['event']=='case':
                    casefile.write(json.dumps(event['row'],ensure_ascii=False,allow_nan=False)+'\n');casefile.flush()
                elif event['event']=='final':report=event['report']
                else:print(json.dumps(event,ensure_ascii=False),flush=True)
        returncode=process.wait(timeout=30)
    if report is None:report={'completed':False,'passed':False,'returncode':returncode,'final_evidence_missing':True}
    report['tool_sha256']=hashlib.sha256(Path(__legacy_source_file__).read_bytes()).hexdigest();report['fixture_sha256']=FIXTURE_SHA
    with (args.output/'evidence.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({k:report.get(k) for k in ['completed','passed','reason','provider_counts','native_reads','online_state_unchanged']},ensure_ascii=False))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':
    main()
