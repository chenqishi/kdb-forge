from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
用户 ID 映射查询模块

从 data_scrm 和 data_scrm_id_map 聚合用户的 cid、email、
external_id 映射（致趣 + 公众号双通道），并按机器人(robot_name)拆行。

返回结构（每行一个 (cid, channel, robot) 组合）:
- 一个 cid 在致趣下被多个机器人添加 → 拆成多行
- 公众号通道没有"机器人"概念，robot_name = None
- cid 无任何 external_id → 1 行: external_id=None, source=None, robot_name=None
"""
import json
import logging
import os

from mysql.connector import Error

TYPE_WECOM_SERVICE = 'wechatcom_service_substitute'
TYPE_ZHIQU = 'zhiqu_external_id'
SOURCE_BY_TYPE = {TYPE_WECOM_SERVICE: 'wecom_service', TYPE_ZHIQU: 'zhiqu'}

# 入参 client 别名：传入 key 时，data_scrm 过滤扩到 value 里所有 client。
# data_scrm_id_map 步骤本就不按 client 过滤；sid_to_robots 索引按 key 读（共享 cron 产物）。
CLIENT_ALIASES = {
    'mercado': ['mercado', 'mercado_local'],
}

BASE = str(_PROJECT_ROOT)
# sid -> [robot_name, ...]，由 cron 写出（其值就是「致趣 user_owner 名字 ∩ scope 内 16 助手」）
DEFAULT_SID_ROBOTS_PATH_TMPL = os.path.join(BASE, 'config', 'zhiqu_sid_to_robots_{client}.json')
# nick_name -> rfwkt_we_com_user_id (marsmind 助手内部 id) 反查数据源；用于按 robot 精确取 email
DEFAULT_ASSISTANT_MAP_PATH = os.path.join(BASE, 'config', 'zhiqu_assistant_id_map.json')


def _load_sid_to_robots(client, path_override=None):
    """加载 sid -> [robot_name, ...]，来源为 cron 写出的索引文件。"""
    path = path_override or DEFAULT_SID_ROBOTS_PATH_TMPL.format(client=client)
    if not os.path.exists(path):
        logging.warning('sid_to_robots 索引不存在: %s, robot_name 将全为 None', path)
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.warning('读取 %s 失败: %s', path, e)
        return {}


def _load_robot_to_marsmind_uid(client, path_override=None):
    """反向 zhiqu_assistant_id_map.json：nick_name -> rfwkt_we_com_user_id (== data_scrm.user_id)。

    用于把 zhiqu 每个 robot 精确对上 data_scrm 里"那个助手写的 profile"，进而拿独立 email。
    """
    path = path_override or DEFAULT_ASSISTANT_MAP_PATH
    if not os.path.exists(path):
        logging.warning('assistant_map 不存在: %s, zhiqu 行 email 精确匹配将全 None', path)
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
    except Exception as e:
        logging.warning('读取 %s 失败: %s', path, e)
        return {}
    entry = (d or {}).get(client) or {}
    out = {}
    for a in entry.get('assistants', []) or []:
        nm = (a.get('nick_name') or '').strip()
        uid = a.get('rfwkt_we_com_user_id')
        if nm and uid:
            out[nm] = str(uid)
    return out


def _load_cid_to_name(cursor, cids):
    """按 cid 反查 rfwkt 外部好友姓名: nick_name 优先, fallback real_name。"""
    if not cids:
        return {}
    out = {}
    ids = list(cids)
    for i in range(0, len(ids), 1000):
        chunk = ids[i:i + 1000]
        ph = ','.join(['%s'] * len(chunk))
        cursor.execute(
            f"""
            SELECT we_com_contact_user_id AS cid,
                   we_com_contact_nick_name AS nick,
                   we_com_contact_real_name AS real_n
            FROM rf_wkt_we_com_contact
            WHERE we_com_contact_user_id IN ({ph})
              AND we_com_contact_relation_type = 2
              AND we_com_contact_type = 1
              AND del_flag = 0
            """,
            chunk,
        )
        for r in cursor.fetchall():
            if r['cid'] in out:
                continue
            name = (r['nick'] or '').strip() or (r['real_n'] or '').strip() or None
            out[r['cid']] = name
    return out


def query_user_id_map(mysql_connector, client, start_time, end_time, user_id=None,
                      sid_robots_path=None, assistant_map_path=None):
    """
    查询 cid / email / external_id 映射，按 (cid, channel, robot) 拆行。

    Args:
        mysql_connector: 已初始化的 MySQLConnector
        client:     租户标识
        start_time: 起始时间
        end_time:   结束时间
        user_id:    可选，str 或 list[str]
        sid_robots_path: 可选，覆盖默认的 sid_to_robots 索引文件路径
        assistant_map_path: 可选，覆盖默认的 zhiqu_assistant_id_map 路径

    Returns:
        list[dict]，每条:
          cid:           str
          email:         str | None  (zhiqu 行按 (cid, robot 的 marsmind uid) 精确取；wecom/兜底行取 cid 级)
          customer_name: str | None  (rfwkt contact 的 nick_name 优先，fallback real_name)
          external_id:   str | None
          source:        'zhiqu' | 'wecom_service' | None
          robot_name:    str | None
        cid 级过滤：该 cid 若所有 data_scrm 行都无 email，则整体丢弃。
    """
    connection = mysql_connector.get_connection()
    if connection is None:
        raise RuntimeError('无法获取数据库连接')

    try:
        cursor = connection.cursor(dictionary=True)

        # Step 1: data_scrm 筛选（支持 client 别名扩展）
        scrm_clients = CLIENT_ALIASES.get(client, [client])
        ph_clients = ','.join(['%s'] * len(scrm_clients))
        sql = f"""
            SELECT cid, user_id, customer_profile_info
            FROM data_scrm
            WHERE client IN ({ph_clients})
              AND create_time >= %s
              AND create_time <= %s
              AND (status IS NULL OR status != 'before_scrm')
        """
        params = list(scrm_clients) + [start_time, end_time]

        if user_id:
            user_ids = [user_id] if isinstance(user_id, str) else list(user_id)
            placeholders_uid = ','.join(['%s'] * len(user_ids))
            sql += f' AND user_id IN ({placeholders_uid})'
            params.extend(user_ids)

        cursor.execute(sql, params)
        scrm_rows = cursor.fetchall()
        if not scrm_rows:
            return []

        # Step 2: 双 type 查 external_id
        cids = list({r['cid'] for r in scrm_rows if r['cid']})
        cid_to_zhiqu = {}
        cid_to_wecom = {}
        if cids:
            placeholders = ','.join(['%s'] * len(cids))
            cursor.execute(
                f"""
                SELECT cid, sid, type
                FROM data_scrm_id_map
                WHERE cid IN ({placeholders})
                  AND type IN (%s, %s)
                """,
                cids + [TYPE_WECOM_SERVICE, TYPE_ZHIQU],
            )
            for row in cursor.fetchall():
                if row['type'] == TYPE_ZHIQU:
                    cid_to_zhiqu.setdefault(row['cid'], row['sid'])
                elif row['type'] == TYPE_WECOM_SERVICE:
                    cid_to_wecom.setdefault(row['cid'], row['sid'])

        # Step 3: 加载 sid -> robots 索引（由 cron 写出）
        sid_to_robots = _load_sid_to_robots(client, sid_robots_path)
        # Step 3b: 加载 robot_name -> marsmind uid（用于 zhiqu 行按 (cid, uid) 精确取 email）
        robot_to_uid = _load_robot_to_marsmind_uid(client, assistant_map_path)

        # Step 4: 按 cid 反查 customer_name
        cid_to_name = _load_cid_to_name(cursor, cids)

        # Step 5a: 建 (cid, user_id) -> email 索引 & cid -> 任一 email（用于 cid 级过滤和 wecom/兜底行 email）
        cid_uid_email = {}
        cid_any_email = {}
        for r in scrm_rows:
            cid = r['cid']
            uid = str(r.get('user_id')) if r.get('user_id') is not None else None
            email = _parse_email(r.get('customer_profile_info'))
            if uid is not None:
                # 同一 (cid, uid) 若有多条 profile，保留第一条命中的非空 email
                if cid_uid_email.get((cid, uid)) is None:
                    cid_uid_email[(cid, uid)] = email
            if email and not cid_any_email.get(cid):
                cid_any_email[cid] = email

        # Step 5b: 按 cid 循环组装（每 cid 只 emit 一次，避免多行 data_scrm 拆重复）
        records = []
        seen_cids = set()
        for row in scrm_rows:
            cid = row['cid']
            if cid in seen_cids:
                continue
            seen_cids.add(cid)
            fallback_email = cid_any_email.get(cid)
            if not fallback_email:
                # cid 级过滤：该 cid 所有 data_scrm 行都无 email → 整体丢弃
                continue
            cust_name = cid_to_name.get(cid)
            zhiqu_sid = cid_to_zhiqu.get(cid)
            wecom_sid = cid_to_wecom.get(cid)
            emitted = False
            if zhiqu_sid:
                robots = sid_to_robots.get(zhiqu_sid) or [None]
                for r_name in robots:
                    uid = robot_to_uid.get(r_name) if r_name else None
                    row_email = cid_uid_email.get((cid, uid)) if uid else None
                    records.append({
                        'cid': cid,
                        'email': row_email,
                        'customer_name': cust_name,
                        'external_id': zhiqu_sid,
                        'source': SOURCE_BY_TYPE[TYPE_ZHIQU],
                        'robot_name': r_name,
                    })
                emitted = True
            if wecom_sid:
                records.append({
                    'cid': cid,
                    'email': fallback_email,
                    'customer_name': cust_name,
                    'external_id': wecom_sid,
                    'source': SOURCE_BY_TYPE[TYPE_WECOM_SERVICE],
                    'robot_name': None,
                })
                emitted = True
            if not emitted:
                records.append({
                    'cid': cid,
                    'email': fallback_email,
                    'customer_name': cust_name,
                    'external_id': None,
                    'source': None,
                    'robot_name': None,
                })
        return records

    except Error as e:
        logging.error(f'数据库查询失败: {e}')
        raise
    finally:
        mysql_connector.close_connection(connection, cursor)


def _parse_email(profile_info_str):
    """从 customer_profile_info JSON 中提取 email。"""
    if not profile_info_str:
        return None
    try:
        info = json.loads(profile_info_str)
        for item in info.get('clue_cleaning', []):
            if item.get('cleaningKey') == 'email':
                return item.get('cleaningValue') or None
    except (json.JSONDecodeError, AttributeError):
        pass
    return None
