#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Assistant-level Daily Report v2.

This script is intentionally single-assistant first. It does not schedule jobs
and does not enable any legacy daily_report configuration.
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('static_report/assistant_daily_report_v2.py')

import argparse
import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal

import requests

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from commons.mysql_connector import MySQLConnector


TEST_SEND_ALLOWLIST = {
    2016324907307692034: {
        "app_user": "customer_platform_admin_MarsMind_Alice_3_we_com",
        "leader_receiver": "7881299907999181",
        "leader_name": "杨若愚_Luke",
    }
}


def parse_time(value):
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError("Unsupported time format: %s" % value)


def json_default(value):
    if isinstance(value, (datetime,)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def sanitize_text(value, max_len=140):
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"https?://\S+", "[链接]", text)
    text = re.sub(r"(?<!\d)\d{7,}(?!\d)", "[数字已省略]", text)
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def pct(numerator, denominator):
    if not denominator:
        return "0.0%"
    return "%.1f%%" % (float(numerator) * 100.0 / float(denominator))


def normalize_send_base_url(send_url):
    url = (send_url or "").strip()
    if not url:
        return ""
    if url.endswith("/send"):
        return url[: -len("/send")]
    return url.rstrip("/")


def fetch_one(cursor, sql, params):
    cursor.execute(sql, params)
    return cursor.fetchone()


def fetch_all(cursor, sql, params):
    cursor.execute(sql, params)
    return cursor.fetchall()


def load_app(cursor, app_id):
    return fetch_one(
        cursor,
        """
        SELECT id, application_name, customer, channel_type, bind_account_id,
               bind_account_name, online_status, is_enabled, host, port,
               create_user_id, update_time, del_flag
        FROM rf_app_info
        WHERE id = %s
        """,
        (app_id,),
    )


def resolve_app_user(cursor, app, explicit_app_user, start_time, end_time):
    if explicit_app_user:
        return explicit_app_user, []

    candidates = fetch_all(
        cursor,
        """
        SELECT user, COUNT(*) AS message_count,
               MIN(create_time) AS first_message_at,
               MAX(create_time) AS last_message_at
        FROM data_chat_history
        WHERE del_flag = 0
          AND app_id = %s
          AND create_time >= %s
          AND create_time < %s
          AND user IS NOT NULL
          AND TRIM(user) <> ''
        GROUP BY user
        ORDER BY message_count DESC
        LIMIT 20
        """,
        (app.get("id"), start_time, end_time),
    )
    app_name = app.get("application_name")
    if app_name:
        for row in candidates:
            if row.get("user") == app_name:
                return app_name, candidates
    if len(candidates) == 1:
        return candidates[0].get("user"), candidates
    if not candidates and app_name:
        return app_name, candidates
    raise SystemExit(
        "Cannot infer a single app_user for app_id=%s; pass --app-user explicitly. candidates=%s"
        % (app.get("id"), [row.get("user") for row in candidates])
    )


def detect_leaders(cursor, app):
    bind_account_id = app.get("bind_account_id")
    customer = app.get("customer")
    if not bind_account_id:
        return []

    leaders = []
    rows = fetch_all(
        cursor,
        """
        SELECT 'admin' AS source, client, channel, admin_name AS leader_name,
               admin_id AS leader_receiver
        FROM user_admins
        WHERE user_id = %s AND (client = %s OR client = 'customer_platform')
        UNION ALL
        SELECT 'manager' AS source, client, channel, manager_name AS leader_name,
               manager_id AS leader_receiver
        FROM user_managers
        WHERE user_id = %s AND (client = %s OR client = 'customer_platform')
        """,
        (bind_account_id, customer, bind_account_id, customer),
    )
    seen = set()
    for row in rows:
        receiver = row.get("leader_receiver")
        if not receiver or receiver in seen:
            continue
        seen.add(receiver)
        leaders.append(row)
    return leaders


def load_chat_stats(cursor, app, app_user, start_time, end_time):
    return fetch_one(
        cursor,
        """
        SELECT
            COUNT(*) AS total_messages,
            COUNT(DISTINCT session_id) AS session_count,
            COUNT(DISTINCT IFNULL(NULLIF(group_id, ''), IFNULL(other_user_id, from_user_id))) AS room_count,
            COUNT(DISTINCT user) AS data_user_count,
            COUNT(DISTINCT customer) AS observed_customer_count,
            GROUP_CONCAT(DISTINCT customer ORDER BY customer SEPARATOR ',') AS observed_customers,
            SUM(CASE WHEN reply_content IS NOT NULL AND TRIM(reply_content) <> '' THEN 1 ELSE 0 END) AS replied_messages,
            SUM(CASE WHEN UPPER(IFNULL(reply_type, '')) = 'ERROR'
                      OR UPPER(IFNULL(reply_content, '')) LIKE '%ERROR%'
                     THEN 1 ELSE 0 END) AS error_messages,
            SUM(CASE WHEN is_group = 1 THEN 1 ELSE 0 END) AS group_messages,
            MIN(create_time) AS first_message_at,
            MAX(create_time) AS last_message_at
        FROM data_chat_history
        WHERE del_flag = 0
          AND app_id = %s
          AND user = %s
          AND create_time >= %s
          AND create_time < %s
        """,
        (app.get("id"), app_user, start_time, end_time),
    )


def load_user_breakdown(cursor, app, app_user, start_time, end_time):
    return fetch_all(
        cursor,
        """
        SELECT user, COUNT(*) AS message_count,
               SUM(CASE WHEN reply_content IS NOT NULL AND TRIM(reply_content) <> '' THEN 1 ELSE 0 END) AS replied_messages
        FROM data_chat_history
        WHERE del_flag = 0
          AND app_id = %s
          AND user = %s
          AND create_time >= %s
          AND create_time < %s
        GROUP BY user
        ORDER BY message_count DESC
        LIMIT 10
        """,
        (app.get("id"), app_user, start_time, end_time),
    )


def load_categories(cursor, app, app_user, start_time, end_time):
    return fetch_all(
        cursor,
        """
        SELECT
            COALESCE(NULLIF(full_category, ''), NULLIF(primary_category, ''), '(未分类)') AS category,
            COUNT(*) AS count
        FROM data_chat_intent_classification_result
        WHERE app_id = %s
          AND app_user = %s
          AND message_create_time >= %s
          AND message_create_time < %s
          AND status = 'success'
        GROUP BY category
        ORDER BY count DESC
        LIMIT 12
        """,
        (app.get("id"), app_user, start_time, end_time),
    )


def load_intent_status(cursor, app, app_user, start_time, end_time):
    return fetch_one(
        cursor,
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN status <> 'success' THEN 1 ELSE 0 END) AS failed_count
        FROM data_chat_intent_classification_result
        WHERE app_id = %s
          AND app_user = %s
          AND message_create_time >= %s
          AND message_create_time < %s
        """,
        (app.get("id"), app_user, start_time, end_time),
    )


def load_answerability(cursor, app, app_user, start_time, end_time):
    return fetch_one(
        cursor,
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN should_reply = 1 THEN 1 ELSE 0 END) AS should_reply_count,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN status <> 'success' THEN 1 ELSE 0 END) AS failed_count,
            AVG(confidence) AS avg_confidence
        FROM data_chat_answerability_result
        WHERE app_id = %s
          AND app_user = %s
          AND message_create_time >= %s
          AND message_create_time < %s
        """,
        (app.get("id"), app_user, start_time, end_time),
    )


def load_examples(cursor, app, app_user, start_time, end_time, limit):
    return fetch_all(
        cursor,
        """
        SELECT create_time, session_id, group_id, is_group, from_user_nickname,
               actual_user_nickname, send_content, reply_content, reply_type
        FROM data_chat_history
        WHERE del_flag = 0
          AND app_id = %s
          AND user = %s
          AND create_time >= %s
          AND create_time < %s
          AND send_content IS NOT NULL
          AND TRIM(send_content) <> ''
        ORDER BY create_time DESC
        LIMIT %s
        """,
        (app.get("id"), app_user, start_time, end_time, limit),
    )


def load_errors(cursor, app, app_user, start_time, end_time, limit):
    return fetch_all(
        cursor,
        """
        SELECT create_time, session_id, group_id, send_content, reply_content, reply_type
        FROM data_chat_history
        WHERE del_flag = 0
          AND app_id = %s
          AND user = %s
          AND create_time >= %s
          AND create_time < %s
          AND (UPPER(IFNULL(reply_type, '')) = 'ERROR'
               OR UPPER(IFNULL(reply_content, '')) LIKE '%ERROR%')
        ORDER BY create_time DESC
        LIMIT %s
        """,
        (app.get("id"), app_user, start_time, end_time, limit),
    )


def category_deltas(current_categories, previous_categories):
    current = Counter({row["category"]: int(row["count"] or 0) for row in current_categories})
    previous = Counter({row["category"]: int(row["count"] or 0) for row in previous_categories})
    rows = []
    for category in set(current) | set(previous):
        delta = current[category] - previous[category]
        if delta:
            rows.append((category, current[category], previous[category], delta))
    rows.sort(key=lambda item: abs(item[3]), reverse=True)
    return rows[:6]


def assistant_display_name(app):
    return app.get("bind_account_name") or app.get("application_name") or str(app.get("id"))


def build_conclusion(app, stats, categories, errors):
    total = int(stats.get("total_messages") or 0)
    replied = int(stats.get("replied_messages") or 0)
    error_count = int(stats.get("error_messages") or 0)
    top_category = categories[0]["category"] if categories else "暂无分类"
    name = assistant_display_name(app)

    if total == 0:
        return "%s 在本窗口暂无新增消息，leader 只需要确认它是否仍应保持当前启停状态。" % name
    if error_count or errors:
        return "%s 本窗口处理 %s 条消息、AI 回复 %s 条，但出现 %s 条错误，需要优先复核回复链路。" % (
            name,
            total,
            replied,
            error_count,
        )
    return "%s 本窗口处理 %s 条消息、AI 回复 %s 条，主要集中在「%s」，暂未发现明显回复错误。" % (
        name,
        total,
        replied,
        top_category,
    )


def build_report(app, app_user, app_user_candidates, leader, window, stats, user_breakdown, categories, previous_categories,
                 intent_status, answerability, examples, errors):
    start_time, end_time = window
    total = int(stats.get("total_messages") or 0)
    replied = int(stats.get("replied_messages") or 0)
    sessions = int(stats.get("session_count") or 0)
    rooms = int(stats.get("room_count") or 0)
    error_count = int(stats.get("error_messages") or 0)
    reply_rate = pct(replied, total)
    deltas = category_deltas(categories, previous_categories)
    name = assistant_display_name(app)
    conclusion = build_conclusion(app, stats, categories, errors)

    lines = [
        "# %s｜AI助手日报测试" % name,
        "",
        "**结论：%s**" % conclusion,
        "",
        "- 🧩 助手：%s（app_id=%s，app_user=%s，归属 customer=%s）" % (
            name,
            app.get("id"),
            app_user,
            app.get("customer"),
        ),
        "- 👤 leader：%s（receiver=%s）" % (leader.get("leader_name") or "未配置", leader.get("leader_receiver") or "未配置"),
        "- 🕘 窗口：%s 至 %s" % (start_time.strftime("%Y-%m-%d %H:%M"), end_time.strftime("%Y-%m-%d %H:%M")),
        "- 📊 量级：消息 %s 条，会话 %s 个，触达对象 %s 个，AI 回复 %s 条，回复占比 %s" % (
            total,
            sessions,
            rooms,
            replied,
            reply_rate,
        ),
        "- ⚠️ 错误：%s 条回复错误；intent 分类 %s/%s 成功；应答判断 %s 条、建议回复 %s 条" % (
            error_count,
            int(intent_status.get("success_count") or 0),
            int(intent_status.get("total") or 0),
            int(answerability.get("total") or 0),
            int(answerability.get("should_reply_count") or 0),
        ),
    ]

    if categories:
        category_text = "；".join("%s %s条" % (row["category"], int(row["count"] or 0)) for row in categories[:5])
        lines.append("- 🧭 主要场景：%s" % category_text)
    else:
        lines.append("- 🧭 主要场景：本窗口暂无已完成分类。")

    if deltas:
        delta_parts = []
        for category, current_count, previous_count, delta in deltas[:4]:
            arrow = "增加" if delta > 0 else "减少"
            delta_parts.append("%s %s%s条（本期%s / 上期%s）" % (category, arrow, abs(delta), current_count, previous_count))
        lines.append("- 📈 变化：%s" % "；".join(delta_parts))
    else:
        lines.append("- 📈 变化：相对上一窗口没有明显分类波动。")

    if user_breakdown:
        users = "；".join("%s %s条" % (row.get("user") or "(空)", int(row.get("message_count") or 0)) for row in user_breakdown[:3])
        lines.append(
            "- 🔒 数据隔离：本报告只取 `app_id=%s + user=%s`；customer 只作为归属标签，本窗口观测 customer=%s；聊天 user 分布为 %s"
            % (
                app.get("id"),
                app_user,
                stats.get("observed_customers") or app.get("customer") or "无消息",
                users,
            )
        )

    if examples:
        lines.append("")
        lines.append("**代表消息**")
        for idx, row in enumerate(examples[:3], start=1):
            sender = sanitize_text(row.get("actual_user_nickname") or row.get("from_user_nickname") or "未知发送者", 30)
            question = sanitize_text(row.get("send_content"), 120)
            answer = sanitize_text(row.get("reply_content"), 100)
            if not answer:
                answer = "未记录 AI 回复"
            lines.append("%s. %s：%s / AI：%s" % (idx, sender, question, answer))

    if errors:
        lines.append("")
        lines.append("**错误明细**")
        for idx, row in enumerate(errors[:3], start=1):
            lines.append(
                "%s. %s｜reply_type=%s｜%s"
                % (
                    idx,
                    row.get("create_time"),
                    row.get("reply_type") or "",
                    sanitize_text(row.get("reply_content") or row.get("send_content"), 140),
                )
            )

    if not errors and total > 0:
        lines.append("")
        lines.append("**建议动作**")
        lines.append("- ✅ 暂未发现回复错误；leader 可重点看分类变化和代表消息，判断是否需要补充知识。")
    elif errors:
        lines.append("")
        lines.append("**建议动作**")
        lines.append("- ⚠️ 先复核错误消息对应会话，再判断是发送链路、Prompt 还是知识缺口。")

    markdown = "\n".join(lines)
    payload = {
        "app": app,
        "app_user": app_user,
        "app_user_candidates": app_user_candidates,
        "permission_scope": {
            "app_id": app.get("id"),
            "app_user": app_user,
            "customer_is_permission_boundary": False,
            "customer_label": app.get("customer"),
        },
        "leader": leader,
        "window": {
            "start_time": start_time,
            "end_time": end_time,
        },
        "stats": stats,
        "user_breakdown": user_breakdown,
        "categories": categories,
        "previous_categories": previous_categories,
        "category_deltas": [
            {
                "category": category,
                "current": current_count,
                "previous": previous_count,
                "delta": delta,
            }
            for category, current_count, previous_count, delta in deltas
        ],
        "intent_status": intent_status,
        "answerability": answerability,
        "examples": examples,
        "errors": errors,
        "markdown": markdown,
    }
    return markdown, payload


def write_artifacts(output_dir, app_id, payload, markdown):
    now = datetime.now()
    day_dir = os.path.join(output_dir, now.strftime("%Y%m%d"))
    os.makedirs(day_dir, exist_ok=True)
    prefix = os.path.join(day_dir, "assistant_%s_%s" % (app_id, now.strftime("%Y%m%d%H%M%S")))
    json_path = prefix + ".json"
    md_path = prefix + ".md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=json_default)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)
        f.write("\n")
    return json_path, md_path


def ensure_send_allowed(app_id, app_user, leader_receiver):
    allow = TEST_SEND_ALLOWLIST.get(int(app_id))
    if not allow:
        raise RuntimeError("Sending is blocked for app_id=%s. Only the MarsMind Alice test app is allowlisted." % app_id)
    if str(app_user) != str(allow["app_user"]):
        raise RuntimeError(
            "Sending is blocked: app_id=%s can only send with app_user=%s."
            % (app_id, allow["app_user"])
        )
    if str(leader_receiver) != str(allow["leader_receiver"]):
        raise RuntimeError(
            "Sending is blocked: app_id=%s can only send to leader_receiver=%s."
            % (app_id, allow["leader_receiver"])
        )


def send_report(send_url, leader_receiver, markdown):
    base_url = normalize_send_base_url(send_url)
    if not base_url:
        raise RuntimeError("--send-url is required when --send is set")
    payload = {
        "content": markdown,
        "receiver": str(leader_receiver),
        "is_group": "false",
        "is_id": "true",
        "data_type": "TEXT",
        "add_onlinesession_context": "false",
    }
    response = requests.post(base_url + "/send", json=payload, timeout=30)
    response.raise_for_status()
    try:
        result = response.json()
    except ValueError:
        return False, "send service returned non-JSON response: %s" % response.text
    return bool(result.get("success")), json.dumps(result, ensure_ascii=False)


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Generate one assistant-level Daily Report v2.")
    parser.add_argument("--app-id", type=int, required=True)
    parser.add_argument("--app-user", help="Bound app user. If omitted, the script infers one user from app_id in the report window.")
    parser.add_argument("--sql-config", default="config/mysql_conn_config.json")
    parser.add_argument("--output-dir", default="data/assistant_daily_report_v2")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--start-time")
    parser.add_argument("--end-time")
    parser.add_argument("--example-limit", type=int, default=6)
    parser.add_argument("--leader-name")
    parser.add_argument("--leader-receiver")
    parser.add_argument("--send-url")
    parser.add_argument("--send", action="store_true", help="Actually send to leader. Dry-run is the default.")
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="[%(levelname)s] [%(asctime)s] [%(filename)s:%(lineno)d]: %(message)s",
    )

    end_time = parse_time(args.end_time) or datetime.now()
    start_time = parse_time(args.start_time) or (end_time - timedelta(days=args.days))
    if start_time >= end_time:
        raise SystemExit("--start-time must be earlier than --end-time")

    connector = MySQLConnector(args.sql_config)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        app = load_app(cursor, args.app_id)
        if not app:
            raise SystemExit("app_id=%s not found in rf_app_info" % args.app_id)
        if app.get("del_flag"):
            raise SystemExit("app_id=%s is deleted; blocked" % args.app_id)

        app_user, app_user_candidates = resolve_app_user(cursor, app, args.app_user, start_time, end_time)
        detected_leaders = detect_leaders(cursor, app)
        leader = {
            "leader_name": args.leader_name,
            "leader_receiver": args.leader_receiver,
            "source": "args",
        }
        if not leader["leader_receiver"] and detected_leaders:
            chosen = detected_leaders[0]
            leader = {
                "leader_name": chosen.get("leader_name"),
                "leader_receiver": chosen.get("leader_receiver"),
                "source": chosen.get("source"),
            }

        stats = load_chat_stats(cursor, app, app_user, start_time, end_time) or {}
        user_breakdown = load_user_breakdown(cursor, app, app_user, start_time, end_time)
        categories = load_categories(cursor, app, app_user, start_time, end_time)
        previous_start = start_time - (end_time - start_time)
        previous_categories = load_categories(cursor, app, app_user, previous_start, start_time)
        intent_status = load_intent_status(cursor, app, app_user, start_time, end_time) or {}
        answerability = load_answerability(cursor, app, app_user, start_time, end_time) or {}
        examples = load_examples(cursor, app, app_user, start_time, end_time, args.example_limit)
        errors = load_errors(cursor, app, app_user, start_time, end_time, args.example_limit)
    finally:
        connector.close_connection(conn, cursor)

    markdown, payload = build_report(
        app=app,
        app_user=app_user,
        app_user_candidates=app_user_candidates,
        leader=leader,
        window=(start_time, end_time),
        stats=stats,
        user_breakdown=user_breakdown,
        categories=categories,
        previous_categories=previous_categories,
        intent_status=intent_status,
        answerability=answerability,
        examples=examples,
        errors=errors,
    )
    payload["detected_leaders"] = detected_leaders
    payload["send"] = {
        "requested": bool(args.send),
        "send_url": args.send_url,
        "leader_receiver": leader.get("leader_receiver"),
        "leader_name": leader.get("leader_name"),
    }

    json_path, md_path = write_artifacts(args.output_dir, args.app_id, payload, markdown)
    logging.info("wrote artifacts json=%s markdown=%s", json_path, md_path)

    print(markdown)
    print("\n--- artifacts ---")
    print(json_path)
    print(md_path)

    if args.send:
        if not leader.get("leader_receiver"):
            raise SystemExit("--leader-receiver is required when --send is set")
        ensure_send_allowed(args.app_id, app_user, leader.get("leader_receiver"))
        ok, message = send_report(args.send_url, leader.get("leader_receiver"), markdown)
        print("\n--- send result ---")
        print(json.dumps({"ok": ok, "message": message}, ensure_ascii=False))
        if not ok:
            raise SystemExit("send failed: %s" % message)
    else:
        print("\n--- dry-run ---")
        print("No message sent. Use --send to send the allowlisted MarsMind Alice test report.")


if __name__ == "__main__":
    main()
