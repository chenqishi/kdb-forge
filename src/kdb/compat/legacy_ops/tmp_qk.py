import json
from commons.mysql_connector import MySQLConnector
conn = MySQLConnector('config/mysql_conn_config.json').get_connection()
cur = conn.cursor(dictionary=True)
out={}
try:
    cur.execute("""SELECT config_key, COUNT(*) c, COUNT(DISTINCT app_id) apps FROM rufitai.rf_ai_role_config
      WHERE del_flag=0 GROUP BY config_key ORDER BY config_key""")
    out['all_keys']=cur.fetchall()
    cur.execute("""SELECT config_key,config_value FROM rufitai.rf_ai_role_config WHERE app_id=2071478687539675137
      AND config_key IN ('keyword_direct_reply','react_skip_final','kb_prefetch','kb_prefetch_rerank','enable_rerank',
      'skill_routing_strategy','prompt_contexts','use_hot_assistant','no_reply_question','need_reply_question')""")
    out['olive']=cur.fetchall()
    cur.execute("""SELECT app_id, config_value, COUNT(*) c FROM rufitai.rf_ai_role_config
      WHERE config_key='skill_routing_strategy' AND del_flag=0 GROUP BY app_id,config_value""")
    out['strategy_by_app']=cur.fetchall()
finally:
    cur.close(); conn.close()
print(json.dumps(out,ensure_ascii=False,default=str,indent=1))
