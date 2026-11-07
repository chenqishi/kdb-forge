from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
从 data_chat_history 提炼客户真实用户 query 与高频意图。

用途：仅用于校准知识抽取“方向”（用户真实会问什么），不直接把聊天内容变成知识答案。

数据来源（参考 static_report/stat_chat_distribution.py 中的真实列名）：
    表：data_chat_history
    - customer         客户名（client 过滤列；其它表用 client）
    - send_content     用户消息文本（top 问题分布即基于该列）
    - send_type        消息类型，文本消息为 'TEXT'
    - create_time      消息时间
    - content_category 消息类别（可选）

降级策略：
    - 数据库不可用、配置缺失、列名不存在或任何异常 → 返回空列表 / 空意图，不中断主任务。
"""

import logging
import os
import re
from typing import List, Optional

# 过滤用：图片/链接、纯表情、无意义寒暄
_URL_OR_IMAGE_RE = re.compile(r"https?://|\.(jpg|jpeg|png|gif|webp|bmp)\b", re.IGNORECASE)
_EMOJI_ONLY_RE = re.compile(
    r"^[\s\W_]*$"  # 仅符号/空白（含大部分 emoji 与标点）
)
_GREETING_WORDS = [
    "你好", "您好", "在吗", "在么", "哈喽", "hello", "hi", "嗨", "谢谢", "感谢",
    "好的", "嗯", "ok", "收到", "辛苦了", "再见", "拜拜", "早上好", "晚上好",
]


def _default_mysql_config_path() -> Optional[str]:
    """定位默认 mysql 配置文件。"""
    project_root = str(_PROJECT_ROOT)
    candidate = os.path.join(project_root, "config", "mysql_conn_config.json")
    return candidate if os.path.exists(candidate) else None


def _is_meaningful_query(text: str) -> bool:
    """判定一条用户消息是否值得作为意图分析输入。"""
    if not text:
        return False
    t = text.strip()
    if len(t) < 4:
        return False
    if _URL_OR_IMAGE_RE.search(t):
        return False
    if _EMOJI_ONLY_RE.match(t):
        return False
    low = t.lower()
    # 纯寒暄（整条消息基本等于寒暄词）
    for w in _GREETING_WORDS:
        if low == w or (len(t) <= 6 and w in low):
            return False
    return True


def load_client_queries(
    *,
    client: str,
    admin_user_id: Optional[str] = None,
    app_id: Optional[str] = None,
    days: int = 180,
    limit: int = 1000,
    mysql_config_path: Optional[str] = None,
) -> List[str]:
    """查询 data_chat_history 中同 client 的用户真实问题，过滤并去重。

    任何异常（无配置/连不上/列名不符）都会被吞掉并返回空列表，保证主任务不中断。

    Args:
        client: 客户名（对应 data_chat_history.customer）。
        admin_user_id/app_id: 预留过滤维度（当前 data_chat_history 无对应列时忽略）。
        days: 取最近多少天的消息。
        limit: 最多取多少条原始消息。
        mysql_config_path: mysql 配置文件路径，缺省自动定位 config/mysql_conn_config.json。

    Returns:
        去重、清洗后的用户 query 列表；不可用时为空列表。
    """
    if not client:
        logging.warning("chat_query_context: client 为空，跳过 data_chat_history 查询")
        return []

    cfg_path = mysql_config_path or _default_mysql_config_path()
    if not cfg_path or not os.path.exists(cfg_path):
        logging.warning(f"chat_query_context: 未找到 mysql 配置({cfg_path})，降级返回空 query")
        return []

    connection = None
    cursor = None
    try:
        from kdb.shared.clients.mysql_connector import MySQLConnector

        connector = MySQLConnector(cfg_path)
        connection = connector.get_connection()
        if connection is None:
            logging.warning("chat_query_context: 获取数据库连接失败，降级返回空 query")
            return []
        cursor = connection.cursor()

        # 仅取文本消息、指定客户、时间窗内；按时间倒序取最近 limit 条
        sql = (
            "SELECT send_content FROM data_chat_history "
            "WHERE customer = %s AND send_type = 'TEXT' "
            "AND create_time >= (NOW() - INTERVAL %s DAY) "
            "ORDER BY create_time DESC LIMIT %s"
        )
        cursor.execute(sql, (client, int(days), int(limit)))
        rows = cursor.fetchall()

        seen = set()
        queries: List[str] = []
        for row in rows:
            text = (row[0] or "").strip() if row and row[0] is not None else ""
            if not _is_meaningful_query(text):
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            queries.append(text)

        logging.info(
            f"chat_query_context: client={client} 原始消息={len(rows)} 有效去重 query={len(queries)}"
        )
        return queries
    except Exception as exc:
        logging.warning(f"chat_query_context: 查询 data_chat_history 失败，降级返回空 query: {exc}")
        return []
    finally:
        try:
            if cursor is not None:
                cursor.close()
            if connection is not None and connection.is_connected():
                connection.close()
        except Exception:
            pass


def _fallback_intents(queries: List[str], top_n: int = 20) -> List[dict]:
    """LLM 不可用时的兜底：按归一化文本做简单频次聚合，输出高频意图。"""
    from collections import Counter

    counter: Counter = Counter()
    samples: dict = {}
    for q in queries:
        norm = re.sub(r"\s+", "", q)[:30]
        counter[norm] += 1
        samples.setdefault(norm, []).append(q)
    intents = []
    for norm, _cnt in counter.most_common(top_n):
        intents.append({"intent": norm, "sample_queries": samples[norm][:3]})
    return intents


def summarize_query_intents(
    queries: List[str],
    *,
    client: str,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    max_intents: int = 30,
) -> List[dict]:
    """把用户 query 聚类为高频意图。

    优先用本地 LLM 聚类；LLM 不可用 / 解析失败时退化为频次兜底。

    Returns:
        [{"intent": str, "sample_queries": [str, ...]}, ...]；输入为空时返回 []。
    """
    if not queries:
        return []

    try:
        from kdb.shared.clients.local_llm_adapter import request_knowledge_llm
    except Exception as exc:
        logging.warning(f"chat_query_context: 无法导入 local_llm_adapter，使用频次兜底: {exc}")
        return _fallback_intents(queries, top_n=max_intents)

    # 控制 prompt 体积，最多采样 300 条
    sample_queries = queries[:300]
    numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(sample_queries))
    system_message = (
        f"你是客服会话分析专家。下面是客户「{client}」的真实用户问题。"
        "请把它们聚类成高频业务意图，只输出 JSON 数组，不要 Markdown。"
        f'格式：[{{"intent":"意图简述","sample_queries":["原始问题1","原始问题2"]}}]。'
        f"最多输出 {max_intents} 个意图，按高频优先。只保留有业务价值的问题意图，"
        "忽略寒暄、闲聊、无意义短句。"
    )
    content = request_knowledge_llm(
        query=numbered,
        system_message=system_message,
        model_name=model_name,
        provider=provider,
        temperature=0.1,
        max_tokens=4000,
    )
    if not content:
        return _fallback_intents(queries, top_n=max_intents)

    import json

    text = content.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        obj = json.loads(text)
    except Exception:
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                obj = json.loads(text[start:end + 1])
            except Exception:
                logging.warning("chat_query_context: 意图 JSON 解析失败，使用频次兜底")
                return _fallback_intents(queries, top_n=max_intents)
        else:
            return _fallback_intents(queries, top_n=max_intents)

    if not isinstance(obj, list):
        return _fallback_intents(queries, top_n=max_intents)

    intents = []
    for item in obj[:max_intents]:
        if not isinstance(item, dict):
            continue
        intent = str(item.get("intent", "")).strip()
        if not intent:
            continue
        sq = item.get("sample_queries", [])
        if not isinstance(sq, list):
            sq = [str(sq)]
        intents.append({"intent": intent, "sample_queries": [str(x) for x in sq[:5]]})
    return intents or _fallback_intents(queries, top_n=max_intents)
