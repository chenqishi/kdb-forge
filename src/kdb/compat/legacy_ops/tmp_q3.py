import json
from commons.mysql_connector import MySQLConnector
conn = MySQLConnector('config/mysql_conn_config.json').get_connection()
cur = conn.cursor(dictionary=True)
out={}
def q(k,sql,args=None):
    try:
        cur.execute(sql,args or ())
        out[k]=cur.fetchall()
    except Exception as e:
        out[k]=f"ERR {e}"
q('gap',"SELECT app_id,config_value,update_time FROM rufitai.rf_ai_role_config WHERE config_key='session_gap_seconds' AND del_flag=0")
q('levers',"""SELECT app_id,config_key,config_value FROM rufitai.rf_ai_role_config
  WHERE config_key IN ('kb_prefetch_style','kb_prefetch_rewrite','max_iterations','dual_query_recall','query_completion_prompt','no_knowledge_policy','react_final_model','react_step_model','risk_control','output_verify') AND del_flag=0""")
q('wfcols',"SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='rufitai' AND TABLE_NAME='wf_client_config' ORDER BY ORDINAL_POSITION")
q('wf',"SELECT * FROM rufitai.wf_client_config WHERE client LIKE '%olive%' OR client LIKE '%payoneer%'")
cur.close(); conn.close()
print(json.dumps(out,ensure_ascii=False,default=str,indent=1))
