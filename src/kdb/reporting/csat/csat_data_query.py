#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
CSAT 满意度报告数据查询模块

按时间范围和渠道类型，从 data_csat_result 和 data_online_sessions 中聚合
每份问卷对应的会话信息及转人工情况。
"""
import logging
from datetime import datetime

from mysql.connector import Error

ESCALATION_KEYWORD = '正在帮您转人工'


def query_csat_sessions(mysql_connector, start_time, end_time, channel_type, client, include_chat_detail=False):
    """
    查询 CSAT 会话报告，按 survey_instance 分组返回对话明细。

    Args:
        mysql_connector: 已初始化的 MySQLConnector 实例
        start_time:   查询起始时间（data_csat_result.create_time >= start_time）
        end_time:     查询结束时间（data_csat_result.create_time <= end_time）
        channel_type: 渠道类型，用于过滤两张表
        client:              租户/客户标识，过滤 data_csat_result.client
        include_chat_detail: 是否在结果中包含 chat_detail，默认 False

    Returns:
        list[dict]，每个元素对应一条 survey 记录，字段见 function_schema
    """
    connection = mysql_connector.get_connection()
    if connection is None:
        raise RuntimeError('无法获取数据库连接')

    try:
        cursor = connection.cursor(dictionary=True)

        # ── Step 1: 获取时间范围内的 CSAT 结果 ──────────────────────────────
        cursor.execute(
            """
            SELECT survey_instance_id, robot_id, session_id, reply_result, create_time, account_id
            FROM data_csat_result
            WHERE create_time >= %s
              AND create_time <= %s
              AND channel_type = %s
              AND client = %s
            """,
            (start_time, end_time, channel_type, client)
        )
        csat_results = cursor.fetchall()

        if not csat_results:
            return []

        # ── Step 2: 收集 session_id 集合 ─────────────────────────────────────
        session_ids = list({r['session_id'] for r in csat_results if r['session_id']})

        # ── Step 2.5: 查询窗口之前各 session 最近一份 survey 时间 ────────────
        # 用于修正第一份 survey 的消息下界，避免遗漏窗口前的问卷导致消息范围过宽
        placeholders = ','.join(['%s'] * len(session_ids))
        cursor.execute(
            f"""
            SELECT session_id, MAX(create_time) as prev_survey_time
            FROM data_csat_result
            WHERE session_id IN ({placeholders})
              AND create_time < %s
            GROUP BY session_id
            """,
            session_ids + [start_time]
        )
        prev_survey_times = {r['session_id']: r['prev_survey_time'] for r in cursor.fetchall()}

        # ── Step 3: 获取对应的在线会话消息 ──────────────────────────────────
        # 注意：data_online_sessions.channel 与 data_csat_result.channel_type 使用相同值
        placeholders = ','.join(['%s'] * len(session_ids))
        cursor.execute(
            f"""
            SELECT session_id, sender_name, sender_id, mess_type, mess_data_type,
                   content, create_time
            FROM data_online_sessions
            WHERE session_id IN ({placeholders})
              AND channel = %s
              AND IFNULL(del_flag, 0) != 1
            ORDER BY session_id, create_time ASC
            """,
            session_ids + [channel_type]
        )
        online_msgs = cursor.fetchall()

        # ── Step 4: 按 session_id 分组消息 ──────────────────────────────────
        session_messages: dict = {}
        for msg in online_msgs:
            sid = msg['session_id']
            session_messages.setdefault(sid, []).append(msg)

        # ── Step 5: 按 session_id 分组 CSAT，每组按 create_time 升序 ─────────
        session_surveys: dict = {}
        for r in csat_results:
            sid = r['session_id']
            session_surveys.setdefault(sid, []).append(r)
        for sid in session_surveys:
            session_surveys[sid].sort(key=lambda x: x['create_time'])

        # ── Step 6: 按 survey 切分消息窗口并组装输出 ─────────────────────────
        records = []
        for session_id, surveys in session_surveys.items():
            messages = session_messages.get(session_id, [])
            # 确保消息按时间升序（数据库查询已排序，这里做防御性排序）
            messages.sort(key=lambda x: x['create_time'] or datetime.min)

            for i, survey in enumerate(surveys):
                survey_time = survey['create_time']

                if i == 0:
                    prev_time = prev_survey_times.get(session_id)
                    if prev_time:
                        # 窗口前存在历史问卷，以其时间为下界，避免消息范围过宽
                        lower_bound = prev_time
                    else:
                        lower_bound = _get_first_survey_lower_bound(messages, survey_time)
                else:
                    lower_bound = surveys[i - 1]['create_time']

                group_msgs = _filter_messages(messages, lower_bound, survey_time)

                # 若关联不到任何消息，跳过该 survey（如同一 session 重复发问卷导致窗口无消息）
                if not group_msgs:
                    continue

                record = _build_record(survey, session_id, group_msgs, include_chat_detail)
                records.append(record)

        return records

    except Error as e:
        logging.error(f'数据库查询失败: {e}')
        raise
    finally:
        mysql_connector.close_connection(connection, cursor)


def _get_first_survey_lower_bound(messages, survey_time):
    """
    第一份 survey 的消息下界：
    取 survey_time 之前最后一条含转人工关键词的消息时间；
    若无，则取 session 内第一条消息的时间（即 None 表示无下界）。
    """
    escalation_before = [
        m for m in messages
        if m['create_time'] and m['create_time'] <= survey_time
        and m['content'] and ESCALATION_KEYWORD in m['content']
    ]
    if escalation_before:
        return escalation_before[-1]['create_time']
    # 无转人工记录，从 session 最早消息时间开始；messages 为空则返回 None（无下界）
    return messages[0]['create_time'] if messages else None


def _filter_messages(messages, lower_bound, upper_bound):
    """按时间窗口过滤消息，两侧均带等号。"""
    result = []
    for m in messages:
        t = m['create_time']
        if t is None:
            continue
        if upper_bound is not None and t > upper_bound:
            continue
        if lower_bound is not None and t < lower_bound:
            continue
        result.append(m)
    return result


def _build_record(survey, session_id, group_msgs, include_chat_detail=False):
    """将一组消息和 survey 元数据组装为输出 dict。"""
    # session_create_datetime：组内第一条消息时间
    session_create_dt = group_msgs[0]['create_time'] if group_msgs else None

    # 转人工判断：组内含关键词的第一条消息
    escalation_msgs = [
        m for m in group_msgs
        if m['content'] and ESCALATION_KEYWORD in m['content']
    ]
    escalated = 'Yes' if escalation_msgs else 'No'
    escalation_dt = escalation_msgs[0]['create_time'] if escalation_msgs else None

    record = {
        'survey_instance_id': survey['survey_instance_id'],
        'query_session_id': session_id,
        'account_id': survey.get('account_id'),
        'session_create_datetime': _fmt_dt(session_create_dt),
        'escalated': escalated,
        'escalation_datetime': _fmt_dt(escalation_dt),
        'satisfaction': survey['reply_result'],
    }

    if include_chat_detail:
        record['chat_detail'] = [
            {
                'sender_name': m['sender_name'],
                'sender_id': m['sender_id'],
                'content': m['content'],
                'mess_type': m['mess_type'],
                'create_time': _fmt_dt(m['create_time']),
            }
            for m in group_msgs
        ]

    return record


def _fmt_dt(dt):
    """将 datetime 对象格式化为字符串，None 保持 None。"""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    return str(dt)
