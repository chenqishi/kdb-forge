import json
from commons.mysql_connector import MySQLConnector
conn = MySQLConnector('config/mysql_conn_config.json').get_connection()
cur = conn.cursor(dictionary=True)
out={}
def q(k,sql,args=None):
    try:
        cur.execute(sql,args or ()); out[k]=cur.fetchall()
    except Exception as e: out[k]=f"ERR {e}"
q('olive_settings',"SELECT client,config_type,config_json,version,enabled FROM rufitai.wf_client_config WHERE client='payoneer_olive' AND config_type='settings'")
q('olive_flow',"SELECT client,config_type,config_json,version,enabled FROM rufitai.wf_client_config WHERE client IN ('payoneer_olive','__generic__') AND config_type='flow' AND enabled=1")
cur.close(); conn.close()
print(json.dumps(out,ensure_ascii=False,default=str,indent=1))
