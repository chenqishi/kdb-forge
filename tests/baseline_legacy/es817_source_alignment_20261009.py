"""Read-only same-query source-policy diagnostics; no deployment or implementation edit."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/es817_source_alignment_20261009.py')
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from es817_parallel_100_20261009 import REMOTE as EXISTING_GUARDS

REMOTE = EXISTING_GUARDS.rsplit('\nremote_main()', 1)[0] + r'''
captured=[]

def capture_node(client):
    for node in client.transport.node_pool.all():
        original=node.perform_request
        def wrapped(method,target,*args,_original=original,**kwargs):
            if calls>=40:raise RuntimeError('source_probe_read_budget')
            response=_original(method,target,*args,**kwargs)
            if method=='POST' and urlsplit(target).path=='/_msearch':
                body=kwargs.get('body',args[0] if args else None)
                captured.append({'plan':[json.loads(line) for line in body.splitlines() if line.strip()],
                    'payload':json.loads(response.body),'decoded_bytes':len(response.body)})
            return response
        node.perform_request=wrapped
    return client

def qualify_inner(value):
    if isinstance(value,dict):
        nested=value.get('nested')
        if isinstance(nested,dict) and nested.get('inner_hits'):
            path=nested['path']
            nested['inner_hits']['_source']={'includes':[path+'.text',path+'.embedding']}
        for child in value.values():qualify_inner(child)
    elif isinstance(value,list):
        for child in value:qualify_inner(child)

def strip_nested_vectors(source):
    result=copy.deepcopy(source)
    for path in ['indexes','image_indexes']:
        for item in result.get(path,[]) or []:
            if isinstance(item,dict):item.pop('embedding',None)
    return result

def response_stats(payload):
    counts={field:0 for field in ['title_embedding','content_embedding','indexes','image_indexes']}
    inner={'indexes':0,'image_indexes':0};empty_inner=0;raw_hits=0;source_bytes=0;inner_bytes=0
    for sub in payload.get('responses',[payload]):
        for hit in sub.get('hits',{}).get('hits',[]):
            raw_hits+=1;source=hit.get('_source') or {}
            source_bytes+=len(json.dumps(source,ensure_ascii=False,separators=(',',':')).encode())
            for field in ['title_embedding','content_embedding']:
                counts[field]+=len(source.get(field) or [])==1024
            for path in ['indexes','image_indexes']:
                counts[path]+=sum(len(item.get('embedding') or [])==1024 for item in source.get(path,[]) or [] if isinstance(item,dict))
            sections=hit.get('inner_hits') or {}
            inner_bytes+=len(json.dumps(sections,ensure_ascii=False,separators=(',',':')).encode()) if sections else 0
            for section in sections.values():
                for item in section.get('hits',{}).get('hits',[]):
                    path=(item.get('_nested') or {}).get('field')
                    if path in inner:inner[path]+=len((item.get('_source') or {}).get('embedding') or [])==1024
                    empty_inner+=not bool(item.get('_source'))
    return {'raw_hits':raw_hits,'outer_vector_instances':counts,'inner_vector_instances':inner,
        'empty_inner_sources':empty_inner,'outer_source_canonical_bytes':source_bytes,'inner_hits_canonical_bytes':inner_bytes}

def merge_docs(payload):
    merged={}
    for sub in payload['responses']:
        for hit in sub.get('hits',{}).get('hits',[]):
            key=(hit['_index'],hit['_id'])
            doc={'_index':hit['_index'],'_id':hit['_id'],'score':hit['_score'],**copy.deepcopy(hit.get('_source') or {})}
            engine._restore_inner_embeddings(hit,doc)
            if key in merged:engine._merge_index_embeddings(merged[key],doc)
            else:merged[key]=doc
    return list(merged.values())

def compare_responses(full,other,filtered=False):
    ids_a=[];ids_b=[];totals_a=[];totals_b=[];sources_a=[];sources_b=[];inner_a=[];inner_b=[]
    for sub in full['responses']:
        totals_a.append(sub.get('hits',{}).get('total'))
        for hit in sub.get('hits',{}).get('hits',[]):
            ids_a.append((hit['_index'],hit['_id'],hit['_score']))
            source=hit.get('_source') or {}
            sources_a.append(strip_nested_vectors(source) if filtered else source)
            inner_a.append(hit.get('inner_hits') or {})
    for sub in other['responses']:
        totals_b.append(sub.get('hits',{}).get('total'))
        for hit in sub.get('hits',{}).get('hits',[]):
            ids_b.append((hit['_index'],hit['_id'],hit['_score']))
            sources_b.append(hit.get('_source') or {})
            inner_b.append(hit.get('inner_hits') or {})
    return {'hit_identity_order_score_equal':sha(ids_a)==sha(ids_b),'total_equal':sha(totals_a)==sha(totals_b),
        'expected_source_equal':sha(sources_a)==sha(sources_b),'inner_hits_equal':sha(inner_a)==sha(inner_b)}

def source_main():
    global engine,initial
    incoming=json.load(sys.stdin);logging.disable(logging.CRITICAL)
    initial=snapshot();report={'before':initial,'rows':[],'images':[],'persistent_ES_writes':0,'embedding_calls':0,'service_HTTP_calls':0}
    try:
        from knowledge_interface_tools.es8_search_interface import EsSearchInterfaceES8
        cfg=json.loads((root/'config/config_es_engine_es817.online.json').read_text())
        cfg['extra_params'].update(ensure_index_on_init=False,auto_update_mapping=False)
        for p in cfg['providers'].values():p.update(max_retries=0,retry_on_timeout=False,request_timeout=15)
        engine=EsSearchInterfaceES8(config=cfg,ensure_index=False)
        for public in ['payoneer_olive','mercado']:capture_node(trace_node(engine.get_client_by_index(public)))
        legacy_cfg=json.loads(Path('/root/dify/knowledge_database_builder/config/config_es_engine.json').read_text())
        report['legacy_recall_mode_override']=legacy_cfg.get('extra_params',{}).get('recall_mode')
        report['legacy_engine_sha256']=hashlib.sha256((root/'knowledge_interface_tools/es_search_interface.py').read_bytes()).hexdigest()
        reranker=SearchDataInterface.__new__(SearchDataInterface)
        for case in incoming['cases']:
            client=engine.get_client_by_index(case['public'])
            for name in case['indexes']:
                if not client.indices.exists(index=name):raise RuntimeError('required_index_missing:'+name)
            query={'query':case['query'],'vector':{'value':case['vector']},'attribute':case['condition']}
            captured.clear()
            docs,total=engine.search_multi(copy.deepcopy(query),index_names=case['indexes'],size=40,recall_mode='dual')
            if len(captured)!=1:raise RuntimeError('expected_single_successful_native_batch')
            baseline=captured[-1];full_plan=copy.deepcopy(baseline['plan']);qualify_inner(full_plan)
            client.msearch(searches=full_plan,max_concurrent_searches=2)
            qualified=captured[-1];lean_plan=copy.deepcopy(full_plan)
            for body in lean_plan[1::2]:body['_source']={'excludes':['indexes.embedding','image_indexes.embedding']}
            client.msearch(searches=lean_plan,max_concurrent_searches=2)
            lean=captured[-1]
            if any(e['invalid_subsearches'] for e in events):raise RuntimeError('incomplete_native_source_response')
            full_docs=merge_docs(qualified['payload']);lean_docs=merge_docs(lean['payload'])
            if sha(docs)!=sha(merge_docs(baseline['payload'])):raise RuntimeError('probe_merge_differs_from_real_public_method')
            full_scores={(d['_index'],d['_id']):reranker._cal_similarity(case['query'],case['vector'],d,use_synonyms=True) for d in full_docs}
            lean_scores={(d['_index'],d['_id']):reranker._cal_similarity(case['query'],case['vector'],d,use_synonyms=True) for d in lean_docs}
            common=full_scores.keys() & lean_scores.keys();changed=[key for key in common if full_scores[key]!=lean_scores[key]]
            full_map={(d['_index'],d['_id']):d for d in full_docs};lean_map={(d['_index'],d['_id']):d for d in lean_docs}
            vector_hits={(h['_index'],h['_id']) for sub in qualified['payload']['responses'][1::2] for h in sub.get('hits',{}).get('hits',[])}
            changes=[]
            for key in sorted(changed):
                a=full_map[key];b=lean_map[key]
                changes.append({'id_sha256':sha(key),'vector_route_hit':key in vector_hits,
                    'full_nested_vectors':sum(bool(x.get('embedding')) for x in a.get('indexes',[]) or []),
                    'lean_nested_vectors':sum(bool(x.get('embedding')) for x in b.get('indexes',[]) or []),
                    'root_vectors_equal':all(sha(a.get(f))==sha(b.get(f)) for f in ['title_embedding','content_embedding']),
                    'title_similarity_without_synonyms':reranker._cal_title_similarity(case['query'],case['vector'],a,False),
                    'full_title_similarity_with_synonyms':reranker._cal_title_similarity(case['query'],case['vector'],a,True),
                    'lean_title_similarity_with_synonyms':reranker._cal_title_similarity(case['query'],case['vector'],b,True),
                    'full_final_similarity':full_scores[key],'lean_final_similarity':lean_scores[key]})
            if changed:
                print(json.dumps({'event':'private_failure','case':case['case'],'payload':{'input':case,
                    'current_full_changed_docs':[full_map[k] for k in sorted(changed)],
                    'old_policy_changed_docs':[lean_map[k] for k in sorted(changed)]}},allow_nan=False),flush=True)
            old_stats=response_stats(lean['payload']);new_stats=response_stats(baseline['payload'])
            row={'case':case['case'],'provider':case['provider'],'public':case['public'],'indexes':case['indexes'],
                'query_sha256':case['query_sha256'],'per_route_budget':20,'total':total,
                'baseline_current':{'decoded_bytes':baseline['decoded_bytes'],**new_stats},
                'qualified_full':{'decoded_bytes':qualified['decoded_bytes'],**response_stats(qualified['payload'])},
                'qualified_old_policy':{'decoded_bytes':lean['decoded_bytes'],**old_stats},
                'current_to_qualified':compare_responses(baseline['payload'],qualified['payload']),
                'qualified_to_old_policy':compare_responses(qualified['payload'],lean['payload'],True),
                'current_excess_bytes_vs_old_policy':baseline['decoded_bytes']-lean['decoded_bytes'],
                'current_excess_percent_vs_old_policy':100*(baseline['decoded_bytes']/lean['decoded_bytes']-1),
                'restored_old_policy_nested_vectors':sum(bool(item.get('embedding')) for d in lean_docs for item in d.get('indexes',[]) or []),
                'full_docs':len(full_docs),'lean_docs':len(lean_docs),'business_score_changed':len(changed),
                'baseline_vs_qualified_merged_equal':sha(docs)==sha(full_docs),'changed_details':changes,
                'max_business_score_drop':max((full_scores[k]-lean_scores[k] for k in common),default=0),
                'changed_id_sha256':[sha(key) for key in sorted(changed)],
                'top20_identity_equal':sha(sorted(full_scores,key=full_scores.get,reverse=True)[:20])==sha(sorted(lean_scores,key=lean_scores.get,reverse=True)[:20])}
            report['rows'].append(row)
            print(json.dumps({'event':'progress','case':case['case'],'bytes':row['current_excess_bytes_vs_old_policy'],'score_changed':len(changed)}),flush=True)
            sample=client.search(index=case['public'],size=2,source_includes=['image_indexes'],
                query={'nested':{'path':'image_indexes','query':{'exists':{'field':'image_indexes.embedding'}}}}).body
            image={'provider':case['provider'],'public':case['public'],'sample_limit':2,'sample_hits':len(sample.get('hits',{}).get('hits',[]))}
            vector=next((item['embedding'] for hit in sample.get('hits',{}).get('hits',[]) for item in hit.get('_source',{}).get('image_indexes',[]) or []
                if isinstance(item,dict) and len(item.get('embedding') or [])==1024 and all(math.isfinite(v) for v in item['embedding']) and any(item['embedding'])),None)
            if vector:
                native=engine._build_knn_clause(vector,vector_field='image_indexes.embedding',k=2,with_inner_hits=True)
                relative=client.search(index=case['public'],size=2,query=native,source_excludes=['image_indexes.embedding']).body
                qualified_image=copy.deepcopy(native);qualify_inner(qualified_image)
                complete=client.search(index=case['public'],size=2,query=qualified_image,source_excludes=['image_indexes.embedding']).body
                image['relative']=response_stats(relative);image['qualified']=response_stats(complete)
                image['same_hits']=compare_responses({'responses':[relative]},{'responses':[complete]})['hit_identity_order_score_equal']
            else:image['vector_path_verified']=False
            report['images'].append(image)
        if violations or any(e['invalid_subsearches'] for e in events):raise RuntimeError('source_probe_guard_failed')
        report['completed']=True
    except Exception as exc:
        report['completed']=False;report['error_type']=type(exc).__name__
        if isinstance(exc,RuntimeError):report['reason']=str(exc)
    finally:
        if engine is not None:engine.router.close()
        report['native_reads']=calls;report['violations']=violations;report['native_errors']=native_errors[:10]
        report['after']=snapshot()
        report['online_state_unchanged']=all(initial[k]==report['after'][k] for k in ['services','file_sha256'])
        print(json.dumps({'event':'final','report':report},allow_nan=False),flush=True)

source_main()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--case')
    args = parser.parse_args()
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    args.private_output.mkdir(parents=True, mode=0o700, exist_ok=False)
    cases = json.loads(args.fixture.read_text())
    selected = [next(c for c in cases if c['public'] == public and c['search_type'] == 'qa' and c['use_synonyms']
                     and c['top_k'] == 20 and len(c['indexes']) == 2)
                for public in ['payoneer_olive', 'payoneer', 'mercado', 'mercado_local']]
    if args.case:
        selected = [c for c in selected if c['case'] == args.case]
        if not selected:
            raise ValueError('case must be one of the four previously selected queries')
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'shenzhen-120',
               'cd /root/knowledge_database_builder && PYTHONDONTWRITEBYTECODE=1 nice -n 15 .venv-es817/bin/python -u -c ' + shlex.quote(REMOTE)]
    result = subprocess.run(command, input=json.dumps({'cases': selected}), capture_output=True, text=True, timeout=180)
    output = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    for item in output:
        if item.get('event') == 'private_failure':
            target = args.private_output / (item['case'] + '.json')
            with target.open('x') as handle:
                handle.write(json.dumps(item['payload'], ensure_ascii=False, allow_nan=False))
            target.chmod(0o600)
    report = next((item['report'] for item in reversed(output) if item.get('event') == 'final'), None)
    if report is None:
        report = {'completed': False, 'returncode': result.returncode, 'final_evidence_missing': True}
    report['tool_sha256'] = hashlib.sha256(Path(__legacy_source_file__).read_bytes()).hexdigest()
    report['fixture_sha256'] = hashlib.sha256(args.fixture.read_bytes()).hexdigest()
    (args.output / 'evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: report.get(k) for k in ['completed', 'native_reads', 'violations', 'online_state_unchanged', 'reason']}, ensure_ascii=False))
    if not report['completed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
