"""Actual offline-task insert stages -> Fire -> business -> real ES8 factory.

Only external boundaries are replaced; no real jobs, database/model calls or ES
writes occur. Known contract defects are strict xfails, not claimed fixed.
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_off_task_es817_20261008.py')
import contextlib
import copy
import importlib.util
import json
import os
import runpy
import shlex
import socket
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import fire
import numpy as np
import pytest
import requests

from knowledge_interface_tools import search_index_data_interface as business
from knowledge_interface_tools.es8_client_router import IndexClientRouter
from knowledge_interface_tools.es8_search_interface import EsSearchInterfaceES8
from knowledge_interface_tools.es_search_interface import EsSearchInterface
from test_es8_interface import FakeIndices

ROOT = Path(__legacy_source_file__).resolve().parents[1]
REAL_CREATE_CLIENT = IndexClientRouter._create_client
STAGES = [
    ('document_qa_mining_task_control','DocumentQAMiningTaskController','stage_7_insert_index','qa'),
    ('document_qa_segment_mining','DocumentQAMiningTaskController','stage_8_insert_index','qa'),
    ('document_qa_segment_mining','DocumentQAMiningTaskController','stage_11_insert_segment_index','segment'),
    ('html_kg_gen_task_control','HtmlKgGenTaskController','stage_8_insert_index','qa'),
    ('html_kg_gen_task_control','HtmlKgGenTaskController','stage_11_insert_segment_index','segment'),
    ('chat_qa_mining_task_control','ChatQAMiningTaskController','stage_5_insert_index','qa'),
    ('excel_qa_segment_upload_control','ExcelQASegmentUploadController','stage_3_insert_index','qa'),
]


class CaptureClient:
    def __init__(self, provider):
        self.provider = provider
        self.indices = FakeIndices()
        self.calls = []
        self.update_result = 'created'
        self.update_error = None
        self.search_error = None

    def search(self, **kwargs):
        self.calls.append(('search',copy.deepcopy(kwargs)))
        if self.search_error:
            raise self.search_error
        return {'_shards': {'total':1,'successful':1,'failed':0},
                'hits': {'total':{'value':0,'relation':'eq'},'hits':[]}}

    def update(self, **kwargs):
        self.calls.append(('update',copy.deepcopy(kwargs)))
        if self.update_error:
            raise self.update_error
        return {'result':self.update_result}


@pytest.fixture
def offline_boundaries(monkeypatch, tmp_path, request):
    for name, attrs in {
        'off_task_tools.minio_downloader': {'MinioDownloader':Mock()},
        'off_task_tools.task_status_updater': {'TaskStatusUpdater':Mock()},
        'data_preprocess.document_clear_price_access': {'access_document_clear_price':Mock(),'asscess_document_clear_price':Mock()},
        'data_control_tools.get_data_from_sql': {'ChatDataExtractor':Mock()},
        'commons.schema_trans': {'classify_excel_upload':Mock()},
    }.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules,name,module)
    controllers = {}
    for name, _, _, _ in STAGES:
        if name in controllers:
            continue
        spec = importlib.util.spec_from_file_location('_offtask_probe_'+name,ROOT/'control_service'/f'{name}.py')
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,spec.name,module)
        spec.loader.exec_module(module)
        controllers[name] = module
    clients = {name:CaptureClient(name) for name in ('serverless','paas')}
    monkeypatch.setattr(IndexClientRouter,'_create_client',Mock(side_effect=lambda cfg: clients['paas' if 'paas' in cfg['hosts'][0] else 'serverless']))
    embedding = Mock()
    embedding.text2embedding.side_effect = lambda text: np.asarray([1.0]+[0.125]*1023)
    monkeypatch.setattr(business,'EmbeddingTools',Mock(return_value=embedding))
    monkeypatch.setattr('commons.embedding_tools.AliEmbedding',Mock(return_value=embedding))
    monkeypatch.setattr(business.simility_tools,'SimilityTools',Mock(return_value=Mock(is_simility_knowledge=Mock(return_value=False))))
    monkeypatch.setattr(business,'gen_keyword_by_title_content',Mock(return_value=[{'word':'offline'}]))
    monkeypatch.setattr(socket.socket,'connect',Mock(side_effect=AssertionError('real network forbidden in offline task test')))
    monkeypatch.setattr(requests.sessions.Session,'request',Mock(side_effect=AssertionError('real HTTP forbidden in offline task test')))
    state = {'clients':clients,'controllers':controllers,'cli_runs':[],'tmp':tmp_path,'embedding':embedding}
    monkeypatch.setattr(business,'SearchDataInterface',business.SearchDataInterface)
    monkeypatch.setattr(controllers[STAGES[0][0]].subprocess,'run',lambda cmd,**kw: invoke_cli(state,cmd,kw['stdout']))

    class StubProcess:
        def __init__(self,cmd,**kw):
            result = invoke_cli(state,cmd,kw['stdout'])
            self.returncode = result.returncode
            self.pid = 987654321

        def wait(self,timeout=None):
            return self.returncode

    monkeypatch.setattr(controllers[STAGES[0][0]].subprocess,'Popen',StubProcess)
    yield state
    folder = os.environ.get('KDB_OFFLINE_ES8_EVIDENCE')
    if folder:
        summary = {'test':request.node.nodeid,'real_business_and_factory':True,'actual_es_writes':0,
                   'cli_runs':state['cli_runs'],'requests':[],'index_creates':[]}
        for provider,client in clients.items():
            for kind,kwargs in client.calls:
                doc = kwargs.get('doc') or {}
                summary['requests'].append({'provider':provider,'method':kind,'index':kwargs['index'],
                    'id':kwargs.get('id'),'doc_as_upsert':kwargs.get('doc_as_upsert'),'source_fields':sorted(doc),
                    'title_dims':len(doc.get('title_embedding') or []),'content_dims':len(doc.get('content_embedding') or []),
                    'index_entries':len(doc.get('indexes') or []),'image_entries':len(doc.get('image_indexes') or []),
                    'native_knn': '"knn"' in json.dumps(kwargs.get('query') or {}),
                    'script_score':'script_score' in json.dumps(kwargs.get('query') or {})})
            summary['index_creates'].extend({'provider':provider,'index':row['index']} for row in client.indices.created)
        path = Path(folder)/(request.node.name.replace('/','_')+'.json')
        assert not path.exists(), 'preserve existing offline evidence'
        path.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        path.chmod(0o600)


def make_configs(state,index,ensure=False,check_duplicate=False,specific=False):
    directory = state['tmp']/'config'
    directory.mkdir(exist_ok=True)
    engine_path = directory/'es8.json'
    engine = {'es_version':'8.17','index_name':'unused_default','vector_fields':{'indexes_embedding':1024},
        'providers':{name:{'hosts':[f'http://{name}.new.invalid']} for name in state['clients']},
        'default_provider':'serverless','index_routes':{'payoneer*':'paas','mercado*':'serverless'},
        'extra_params':{'ensure_index_on_init':ensure,'auto_update_mapping':False,'recall_mode':'dual'}}
    engine_path.write_text(json.dumps(engine))
    business_path = directory/(f'{index}_config.json' if specific else 'config_for_search_index.json')
    business_path.write_text(json.dumps({'search_engine_config_path':str(engine_path),
        'embedding_config_path':'offline-no-model.json','simility_config_path':'offline-no-llm.json',
        'check_duplicate':check_duplicate,'category_service_url':''}))
    state['engine_path'] = engine_path
    state['business_path'] = business_path
    return business_path


def make_record(index,kind):
    data = {'content':'synthetic offline answer','data_type':kind,'client':index,'platform':index,
        'from_type':'document','quality_level':'high','audit_result':-1,'review_decision':'accept',
        'task_id':'offline-es817-contract','flag':'fixture-flag',
        'ext_info':{'from_file_name':'synthetic.txt','nested':{'zero':0,'false':False,'items':[]}},
        'primary_category':{'cate1_id':'1','cate1_name':'默认分组','category_ids':['1'],'category_path':'默认分组'},
        'custom_metadata':{'kept':True},'keywords':['fixture'],
        'indexes':[{'text':'existing query','embedding':[0.25]+[0.125]*1023},{'text':'  '}],
        'image_indexes':[{'text':'synthetic image OCR','image_url':'fixture://image'}]}
    if kind=='qa':
        data.update(title='synthetic offline question',synonyms_title=['synthetic alternative one','synthetic alternative two'])
    return data


def make_controller(state,stage,index,rows=None):
    module_name,class_name,method,kind = stage
    cls = getattr(state['controllers'][module_name],class_name)
    controller = cls.__new__(cls)
    controller.script_dir = str(ROOT)
    controller.config_dir = str(state['tmp']/'config')
    controller.task_id = 'offline-contract'
    controller.task_info = {}
    controller.index_name = controller.index = controller.client = index
    controller._index_config_path = None
    controller.log_dir = str(state['tmp']/'logs')
    Path(controller.log_dir).mkdir(exist_ok=True)
    controller.status_updater = Mock()
    input_path = state['tmp']/'data.jsonl'
    input_path.write_text('\n'.join(json.dumps(row,ensure_ascii=False) for row in (rows or [make_record(index,kind)]))+'\n')
    controller.search_data_file_path = controller.segment_search_data_file_path = controller.index_input_file_path = str(input_path)
    controller.insert_result_file_path = str(state['tmp']/'insert_result.json')
    controller.task_timeout_seconds = None
    return controller


def invoke_cli(state,cmd,stdout):
    command = cmd if isinstance(cmd,list) else shlex.split(cmd)
    position = next(i for i,word in enumerate(command) if word.endswith('/knowledge_interface_tools/search_index_data_interface.py'))
    args = command[position+1:]
    row = {'executable':command[position-1],'arguments':args,'returncode':0}
    state['cli_runs'].append(row)
    try:
        with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stdout):
            row['stats'] = fire.Fire({'insert_data_to_search_index':business.insert_data_to_search_index},command=args)
    except Exception as exc:
        row.update(returncode=1,error_type=type(exc).__name__)
    return SimpleNamespace(returncode=row['returncode'])


@pytest.mark.parametrize('stage',STAGES,ids=[row[0]+'.'+row[2] for row in STAGES])
@pytest.mark.parametrize('index,provider',[('mercado_local','serverless'),('payoneer_olive','paas')])
def test_controller_real_batch_selects_new_provider(offline_boundaries,stage,index,provider):
    state = offline_boundaries
    make_configs(state,index)
    # Exact factory/class handoff, followed by the actual controller batch path.
    engine = EsSearchInterface(config_path=str(state['engine_path']),index_name='mix')
    assert isinstance(engine._impl,EsSearchInterfaceES8)
    controller = make_controller(state,stage,index)
    assert getattr(controller,stage[2])() is True
    assert state['cli_runs'][-1]['stats']['insert_success_num']==1
    writes = [kw for name,kw in state['clients'][provider].calls if name=='update']
    assert len(writes)==1
    assert not any(name=='update' for p,client in state['clients'].items() if p!=provider for name,_ in client.calls)
    request = writes[0]
    doc = request['doc']
    assert request['index']==index and request['doc_as_upsert'] is True and '_id' not in doc
    assert request['id']==business.gen_data_id({'title':'synthetic offline question' if stage[3]=='qa' else '',
        'content':'synthetic offline answer','data_type':stage[3]})
    assert doc['dataset']==index and doc['data_type']==stage[3]
    assert doc['ext_info']['nested']=={'zero':0,'false':False,'items':[]}
    assert doc['ext_info']['custom_metadata']=={'kept':True}
    assert doc['task_id']=='offline-es817-contract' and doc['flag']=='fixture-flag'
    assert doc['primary_category']['cate1_id']=='1' and doc['audit_result']==-1
    assert doc['insert_time'] and doc['update_time'] and doc['del_flag']==0
    assert len(doc['content_embedding'])==1024
    assert all(len(entry['embedding'])==1024 and entry['text'].strip() for entry in doc['indexes'])
    assert len(doc['image_indexes'][0]['embedding'])==1024
    if stage[3]=='qa':
        assert len(doc['title_embedding'])==1024
        assert set(doc['synonyms_title']).issubset({entry['text'] for entry in doc['indexes']})
    else:
        assert 'title' not in doc and 'synonyms_title' not in doc
    assert state['cli_runs'][-1]['executable']==(sys.executable if stage[0]=='excel_qa_segment_upload_control' else 'python')


@pytest.mark.parametrize('selection',['specific','generic','index_fallback'])
def test_specific_configuration_overrides_default(offline_boundaries,selection):
    state = offline_boundaries
    generic = make_configs(state,'mercado_local')
    specific = generic.parent/'mercado_local_config.json'
    fallback = generic.parent/'index_config.json'
    if selection=='specific':
        specific.write_text(json.dumps({'search_engine_config_path':'synthetic-old-config-kept.json'}))
        expected = specific
    elif selection=='index_fallback':
        generic.rename(fallback)
        expected = fallback
    else:
        expected = generic
    controller = make_controller(state,STAGES[1],'mercado_local')
    assert controller._get_index_config_path()==str(expected)
    assert not any(client.calls for client in state['clients'].values())


def test_chat_gate_and_real_new_dedup(offline_boundaries):
    state = offline_boundaries
    index = 'payoneer_olive'
    make_configs(state,index,check_duplicate=True)
    accepted = make_record(index,'qa')
    accepted['from_type']='chat_auto'
    mid = {**copy.deepcopy(accepted),'title':'mid fixture','quality_level':'mid','review_decision':'review'}
    rejected = {**copy.deepcopy(accepted),'title':'reject fixture','review_decision':'reject'}
    controller = make_controller(state,STAGES[5],index,[accepted,mid,rejected])
    assert controller.stage_5_insert_index() is True
    stats = state['cli_runs'][-1]['stats']
    assert stats['input_num']==3 and stats['gate_skip_num']==2 and stats['insert_success_num']==1
    assert json.loads(Path(controller.insert_result_file_path).read_text())==stats
    calls = state['clients']['paas'].calls
    assert [name for name,_ in calls]==['search','update']
    assert '"knn"' in json.dumps(calls[0][1]['query']) and 'script_score' not in json.dumps(calls[0][1]['query'])
    assert calls[1][1]['doc']['from_type']=='chat_auto'


def test_es8_guard_rejects_es7_worker_client(offline_boundaries,monkeypatch):
    module = types.ModuleType('elasticsearch')
    module.__versionstr__ = '7.10.0'
    module.Elasticsearch = Mock(side_effect=AssertionError('must fail before constructing wrong client'))
    monkeypatch.setitem(sys.modules,'elasticsearch',module)
    router = IndexClientRouter(config={'hosts':['http://new.invalid']},client_factory=Mock())
    with pytest.raises(RuntimeError,match='拒绝非 8.17'):
        REAL_CREATE_CLIENT(router,{'hosts':['http://new.invalid']})
    module.Elasticsearch.assert_not_called()


@pytest.mark.xfail(strict=True,reason='O01: ordinary failed-row stats leave CLI exit zero and controller reports success')
def test_row_failure_is_reported_as_task_failure(offline_boundaries):
    state = offline_boundaries
    make_configs(state,'mercado_local')
    state['embedding'].text2embedding.side_effect = TimeoutError('synthetic embedding provider outage')
    controller = make_controller(state,STAGES[1],'mercado_local')
    success = controller.stage_8_insert_index()
    assert state['cli_runs'][-1]['stats']['insert_failure_num']==1
    assert state['cli_runs'][-1]['stats']['insert_success_num']==0
    assert not any(name=='update' for client in state['clients'].values() for name,_ in client.calls)
    assert success is False


def test_batch_mix_initialization_keeps_target_provider(offline_boundaries):
    state = offline_boundaries
    make_configs(state,'payoneer_olive',ensure=True)
    controller = make_controller(state,STAGES[1],'payoneer_olive')
    assert controller.stage_8_insert_index() is True
    # Legacy batch already initialized mix; this must not redirect target writes.
    created = [(provider,row['index']) for provider,client in state['clients'].items()
               for row in client.indices.created]
    assert created==[('serverless','mix'),('paas','payoneer_olive')]
    writes = [(provider,kw['index']) for provider,client in state['clients'].items()
              for method,kw in client.calls if method=='update']
    assert writes==[('paas','payoneer_olive')]
    assert state['cli_runs'][-1]['stats']['insert_success_num']==1


@pytest.mark.xfail(strict=True,reason='O03: factory accepts project example es8.17 but current ES8 class rejects it')
def test_example_alias_initializes_real_es8(offline_boundaries):
    state = offline_boundaries
    make_configs(state,'mercado_local')
    cfg = json.loads(state['engine_path'].read_text())
    cfg['es_version']='es8.17'
    state['engine_path'].write_text(json.dumps(cfg))
    engine = EsSearchInterface(config_path=str(state['engine_path']),index_name='mix')
    assert isinstance(engine._impl,EsSearchInterfaceES8)


def test_upsert_exception_prevents_success(offline_boundaries):
    state = offline_boundaries
    make_configs(state,'mercado_local')
    state['clients']['serverless'].update_error = RuntimeError('synthetic write failure')
    controller = make_controller(state,STAGES[1],'mercado_local')
    assert controller.stage_8_insert_index() is False
    assert state['cli_runs'][-1]['returncode']==1
    assert state['cli_runs'][-1]['error_type']=='RuntimeError'


def test_existing_id_and_partial_payload(offline_boundaries):
    state = offline_boundaries
    config = make_configs(state,'mercado_local')
    record = make_record('mercado_local','qa')
    record['_id']='existing-fixture'
    record['del_flag']=1
    record['title_embedding']=[0.5]+[0.125]*1023
    controller = make_controller(state,STAGES[1],'mercado_local',[record])
    assert controller.stage_8_insert_index() is True
    kw = next(kw for name,kw in state['clients']['serverless'].calls if name=='update')
    assert kw['id']=='existing-fixture' and '_id' not in kw['doc']
    assert 'insert_time' not in kw['doc'] and kw['doc']['del_flag']==1
    assert kw['doc']['ext_info']['nested']['zero']==0 and kw['doc']['ext_info']['nested']['false'] is False
    assert kw['doc']['title_embedding']==record['title_embedding']


def test_config_reload_at_next_cli(offline_boundaries):
    state = offline_boundaries
    make_configs(state,'mercado_local')
    controller = make_controller(state,STAGES[1],'mercado_local')
    assert controller.stage_8_insert_index() is True
    engine_cfg = json.loads(state['engine_path'].read_text())
    engine_cfg['index_routes']['mercado_local']='paas'
    state['engine_path'].write_text(json.dumps(engine_cfg))
    assert controller.stage_8_insert_index() is True
    assert sum(name=='update' for name,_ in state['clients']['serverless'].calls)==1
    assert sum(name=='update' for name,_ in state['clients']['paas'].calls)==1


def test_dedup_failure_prevents_write(offline_boundaries):
    state = offline_boundaries
    make_configs(state,'payoneer_olive',check_duplicate=True)
    state['clients']['paas'].search_error = RuntimeError('synthetic dedup read failure')
    controller = make_controller(state,STAGES[5],'payoneer_olive')
    assert controller.stage_5_insert_index() is False
    assert state['cli_runs'][-1]['returncode']==1
    stats = json.loads(Path(controller.insert_result_file_path).read_text())
    assert stats['insert_failure_num']==1 and stats['insert_success_num']==0
    assert not any(name=='update' for client in state['clients'].values() for name,_ in client.calls)


def test_address_only_does_not_select_es8(offline_boundaries,monkeypatch):
    detector_client = Mock()
    detector_client.info.return_value = {'version':{'number':'8.17.0'}}
    monkeypatch.setattr('knowledge_interface_tools.es_search_interface.Elasticsearch',Mock(return_value=detector_client))
    factory = EsSearchInterface.__new__(EsSearchInterface)
    assert factory._detect_es_version(['http://new.invalid'],None,None,{})=='es7'


def test_real_cli_entry_returns_normally_on_row_failure(offline_boundaries,monkeypatch,capsys):
    state = offline_boundaries
    config = make_configs(state,'mercado_local')
    controller = make_controller(state,STAGES[1],'mercado_local')
    state['embedding'].text2embedding.side_effect = TimeoutError('synthetic embedding provider outage')
    script = ROOT/'knowledge_interface_tools/search_index_data_interface.py'
    args = [str(script),'insert_data_to_search_index',f'--data_file={controller.search_data_file_path}',
            f'--config_path={config}','--index_name_assign=mercado_local','--check_duplicate=False',
            f'--result_file={controller.insert_result_file_path}']
    monkeypatch.setattr(sys,'argv',args)
    runpy.run_path(str(script),run_name='__main__')
    stats = json.loads(Path(controller.insert_result_file_path).read_text())
    assert stats['insert_failure_num']==1 and stats['insert_success_num']==0
    assert not any(name=='update' for client in state['clients'].values() for name,_ in client.calls)
    state['cli_runs'].append({'entry':'actual __main__ via runpy, no OS child','normal_return':True,'stats':stats})
