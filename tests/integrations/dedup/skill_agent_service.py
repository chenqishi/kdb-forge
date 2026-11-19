import copy, importlib, json, os, runpy, tempfile
from pathlib import Path
from urllib.parse import urlparse
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kdb.entrypoints.http.retrieval.dedup_routes import register_dedup_routes
from kdb.retrieval.application.dedup_tools import TOOL_MODELS
from kdb.retrieval.ingestion.conflict_jobs import DedupJob
import argparse
parser=argparse.ArgumentParser(description='Exercise an isolated sell_agents service with real LLM and synthetic stores')
parser.add_argument('--llm-config',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[3]
f=runpy.run_path(str(ROOT/'tests/retrieval/test_conflict_jobs.py'))
store=f['Store']([f['row']('old',1,audit_result=1),f['row']('new',2,audit_result=-1)])
def scan(kind,**o):
 for r in list(store.rows.values()):
  if r['data_type']!=kind or r.get('del_flag'): continue
  if o.get('since') and r['insert_time']<o['since']: continue
  if o.get('unaudited') and r.get('audit_result')!=-1: continue
  if o.get('only_unchecked') and r.get('dedup_check',{}).get('status')=='complete': continue
  yield copy.deepcopy(r)
store.scan=scan
os.environ['DEDUP_EVAL_TOKEN']='isolated-synthetic-token'
app=FastAPI()
register_dedup_routes(app,config={'enabled':True,'principals':[{'is_admin':True,'role':'leader','indices':['kb'],'allow_mutations':True,'token_env':'DEDUP_EVAL_TOKEN'}]},job_factory=lambda i:DedupJob(store,f['Models']()))
tool_client=TestClient(app)
config=json.load(open(args.llm_config))
original_post,original_request=requests.post,requests.sessions.Session.request
allowed={urlparse(config['llm']['providers']['deepseek']['api_url']).hostname}
calls=[]
def restricted(self,method,url,*a,**kw):
 if urlparse(url).hostname not in allowed: raise RuntimeError('unexpected external request blocked: '+str(urlparse(url).hostname))
 return original_request(self,method,url,*a,**kw)
requests.sessions.Session.request=restricted
def dispatch(url,*a,**kw):
 if url.startswith('https://dedup.integration.invalid/'):
  calls.append(kw['json'].get('params',{}))
  return tool_client.post('/knowledge_dedup/mcp',json=kw['json'],headers=kw.get('headers',{}))
 return original_post(url,*a,**kw)
requests.post=dispatch
import commons.agent_stage_logger as stage_logger
stage_logger.log_agent_stage=lambda *a,**kw:None
sa=importlib.import_module('agents.skill_agent')
service=importlib.import_module('service.agent_service')
from commons.llm_client import configure_providers
configure_providers(config['llm'])
service.SERVICE_CONFIG={'skill_agent':{'default_function_call_model':'deepseek-chat','default_text_gen_model':'deepseek-chat'}}
sa.log_agent_stage=lambda *a,**kw:None
sa.build_tool_registry=lambda req:{}
tools=[{'tool_key':name,'tool_type':'mcp','tool_schema':{'name':name,'description':desc,'parameters':model.model_json_schema()},'config':{'server_url':'https://dedup.integration.invalid/knowledge_dedup/mcp','tool_name':name,'headers':{'Authorization':'Bearer isolated-synthetic-token'}}} for name,(model,desc) in TOOL_MODELS.items()]
skill={'skill_key':'knowledge-dedup','skill_name':'知识去重','description':'知识重复冲突检查','scope':'admin_system','category':['knowledge'],'applicable_scopes':['role:leader'],'prompt_template':(ROOT/'resources/skills/knowledge-dedup/SKILL.md').read_text(),'tools':tools}
sa.get_skills_for_user=lambda admin:{'skills':[skill]}
client=TestClient(service.app)
with tempfile.TemporaryDirectory() as empty:
 common={'skills_dir':empty,'admin_user_id':'isolated-test','function_call_model':'deepseek-chat','text_gen_model':'deepseek-chat','max_iterations':5,'inject_runtime_context':False,'skill_filter_conditions':{'scope':'admin_system','applicable_scopes':['role:leader']},'system_prompt':'使用知识去重技能完成任务。必须执行已明确授权的工具操作。根据实际结果回答。','enable_search_skill_llm_fallback':False}
 noninteractive=client.post('/skill_agent_request',json={**common,'prompt':'非交互模式：请对index=kb自2026-11-02新增的未去重、未审核QA做重复检查，只记录similarity_info，不删除不改正文。已经授权记录结果，请实际执行，不要只给方案。'}).json()
 first_calls=copy.deepcopy(calls)
 assert noninteractive['success'],noninteractive
 assert store.rows['new'].get('similarity_info'),(noninteractive,first_calls)
 assert all(r['del_flag']==0 and r['content']=='通常两周到账' for r in store.rows.values())
 calls.clear()
 interactive=client.post('/skill_agent_request',json={**common,'prompt':'交互模式：我想清理重复知识，但还没决定要处理哪个index、QA还是Segment、是否删除。请先确认范围。'}).json()
 assert interactive['success'],interactive
 assert not calls,calls
 Path(args.output).write_text(json.dumps({'noninteractive':noninteractive,'noninteractive_tool_calls':first_calls,'interactive':interactive,'interactive_tool_calls':calls,'assertions':'passed','boundary':'real sell_agents service route and LLM; synthetic skill store and knowledge backend; no production writes'},ensure_ascii=False,indent=2))
 print(json.dumps({'assertions':'passed','noninteractive_tools':[r.get('name') for r in first_calls],'interactive_tool_count':len(calls)},ensure_ascii=False))
