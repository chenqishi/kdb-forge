import json
from commons.mysql_connector import MySQLConnector
conn = MySQLConnector('config/mysql_conn_config.json').get_connection()
cur = conn.cursor(dictionary=True)
out={}
def q(k,sql,args=None):
    try:
        cur.execute(sql,args or ()); out[k]=cur.fetchall()
    except Exception as e: out[k]=f"ERR {e}"
q('cols',"SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='rufitai' AND TABLE_NAME='rf_app_info' ORDER BY ORDINAL_POSITION")
q('app',"SELECT * FROM rufitai.rf_app_info WHERE id=2071478687539675137")
cur.close(); conn.close()
print(json.dumps(out,ensure_ascii=False,default=str,indent=1)[:2500])
