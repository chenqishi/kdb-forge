import json
from commons.mysql_connector import MySQLConnector
conn = MySQLConnector('config/mysql_conn_config.json').get_connection()
cur = conn.cursor(dictionary=True)
out={}
try:
    cur.execute("""SELECT app_id,config_value,update_time FROM rufitai.rf_ai_role_config
      WHERE config_key='session_gap_seconds' AND del_flag=0""")
    out['gap']=cur.fetchall()
    cur.execute("""SELECT app_id,config_key,config_value FROM rufitai.rf_ai_role_config
      WHERE config_key IN ('kb_prefetch_style','kb_prefetch_rewrite','max_iterations','dual_query_recall','query_completion_prompt','no_knowledge_policy','react_final_model','react_step_model','risk_control','output_verify')
      AND del_flag=0""")
    out['levers']=cur.fetchall()
    cur.execute("""SELECT id,app_id,name,client,config_type,LEFT(config_value,1200) v FROM rufitai.wf_client_config
      WHERE client LIKE '%olive%' OR client LIKE '%payoneer%'""")
    out['wf']=cur.fetchall()
finally:
    cur.close(); conn.close()
print(json.dumps(out,ensure_ascii=False,default=str,indent=1))
