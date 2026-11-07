import json
from commons.mysql_connector import MySQLConnector
conn = MySQLConnector('config/mysql_conn_config.json').get_connection()
cur = conn.cursor(dictionary=True)
out={}
def q(k,sql,args=None):
    try:
        cur.execute(sql,args or ()); out[k]=cur.fetchall()
    except Exception as e: out[k]=f"ERR {e}"
q('apps',"SELECT id,client,customer,app_name,del_flag FROM rufitai.rf_app_info WHERE id IN (2071478687539675137) OR client LIKE '%olive%' OR client LIKE '%react%'")
q('react_apps',"""SELECT r.app_id, r.config_key, r.config_value FROM rufitai.rf_ai_role_config r
  WHERE r.config_key IN ('skill_routing_strategy','session_gap_seconds','react_skip_final','kb_prefetch')
  AND r.del_flag=0 AND r.app_id IN (SELECT app_id FROM rufitai.rf_ai_role_config WHERE config_key='skill_routing_strategy' AND config_value='react_only' AND del_flag=0)""")
cur.close(); conn.close()
print(json.dumps(out,ensure_ascii=False,default=str,indent=1))
