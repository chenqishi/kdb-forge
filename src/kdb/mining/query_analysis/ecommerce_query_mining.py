#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
从 data_chat_history 挖掘电商平台知识覆盖率测评 query。

推荐流程：
1. 一次性从 data_chat_history 随机下载 1-2 万条样本到本地 JSONL。
2. 后续所有候选构造、清洗、LLM 泛化都只基于本地样本执行。
3. 小批量调用低成本 LLM，把聊天式问题泛化为自包含测评 query。
4. 跨批次去重、按主题限额采样，输出 CSV/JSONL/报告。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('query_understanding_analysis/ecommerce_query_mining.py')

import argparse
import csv
import json
import logging
import math
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from commons.mysql_connector import MySQLConnector


_URL_OR_IMAGE_RE = re.compile(r"https?://|www\.|\.((jpg)|(jpeg)|(png)|(gif)|(webp)|(bmp)|(pdf))\b", re.I)
_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\s，。！？!?、,.；;：:（）()【】\[\]《》<>\"'“”‘’`~\-_/\\|]+")
_QUOTE_PREFIX_RE = re.compile(r"^(回复|引用|转发|@[^：:]+[:：]|[A-Za-z0-9_\-\u4e00-\u9fff]{1,20}[:：])")

_GREETING_WORDS = {
    "你好", "您好", "在吗", "在么", "哈喽", "hello", "hi", "嗨", "谢谢", "感谢",
    "好的", "好", "嗯", "ok", "收到", "辛苦了", "再见", "拜拜", "早上好", "晚上好",
    "可以", "不客气", "麻烦了",
}

_NOISE_KEYWORDS = (
    "企业微信", "客户群", "打卡", "微盘", "通讯录", "审批", "日程", "会议",
    "卖群", "群码", "换群", "各行业各类型", "加v", "加V", "加微", "出售",
    "我已经添加了你", "联系人信息已更新", "小程序", "祝您生意兴隆",
    "欢迎咨询", "有需要", "私信我", "公众号", "直播时间", "点击报名",
    "联系电话", "微信同号", "换标支持", "推荐一个靠谱", "现店，可立马交付",
)

_ALERT_NOISE_KEYWORDS = (
    "告警", "警告", "报警", "系统通知", "通知消息", "消息通知", "消息更新",
    "提醒消息", "状态提醒", "运营状态或消息更新", "通知在哪里看",
)

_BUSINESS_KEYWORDS = (
    "入驻", "入住", "开店", "注册", "招商", "店铺", "卖家", "商家", "账号", "账户",
    "审核", "资质", "资料", "营业执照", "法人", "kyc", "KYC", "品牌", "授权",
    "类目", "品类", "商品", "产品", "sku", "SKU", "刊登", "上架", "listing",
    "运营", "流量", "广告", "活动", "促销", "报名", "优惠券", "折扣", "销量",
    "订单", "发货", "物流", "仓库", "海外仓", "尾程", "运费", "配送", "时效",
    "自发货", "FBM", "FBA",
    "退货", "退款", "售后", "纠纷", "评价", "差评", "罚款", "限流", "封店",
    "佣金", "费率", "费用", "保证金", "月租", "结算", "提现", "收款", "支付",
    "美客多", "mercado", "Mercado", "wayfair", "Wayfair", "rakuten", "乐天",
    "onbuy", "OnBuy", "amazon", "亚马逊", "shopee", "Shopee", "tiktok", "TikTok",
    "temu", "Temu", "平台", "站点", "后台", "erp", "ERP",
)

_THEME_RULES = (
    ("入驻开店", ("入驻", "入住", "开店", "注册", "招商", "店铺", "卖家", "商家")),
    ("账号资质", ("账号", "账户", "审核", "资质", "资料", "营业执照", "法人", "kyc", "KYC")),
    ("商品刊登", ("商品", "产品", "sku", "SKU", "刊登", "上架", "listing", "类目", "品类")),
    ("订单物流", ("订单", "发货", "物流", "仓库", "海外仓", "尾程", "运费", "配送", "时效")),
    ("运营营销", ("运营", "流量", "广告", "活动", "促销", "报名", "优惠券", "折扣", "销量")),
    ("费用结算", ("佣金", "费率", "费用", "保证金", "月租", "结算", "提现", "收款", "支付")),
    ("售后风控", ("退货", "退款", "售后", "纠纷", "评价", "差评", "罚款", "限流", "封店")),
)

_PLATFORM_ALIASES = {
    "mercado libre": "美客多平台",
    "mercadolibre": "美客多平台",
    "mercado": "美客多平台",
    "美客多": "美客多平台",
    "wayfair": "Wayfair",
    "rakuten": "Rakuten",
    "乐天": "Rakuten",
    "onbuy": "OnBuy",
    "amazon": "Amazon",
    "亚马逊": "Amazon",
    "shopee": "Shopee",
    "tiktok": "TikTok Shop",
    "temu": "Temu",
}

_PLATFORM_CUSTOMER_NAMES = {
    "mercado": "美客多平台",
    "wayfair": "Wayfair",
    "letain": "Letain",
}

_MERCADO_SITE_COUNTRIES = (
    "墨西哥", "巴西", "加拿大", "乌拉圭", "阿根廷", "智利", "哥伦比亚", "美国",
)

_MERCADO_SITE_PATTERN = re.compile(
    r"(?:Mercado\s*Libre|mercado\s*libre|mercadolibre|美客多|Mercado)\s*"
    r"(墨西哥|巴西|加拿大|乌拉圭|阿根廷|智利|哥伦比亚|美国)\s*(?:站点|站|市场)?",
    re.I,
)

_PLATFORM_SPECIFIC_REPLACEMENTS = (
    (_MERCADO_SITE_PATTERN, "{platform}"),
    (re.compile(r"Mercado\s*Libre|mercado\s*libre|mercadolibre|美客多|Mercado", re.I), "{platform}"),
    (re.compile(r"Wayfair|wayfair", re.I), "{platform}"),
    (re.compile(r"Amazon|amazon|亚马逊", re.I), "{platform}"),
    (re.compile(r"Shopee|shopee|虾皮", re.I), "{platform}"),
    (re.compile(r"TikTok\s*Shop|TikTok|tiktok", re.I), "{platform}"),
    (re.compile(r"Temu|TEMU|temu", re.I), "{platform}"),
    (re.compile(r"电商平台"), "{platform}平台"),
)


def parse_time_arg(value: Optional[str], end_of_day: bool = False) -> Optional[str]:
    """把命令行时间参数转成 MySQL datetime 字符串。"""
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    if len(value) == 14 and value.isdigit():
        return datetime.strptime(value, "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    if len(value) == 10 and re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        suffix = "23:59:59" if end_of_day else "00:00:00"
        return f"{value} {suffix}"
    if len(value) == 19 and re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", value):
        return value
    raise ValueError(f"不支持的时间格式: {value}")


def normalize_text(text: Optional[str]) -> str:
    """清洗单条聊天文本。"""
    if text is None:
        return ""
    cleaned = str(text).replace("\u2006", "").replace("\u00a0", " ")
    cleaned = cleaned.replace("\r", "\n")
    lines = []
    for line in cleaned.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _URL_OR_IMAGE_RE.search(line):
            continue
        line = _QUOTE_PREFIX_RE.sub("", line).strip()
        if line:
            lines.append(line)
    cleaned = " ".join(lines)
    cleaned = _SPACE_RE.sub(" ", cleaned).strip()
    return cleaned[:300]


def is_meaningful_query(text: str) -> bool:
    """过滤明显不适合做测评 query 的聊天文本。"""
    text = normalize_text(text)
    if not text:
        return False
    low = text.lower()
    if len(text) > 220:
        return False
    has_business_word = any(keyword.lower() in low for keyword in _BUSINESS_KEYWORDS)
    if len(text) < 4 and not (len(text) >= 2 and has_business_word):
        return False
    if low in _GREETING_WORDS:
        return False
    if len(text) <= 8 and any(word in low for word in _GREETING_WORDS):
        return False
    if _URL_OR_IMAGE_RE.search(text):
        return False
    if re.fullmatch(r"[\W_]+", text, re.UNICODE):
        return False
    if re.fullmatch(r"[\d\s.,，。:：-]+", text):
        return False
    if is_noise_text(text):
        return False
    fragment_words = ("这个", "那个", "怎么弄", "看下", "帮忙看看", "如图", "图片", "截图", "还是不行")
    if len(text) <= 12 and any(word in text for word in fragment_words):
        return False
    return True


def is_noise_text(text: str) -> bool:
    """识别企业微信提示、广告和纯 @ 助手等噪声。"""
    text = normalize_text(text)
    if not text:
        return True
    low = text.lower()
    if any(keyword.lower() in low for keyword in _NOISE_KEYWORDS):
        return True
    if re.fullmatch(r"@[\w\-\u4e00-\u9fff+]+", text):
        return True
    if text.startswith("@") and len(text) <= 40:
        return True
    if re.search(r"(微信|v[:：]?|电话|手机).{0,8}\d{6,}", low) and not re.search(r"(怎么|如何|哪些|什么|是否|吗|？|\?)", text):
        return True
    if re.search(r"\d{6,}.{0,12}(微信|v|电话|手机)", low) and not re.search(r"(怎么|如何|哪些|什么|是否|吗|？|\?)", text):
        return True
    if re.search(r"\d{6,}", text) and any(word in text for word in ("欢迎咨询", "同行", "资源", "群")):
        return True
    has_question_signal = bool(re.search(r"(怎么|如何|哪些|什么|是否|能不能|可以|为什么|哪里|多久|吗|？|\?)", text))
    if len(text) > 80 and not has_question_signal:
        return True
    return False


def is_alert_noise_query(text: str) -> bool:
    """判断是否为告警、通知或消息更新类噪声。"""
    text = normalize_text(text)
    if not text:
        return True
    low = text.lower()
    if any(keyword.lower() in low for keyword in _ALERT_NOISE_KEYWORDS):
        return True
    if re.search(r"(消息|通知|提醒).{0,8}(更新|状态|查看|查询|在哪里|在哪)", text):
        return True
    return False


def is_business_query(text: str) -> bool:
    """判断是否属于电商平台入驻/运营业务域。"""
    text = normalize_text(text)
    if not is_meaningful_query(text):
        return False
    low = text.lower()
    if any(keyword.lower() in low for keyword in _BUSINESS_KEYWORDS):
        return True
    return bool(re.search(r"(怎么|如何|哪里|哪些|什么|是否|能不能|可以).{0,20}(平台|后台|店铺|订单|发货|收款)", text))


def normalize_query_key(text: str) -> str:
    """生成 query 去重 key。"""
    key = normalize_text(text).lower()
    for alias, canonical in _PLATFORM_ALIASES.items():
        key = key.replace(alias.lower(), canonical.lower())
    key = _PUNCT_RE.sub("", key)
    return key[:120]


def sanitize_query_text(text: str) -> str:
    """清理最终 query 中的聊天 @ 前缀和冗余符号。"""
    text = normalize_text(text)
    if not text:
        return ""
    text = re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "注册邮箱", text)
    text = re.sub(r"(?<!\d)\d{8,}(?!\d)", "具体编号", text)
    text = re.sub(r"@[\w\-\u4e00-\u9fff+·.]{1,35}(?:\s*[（(][^）)]*[）)])?", " ", text)
    text = re.sub(r"\([^)]*小助手[^)]*\)", " ", text)
    text = re.sub(r"（[^）]*小助手[^）]*）", " ", text)
    text = _SPACE_RE.sub(" ", text).strip(" ，,。")
    text = text.replace("是怎样的是什么", "是怎样的")
    text = text.replace("是什么是什么", "是什么")
    text = re.sub(r"？{2,}", "？", text)
    text = re.sub(r"\?+", "？", text)
    if text and not text.endswith("？"):
        text = text.rstrip("。.") + "？"
    return text


def normalize_platform_specific_query(text: str) -> str:
    """生成平台占位符 query 模板。"""
    template = sanitize_query_text(text)
    if not template:
        return ""
    for pattern, replacement in _PLATFORM_SPECIFIC_REPLACEMENTS:
        template = pattern.sub(replacement, template)
    template = re.sub(r"\{platform\}\s*\{platform\}", "{platform}", template)
    template = re.sub(r"\{platform\}\s*平台平台", "{platform}平台", template)
    template = re.sub(
        r"\{platform\}(自发货|官方仓|转运仓)?(墨西哥|巴西|加拿大|乌拉圭|阿根廷|智利|哥伦比亚|美国)(?:站点|站|市场)",
        r"{platform}\1",
        template,
    )
    template = re.sub(r"在\{platform\}平台[，,]\s*\{platform\}平台", "{platform}平台", template)
    if "{platform}" not in template:
        template = f"在{{platform}}平台，{template}"
    template = _SPACE_RE.sub(" ", template).strip()
    template = re.sub(r"？{2,}", "？", template)
    if template and not template.endswith("？"):
        template = template.rstrip("。.") + "？"
    return template


def extract_mercado_site_platforms(text: str) -> List[str]:
    """从 query 中提取美客多站点级平台。"""
    text = normalize_text(text)
    if not text:
        return []
    has_mercado = bool(re.search(r"Mercado\s*Libre|mercado\s*libre|mercadolibre|美客多|Mercado", text, re.I))
    if not has_mercado:
        return []
    platforms = []
    for country in _MERCADO_SITE_COUNTRIES:
        if country in text:
            platform = f"美客多{country}站点"
            if platform not in platforms:
                platforms.append(platform)
    return platforms


def extract_platform_names_for_query(
    text: str,
    source_customers: str = "",
    platform_scope: str = "",
) -> List[str]:
    """从来源 customer、platform_scope 和 query 中抽取平台名。"""
    mercado_site_platforms = extract_mercado_site_platforms(text)
    if mercado_site_platforms:
        return mercado_site_platforms

    source_platforms: List[str] = []
    for raw_customer in str(source_customers or "").split(","):
        customer = raw_customer.strip().lower()
        platform = _PLATFORM_CUSTOMER_NAMES.get(customer)
        if platform and platform not in source_platforms:
            source_platforms.append(platform)

    text_platforms: List[str] = []
    text_haystack = str(text or "").lower()
    for alias, canonical in _PLATFORM_ALIASES.items():
        if canonical not in _PLATFORM_CUSTOMER_NAMES.values():
            continue
        if alias.lower() in text_haystack and canonical not in text_platforms:
            text_platforms.append(canonical)
    if len(source_platforms) > 1 and text_platforms:
        return text_platforms
    if source_platforms:
        return source_platforms

    platforms = list(text_platforms)
    haystack = f"{text} {platform_scope}".lower()
    for alias, canonical in _PLATFORM_ALIASES.items():
        if alias.lower() in haystack and canonical not in platforms:
            platforms.append(canonical)
    if platforms:
        return platforms
    return ["电商平台"]


def build_platform_queries(template: str, platforms: Sequence[str]) -> List[dict]:
    """把占位符模板按平台实例化成具体 query。"""
    clean_template = normalize_platform_specific_query(template)
    results = []
    for platform in platforms:
        platform_name = normalize_text(platform)
        if not platform_name:
            continue
        query = clean_template.replace("{platform}", platform_name)
        query = re.sub(r"电商平台平台", "电商平台", query)
        query = re.sub(r"平台平台", "平台", query)
        query = re.sub(r"站点站点", "站点", query)
        query = re.sub(r"\s+", " ", query).strip()
        if query and not query.endswith("？"):
            query = query.rstrip("。.") + "？"
        results.append({"platform": platform_name, "query": query})
    deduped = []
    seen = set()
    for item in results:
        key = (item["platform"], item["query"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def merge_candidate_stats(candidates: Sequence[dict]) -> List[dict]:
    """按规范化 key 合并候选统计。"""
    merged: Dict[str, dict] = {}
    for item in candidates:
        query = normalize_text(item.get("source_query"))
        key = normalize_query_key(query)
        if not key:
            continue
        if key not in merged:
            merged[key] = dict(item)
            merged[key]["source_query"] = query
            continue
        current = merged[key]
        current["cnt"] = int(current.get("cnt") or 0) + int(item.get("cnt") or 0)
        current["source_customers"] = ",".join(sorted(set(
            [x for x in str(current.get("source_customers", "")).split(",") if x]
            + [x for x in str(item.get("source_customers", "")).split(",") if x]
        )))
        categories = []
        for value in (current.get("categories", ""), item.get("categories", "")):
            categories.extend([x.strip() for x in str(value).split("|") if x.strip()])
        current["categories"] = " | ".join(dict.fromkeys(categories))[:500]
        current["latest_time"] = max(str(current.get("latest_time") or ""), str(item.get("latest_time") or ""))
    return sorted(merged.values(), key=lambda x: (-int(x.get("cnt") or 0), x.get("source_query", "")))


def build_where_clause(
    customers: Sequence[str],
    start_time: Optional[str],
    end_time: Optional[str],
    users: Optional[Sequence[str]] = None,
    app_ids: Optional[Sequence[str]] = None,
    require_reply: bool = True,
) -> Tuple[str, List[object]]:
    """构造 data_chat_history 只读查询 WHERE 片段。"""
    clean_customers = [c.strip() for c in customers if c and c.strip()]
    if not clean_customers:
        raise ValueError("customers 不能为空")

    clauses = [
        f"customer IN ({','.join(['%s'] * len(clean_customers))})",
        "send_type = 'TEXT'",
        "send_content IS NOT NULL",
        "send_content != ''",
        "(channel_type IS NULL OR channel_type != 'wework_juhe')",
    ]
    params: List[object] = list(clean_customers)
    if start_time:
        clauses.append("create_time >= %s")
        params.append(start_time)
    if end_time:
        clauses.append("create_time < %s")
        params.append(end_time)
    if users:
        clean_users = [u.strip() for u in users if u and u.strip()]
        if clean_users:
            clauses.append(f"user IN ({','.join(['%s'] * len(clean_users))})")
            params.extend(clean_users)
    if app_ids:
        clean_app_ids = [a.strip() for a in app_ids if a and str(a).strip()]
        if clean_app_ids:
            clauses.append(f"CAST(app_id AS CHAR) IN ({','.join(['%s'] * len(clean_app_ids))})")
            params.extend(clean_app_ids)
    if require_reply:
        clauses.append("reply_content IS NOT NULL")
        clauses.append("reply_content != ''")
        clauses.append("reply_content NOT LIKE %s")
        params.append("%我暂时遇到了一些问题，请您稍后重试%")
    return " AND ".join(clauses), params


def write_jsonl_rows(output_path: str, rows: Sequence[dict]) -> str:
    """将聊天记录写为 JSONL 样本文件。"""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return output_path


def fetch_random_chat_sample(
    connector: MySQLConnector,
    customers: Sequence[str],
    sample_size: int,
    start_time: Optional[str],
    end_time: Optional[str],
    users: Optional[Sequence[str]] = None,
    app_ids: Optional[Sequence[str]] = None,
    require_reply: bool = True,
    per_customer_even: bool = True,
    random_seed: Optional[int] = None,
) -> List[dict]:
    """从 data_chat_history 随机抽取聊天记录。"""
    clean_customers = [c.strip() for c in customers if c and c.strip()]
    if not clean_customers:
        raise ValueError("customers 不能为空")
    if sample_size <= 0:
        raise ValueError("sample_size 必须大于 0")

    if per_customer_even:
        base = sample_size // len(clean_customers)
        remainder = sample_size % len(clean_customers)
        customer_limits = {
            customer: base + (1 if idx < remainder else 0)
            for idx, customer in enumerate(clean_customers)
        }
    else:
        customer_limits = {customer: sample_size for customer in clean_customers}

    conn = connector.get_connection()
    if conn is None:
        raise RuntimeError("获取 MySQL 连接失败")
    cursor = conn.cursor(dictionary=True)
    rows: List[dict] = []
    try:
        for idx, customer in enumerate(clean_customers):
            limit = int(customer_limits[customer])
            if limit <= 0:
                continue
            where_sql, params = build_where_clause(
                [customer],
                start_time,
                end_time,
                users=users,
                app_ids=app_ids,
                require_reply=require_reply,
            )
            rand_expr = "RAND()"
            if random_seed is not None:
                rand_expr = f"RAND({int(random_seed) + idx})"
            sql = f"""
                SELECT
                    id,
                    customer,
                    user,
                    app_id,
                    session_id,
                    msg_id,
                    send_type,
                    send_content,
                    LEFT(COALESCE(reply_content, ''), 1200) AS reply_content,
                    content_category,
                    norm_content,
                    regular_content,
                    create_time,
                    channel_type,
                    from_user_nickname,
                    other_user_nickname
                FROM data_chat_history
                WHERE {where_sql}
                ORDER BY {rand_expr}
                LIMIT %s
            """
            cursor.execute(sql, params + [limit])
            customer_rows = cursor.fetchall()
            logging.info("随机下载 customer=%s target=%s actual=%s", customer, limit, len(customer_rows))
            for row in customer_rows:
                normalized = {}
                for key, value in row.items():
                    normalized[key] = str(value) if isinstance(value, datetime) else value
                rows.append(normalized)
        return rows
    finally:
        connector.close_connection(conn, cursor)


def download_random_sample(
    mysql_config_path: str,
    customers: Sequence[str],
    sample_size: int,
    sample_output_path: str,
    start_time: Optional[str],
    end_time: Optional[str],
    users: Optional[Sequence[str]] = None,
    app_ids: Optional[Sequence[str]] = None,
    require_reply: bool = True,
    per_customer_even: bool = True,
    random_seed: Optional[int] = None,
) -> dict:
    """随机下载 data_chat_history 样本到本地 JSONL。"""
    connector = create_mysql_connector(mysql_config_path)
    rows = fetch_random_chat_sample(
        connector=connector,
        customers=customers,
        sample_size=sample_size,
        start_time=start_time,
        end_time=end_time,
        users=users,
        app_ids=app_ids,
        require_reply=require_reply,
        per_customer_even=per_customer_even,
        random_seed=random_seed,
    )
    write_jsonl_rows(sample_output_path, rows)
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("customer") or "")] += 1
    return {
        "sample_output_path": sample_output_path,
        "sample_size_requested": sample_size,
        "sample_size_actual": len(rows),
        "customers": list(customers),
        "customer_counts": dict(sorted(counts.items())),
        "require_reply": require_reply,
        "per_customer_even": per_customer_even,
        "random_seed": random_seed,
    }


def load_local_sample_rows(sample_path: str) -> List[dict]:
    """读取本地 JSONL 样本。"""
    rows = []
    with open(sample_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def build_candidate_stats_from_rows(
    rows: Sequence[dict],
    max_candidates: int = 1000,
    sample_per_query: int = 2,
) -> List[dict]:
    """基于本地样本构造候选 query 统计。"""
    grouped: Dict[str, dict] = {}
    seen_msg_keys: Dict[str, set] = defaultdict(set)
    for row in rows:
        source_query = normalize_text(
            row.get("regular_content") or row.get("norm_content") or row.get("send_content")
        )
        if not is_business_query(source_query):
            continue
        key = normalize_query_key(source_query)
        if not key:
            continue
        msg_key = str(row.get("msg_id") or row.get("id") or f"row-{len(seen_msg_keys[key])}")
        if msg_key in seen_msg_keys[key]:
            continue
        seen_msg_keys[key].add(msg_key)

        if key not in grouped:
            grouped[key] = {
                "source_query": source_query,
                "cnt": 0,
                "source_customers": set(),
                "categories": [],
                "latest_time": "",
                "samples": [],
            }
        item = grouped[key]
        item["cnt"] += 1
        if row.get("customer"):
            item["source_customers"].add(str(row.get("customer")))
        category = normalize_text(row.get("content_category"))
        if category and category not in item["categories"]:
            item["categories"].append(category)
        create_time = str(row.get("create_time") or "")
        if create_time > item["latest_time"]:
            item["latest_time"] = create_time
        if len(item["samples"]) < sample_per_query:
            item["samples"].append({
                "send_content": normalize_text(row.get("send_content")),
                "reply_content": normalize_text(row.get("reply_content")),
                "customer": row.get("customer") or "",
                "content_category": row.get("content_category") or "",
                "create_time": create_time,
            })

    candidates = []
    for item in grouped.values():
        candidates.append({
            "source_query": item["source_query"],
            "cnt": item["cnt"],
            "source_customers": ",".join(sorted(item["source_customers"])),
            "categories": " | ".join(item["categories"])[:500],
            "latest_time": item["latest_time"],
            "samples": item["samples"],
        })
    candidates.sort(key=lambda x: (-int(x.get("cnt") or 0), x.get("source_query", "")))
    logging.info("本地样本记录=%s，候选=%s，进入候选上限=%s", len(rows), len(candidates), max_candidates)
    return candidates[:max_candidates]


def fetch_candidate_stats(
    connector: MySQLConnector,
    customers: Sequence[str],
    start_time: Optional[str],
    end_time: Optional[str],
    users: Optional[Sequence[str]] = None,
    app_ids: Optional[Sequence[str]] = None,
    raw_limit: int = 20000,
    require_reply: bool = True,
) -> List[dict]:
    """从 data_chat_history 聚合候选 query 统计。"""
    where_sql, params = build_where_clause(
        customers, start_time, end_time, users=users, app_ids=app_ids, require_reply=require_reply
    )
    source_expr = "COALESCE(NULLIF(regular_content,''), NULLIF(norm_content,''), NULLIF(send_content,''))"
    sql = f"""
        SELECT
            source_query,
            COUNT(DISTINCT msg_key) AS cnt,
            GROUP_CONCAT(DISTINCT customer ORDER BY customer SEPARATOR ',') AS source_customers,
            GROUP_CONCAT(DISTINCT category_short ORDER BY category_short SEPARATOR ' | ') AS categories,
            MAX(create_time) AS latest_time
        FROM (
            SELECT
                {source_expr} AS source_query,
                COALESCE(NULLIF(msg_id, ''), CAST(id AS CHAR)) AS msg_key,
                customer,
                LEFT(COALESCE(content_category, ''), 80) AS category_short,
                create_time
            FROM data_chat_history
            WHERE {where_sql}
        ) AS t
        WHERE source_query IS NOT NULL AND source_query != ''
        GROUP BY source_query
        ORDER BY cnt DESC, latest_time DESC
        LIMIT %s
    """
    conn = connector.get_connection()
    if conn is None:
        raise RuntimeError("获取 MySQL 连接失败")
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params + [int(raw_limit)])
        rows = cursor.fetchall()
        results = []
        for row in rows:
            source_query = normalize_text(row.get("source_query"))
            if not is_business_query(source_query):
                continue
            results.append({
                "source_query": source_query,
                "cnt": int(row.get("cnt") or 0),
                "source_customers": row.get("source_customers") or "",
                "categories": row.get("categories") or "",
                "latest_time": str(row.get("latest_time") or ""),
            })
        merged_results = merge_candidate_stats(results)
        logging.info("SQL 聚合候选=%s，规则过滤后=%s，合并后=%s", len(rows), len(results), len(merged_results))
        return merged_results
    finally:
        connector.close_connection(conn, cursor)


def fetch_samples_for_queries(
    connector: MySQLConnector,
    source_queries: Sequence[str],
    customers: Sequence[str],
    start_time: Optional[str],
    end_time: Optional[str],
    users: Optional[Sequence[str]] = None,
    app_ids: Optional[Sequence[str]] = None,
    per_query: int = 2,
    require_reply: bool = True,
) -> Dict[str, List[dict]]:
    """为候选 query 获取少量原始样本。"""
    clean_queries = [q for q in source_queries if q]
    if not clean_queries:
        return {}
    where_sql, params = build_where_clause(
        customers, start_time, end_time, users=users, app_ids=app_ids, require_reply=require_reply
    )
    source_expr = "COALESCE(NULLIF(regular_content,''), NULLIF(norm_content,''), NULLIF(send_content,''))"
    placeholders = ",".join(["%s"] * len(clean_queries))
    sql = f"""
        SELECT source_query, send_content, reply_content, customer, content_category, create_time
        FROM (
            SELECT
                {source_expr} AS source_query,
                send_content,
                LEFT(COALESCE(reply_content, ''), 300) AS reply_content,
                customer,
                content_category,
                create_time
            FROM data_chat_history
            WHERE {where_sql}
        ) AS t
        WHERE source_query IN ({placeholders})
        ORDER BY source_query, (reply_content IS NOT NULL AND reply_content != '') DESC, create_time DESC
    """
    conn = connector.get_connection()
    if conn is None:
        raise RuntimeError("获取 MySQL 连接失败")
    cursor = conn.cursor(dictionary=True)
    samples: Dict[str, List[dict]] = defaultdict(list)
    try:
        cursor.execute(sql, params + clean_queries)
        for row in cursor.fetchall():
            source_query = normalize_text(row.get("source_query"))
            if len(samples[source_query]) >= per_query:
                continue
            samples[source_query].append({
                "send_content": normalize_text(row.get("send_content")),
                "reply_content": normalize_text(row.get("reply_content")),
                "customer": row.get("customer") or "",
                "content_category": row.get("content_category") or "",
                "create_time": str(row.get("create_time") or ""),
            })
        return dict(samples)
    finally:
        connector.close_connection(conn, cursor)


def create_mysql_connector(mysql_config_path: str, retries: int = 3, sleep_seconds: float = 3.0) -> MySQLConnector:
    """创建 MySQLConnector，并对偶发连接超时做有限重试。"""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return MySQLConnector(mysql_config_path)
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                break
            logging.warning("创建 MySQL 连接失败，%s/%s 次，%.1fs 后重试: %s", attempt, retries, sleep_seconds, exc)
            time.sleep(sleep_seconds)
    raise last_exc


def _guess_theme(text: str) -> str:
    for theme, keywords in _THEME_RULES:
        if any(keyword in text for keyword in keywords):
            return theme
    return "其它运营问题"


def _guess_platform(text: str, source_customers: str = "") -> str:
    low = f"{text} {source_customers}".lower()
    for alias, canonical in _PLATFORM_ALIASES.items():
        if alias.lower() in low:
            return canonical
    return "通用电商平台"


def _questionize(text: str, platform: str) -> str:
    text = normalize_text(text).rstrip("？?。.")
    if not text:
        return ""
    if not re.search(r"(怎么|怎样|如何|什么|哪些|多少|是否|能不能|可以|为什么|哪里|多久|吗)", text):
        text = f"{platform} {text}" if platform != "通用电商平台" and platform not in text else text
        text = f"{text}是什么"
    text = text.replace("入住", "入驻")
    if not text.endswith("？"):
        text += "？"
    return text


def fallback_generalize_batch(candidates: Sequence[dict]) -> List[dict]:
    """LLM 不可用时的规则泛化。"""
    records = []
    for item in candidates:
        source_query = normalize_text(item.get("source_query"))
        if not is_business_query(source_query):
            continue
        platform = _guess_platform(source_query, item.get("source_customers", ""))
        query = _questionize(source_query, platform)
        if not query:
            continue
        cnt = int(item.get("cnt") or 0)
        priority = "P0" if cnt >= 20 else "P1" if cnt >= 5 else "P2"
        records.append({
            "query": query,
            "theme": _guess_theme(query),
            "subtheme": "",
            "platform_scope": platform,
            "priority": priority,
            "evidence_count": cnt,
            "source_queries": [source_query],
            "sample_queries": [s.get("send_content", "") for s in item.get("samples", []) if s.get("send_content")][:3],
            "source_customers": item.get("source_customers", ""),
            "categories": item.get("categories", ""),
            "reason": "规则泛化",
        })
    return records


def llm_generalize_batch(
    candidates: Sequence[dict],
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    batch_index: int = 0,
    skip_llm: bool = False,
) -> List[dict]:
    """用低成本 LLM 泛化一批候选 query。"""
    if skip_llm:
        return fallback_generalize_batch(candidates)
    try:
        from commons.local_llm_adapter import request_knowledge_llm
    except Exception as exc:
        logging.warning("无法导入 local_llm_adapter，使用规则泛化: %s", exc)
        return fallback_generalize_batch(candidates)

    compact = []
    for idx, item in enumerate(candidates, 1):
        compact.append({
            "id": idx,
            "source_query": item.get("source_query", ""),
            "count": item.get("cnt", 0),
            "customers": item.get("source_customers", ""),
            "categories": item.get("categories", ""),
            "samples": [
                {
                    "q": s.get("send_content", ""),
                    "a": s.get("reply_content", ""),
                }
                for s in item.get("samples", [])[:2]
            ],
        })
    system_message = (
        "你是电商平台智能客服测评 query 挖掘专家。请把真实聊天候选问题泛化成可用于"
        "知识覆盖率评测的通用 query。要求：\n"
        "1. 只保留电商平台入驻、开店、资质、商品刊登、运营营销、订单物流、费用结算、售后风控相关问题。\n"
        "2. 输出问题必须自包含，不能依赖“这个/那个/如图/上面”等上下文。\n"
        "3. 不输出答案，不编造政策事实；只生成用户会问的问题。\n"
        "4. 合并语义重复候选，可以把口语改写成自然问法，例如“如何入驻 Mercado Libre？”。\n"
        "5. 输出 JSON 数组，不要 Markdown。每项字段："
        "query, theme, subtheme, platform_scope, priority, source_ids, reason。"
        "priority 只能是 P0/P1/P2，P0 表示高频核心覆盖问题。"
    )
    content = request_knowledge_llm(
        query=json.dumps(compact, ensure_ascii=False),
        system_message=system_message,
        model_name=model_name,
        provider=provider,
        temperature=0.1,
        max_tokens=5000,
    )
    if not content:
        logging.warning("LLM 第 %s 批返回空，使用规则泛化", batch_index)
        return fallback_generalize_batch(candidates)

    text = content.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        start, end = text.find("["), text.rfind("]")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start:end + 1])
            except Exception as exc:
                logging.warning("LLM 第 %s 批 JSON 解析失败，使用规则泛化: %s", batch_index, exc)
                return fallback_generalize_batch(candidates)
        else:
            logging.warning("LLM 第 %s 批未找到 JSON 数组，使用规则泛化", batch_index)
            return fallback_generalize_batch(candidates)

    if not isinstance(parsed, list):
        return fallback_generalize_batch(candidates)

    id_to_candidate = {idx + 1: item for idx, item in enumerate(candidates)}
    records = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        query = normalize_text(item.get("query"))
        if not is_business_query(query):
            continue
        source_ids = item.get("source_ids") or []
        if not isinstance(source_ids, list):
            source_ids = [source_ids]
        source_items = [id_to_candidate.get(int(sid)) for sid in source_ids if str(sid).isdigit()]
        source_items = [x for x in source_items if x]
        if not source_items:
            source_items = [id_to_candidate.get(1)] if id_to_candidate else []
        evidence_count = sum(int(x.get("cnt") or 0) for x in source_items)
        source_queries = [x.get("source_query", "") for x in source_items if x.get("source_query")]
        sample_queries = []
        for source_item in source_items:
            for sample in source_item.get("samples", [])[:2]:
                sample_q = sample.get("send_content", "")
                if sample_q and sample_q not in sample_queries:
                    sample_queries.append(sample_q)
        records.append({
            "query": _questionize(query, _guess_platform(query)),
            "theme": normalize_text(item.get("theme")) or _guess_theme(query),
            "subtheme": normalize_text(item.get("subtheme")),
            "platform_scope": normalize_text(item.get("platform_scope")) or _guess_platform(query),
            "priority": item.get("priority") if item.get("priority") in {"P0", "P1", "P2"} else "P1",
            "evidence_count": evidence_count,
            "source_queries": source_queries[:5],
            "sample_queries": sample_queries[:5],
            "source_customers": ",".join(sorted({x.get("source_customers", "") for x in source_items if x.get("source_customers")})),
            "categories": " | ".join(x.get("categories", "") for x in source_items if x.get("categories"))[:500],
            "reason": normalize_text(item.get("reason")),
        })
    return records or fallback_generalize_batch(candidates)


def merge_records(records: Sequence[dict], max_queries: int = 1000, per_theme_limit: int = 0) -> List[dict]:
    """跨批次合并、去重并排序。"""
    merged: Dict[str, dict] = {}
    for record in records:
        query = sanitize_query_text(record.get("query"))
        if is_alert_noise_query(query):
            continue
        if not is_business_query(query):
            continue
        norm_query = normalize_platform_specific_query(query)
        if not norm_query or is_alert_noise_query(norm_query):
            continue
        key = normalize_query_key(query)
        if not key:
            continue
        if key not in merged:
            record = dict(record)
            record["query"] = _questionize(query, record.get("platform_scope") or _guess_platform(query))
            record["norm_query"] = normalize_platform_specific_query(record["query"])
            record["target_platforms"] = extract_platform_names_for_query(
                record["query"],
                record.get("source_customers", ""),
                record.get("platform_scope", ""),
            )
            record["platform_queries"] = build_platform_queries(record["norm_query"], record["target_platforms"])
            record["source_queries"] = list(record.get("source_queries") or [])
            record["sample_queries"] = list(record.get("sample_queries") or [])
            merged[key] = record
            continue
        current = merged[key]
        current["evidence_count"] = int(current.get("evidence_count") or 0) + int(record.get("evidence_count") or 0)
        current["source_queries"] = list(dict.fromkeys(current.get("source_queries", []) + list(record.get("source_queries") or [])))[:8]
        current["sample_queries"] = list(dict.fromkeys(current.get("sample_queries", []) + list(record.get("sample_queries") or [])))[:8]
        if current.get("priority", "P2") > record.get("priority", "P2"):
            current["priority"] = record.get("priority")
        current_platforms = list(current.get("target_platforms") or [])
        record_platforms = extract_platform_names_for_query(
            record.get("query", ""),
            record.get("source_customers", ""),
            record.get("platform_scope", ""),
        )
        current["target_platforms"] = list(dict.fromkeys(current_platforms + record_platforms))
        current["platform_queries"] = build_platform_queries(current.get("norm_query", ""), current["target_platforms"])

    def sort_key(item: dict) -> Tuple[int, float, str]:
        priority_rank = {"P0": 0, "P1": 1, "P2": 2}.get(item.get("priority"), 3)
        evidence_score = -math.log1p(int(item.get("evidence_count") or 0))
        return priority_rank, evidence_score, item.get("query", "")

    sorted_records = sorted(merged.values(), key=sort_key)
    if per_theme_limit > 0:
        theme_counts = defaultdict(int)
        limited = []
        for item in sorted_records:
            theme = item.get("theme") or "其它"
            if theme_counts[theme] >= per_theme_limit:
                continue
            theme_counts[theme] += 1
            limited.append(item)
            if len(limited) >= max_queries:
                break
        return limited
    return sorted_records[:max_queries]


def write_outputs(output_dir: str, candidates: Sequence[dict], records: Sequence[dict], metadata: dict) -> dict:
    """写出候选、最终 query 和报告。"""
    os.makedirs(output_dir, exist_ok=True)
    candidates_csv = os.path.join(output_dir, "candidates.csv")
    queries_csv = os.path.join(output_dir, "coverage_queries.csv")
    queries_by_platform_csv = os.path.join(output_dir, "coverage_queries_by_platform.csv")
    queries_jsonl = os.path.join(output_dir, "coverage_queries.jsonl")
    report_md = os.path.join(output_dir, "report.md")

    with open(candidates_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["source_query", "cnt", "source_customers", "categories", "latest_time", "samples"],
        )
        writer.writeheader()
        for item in candidates:
            row = dict(item)
            row["samples"] = json.dumps(row.get("samples", []), ensure_ascii=False)
            writer.writerow({k: row.get(k, "") for k in writer.fieldnames})

    query_fields = [
        "query", "norm_query", "target_platforms", "platform_queries", "theme", "subtheme",
        "platform_scope", "priority", "evidence_count", "source_customers", "categories",
        "source_queries", "sample_queries", "reason",
    ]
    with open(queries_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=query_fields)
        writer.writeheader()
        for item in records:
            row = dict(item)
            row["norm_query"] = row.get("norm_query") or normalize_platform_specific_query(row.get("query", ""))
            row["target_platforms"] = row.get("target_platforms") or extract_platform_names_for_query(
                row.get("query", ""),
                row.get("source_customers", ""),
                row.get("platform_scope", ""),
            )
            row["platform_queries"] = row.get("platform_queries") or build_platform_queries(
                row["norm_query"],
                row["target_platforms"],
            )
            row["target_platforms"] = json.dumps(row.get("target_platforms", []), ensure_ascii=False)
            row["platform_queries"] = json.dumps(row.get("platform_queries", []), ensure_ascii=False)
            row["source_queries"] = json.dumps(row.get("source_queries", []), ensure_ascii=False)
            row["sample_queries"] = json.dumps(row.get("sample_queries", []), ensure_ascii=False)
            writer.writerow({k: row.get(k, "") for k in query_fields})

    with open(queries_jsonl, "w", encoding="utf-8") as f:
        for item in records:
            row = dict(item)
            row["norm_query"] = row.get("norm_query") or normalize_platform_specific_query(row.get("query", ""))
            row["target_platforms"] = row.get("target_platforms") or extract_platform_names_for_query(
                row.get("query", ""),
                row.get("source_customers", ""),
                row.get("platform_scope", ""),
            )
            row["platform_queries"] = row.get("platform_queries") or build_platform_queries(
                row["norm_query"],
                row["target_platforms"],
            )
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    expanded_fields = [
        "platform", "query", "norm_query", "source_query", "theme", "subtheme", "priority",
        "evidence_count", "source_customers", "categories", "reason",
    ]
    expanded_seen = set()
    with open(queries_by_platform_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=expanded_fields)
        writer.writeheader()
        for item in records:
            norm_query = item.get("norm_query") or normalize_platform_specific_query(item.get("query", ""))
            platforms = item.get("target_platforms") or extract_platform_names_for_query(
                item.get("query", ""),
                item.get("source_customers", ""),
                item.get("platform_scope", ""),
            )
            platform_queries = item.get("platform_queries") or build_platform_queries(norm_query, platforms)
            for platform_item in platform_queries:
                key = (platform_item.get("platform", ""), platform_item.get("query", ""))
                if key in expanded_seen:
                    continue
                expanded_seen.add(key)
                writer.writerow({
                    "platform": platform_item.get("platform", ""),
                    "query": platform_item.get("query", ""),
                    "norm_query": norm_query,
                    "source_query": item.get("query", ""),
                    "theme": item.get("theme", ""),
                    "subtheme": item.get("subtheme", ""),
                    "priority": item.get("priority", ""),
                    "evidence_count": item.get("evidence_count", ""),
                    "source_customers": item.get("source_customers", ""),
                    "categories": item.get("categories", ""),
                    "reason": item.get("reason", ""),
                })

    theme_counts = defaultdict(int)
    for item in records:
        theme_counts[item.get("theme") or "其它"] += 1
    with open(report_md, "w", encoding="utf-8") as f:
        f.write("# 电商平台知识覆盖率 Query 挖掘报告\n\n")
        f.write("## 运行参数\n\n")
        f.write("```json\n")
        f.write(json.dumps(metadata, ensure_ascii=False, indent=2))
        f.write("\n```\n\n")
        f.write("## 结果概览\n\n")
        f.write(f"- 规则候选数：{len(candidates)}\n")
        f.write(f"- 最终 query 数：{len(records)}\n")
        f.write("- 主题分布：\n")
        for theme, count in sorted(theme_counts.items(), key=lambda x: (-x[1], x[0])):
            f.write(f"  - {theme}: {count}\n")
        f.write("\n## Top 30 Query\n\n")
        for idx, item in enumerate(records[:30], 1):
            norm_query = item.get("norm_query") or normalize_platform_specific_query(item.get("query", ""))
            f.write(
                f"{idx}. [{item.get('priority')}] {item.get('query')}（{item.get('theme')}，证据 {item.get('evidence_count')}）\n"
            )
            if norm_query and norm_query != item.get("query"):
                f.write(f"   - template: {norm_query}\n")
            platform_queries = item.get("platform_queries") or build_platform_queries(
                norm_query,
                item.get("target_platforms") or extract_platform_names_for_query(
                    item.get("query", ""),
                    item.get("source_customers", ""),
                    item.get("platform_scope", ""),
                ),
            )
            for platform_item in platform_queries[:3]:
                f.write(f"   - {platform_item.get('platform')}: {platform_item.get('query')}\n")

    return {
        "candidates_csv": candidates_csv,
        "queries_csv": queries_csv,
        "queries_by_platform_csv": queries_by_platform_csv,
        "queries_jsonl": queries_jsonl,
        "report_md": report_md,
    }


def mine_queries(
    mysql_config_path: str,
    customers: Sequence[str],
    start_time: Optional[str],
    end_time: Optional[str],
    users: Optional[Sequence[str]] = None,
    app_ids: Optional[Sequence[str]] = None,
    raw_limit: int = 20000,
    max_candidates: int = 1000,
    max_queries: int = 500,
    batch_size: int = 50,
    sample_per_query: int = 2,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    output_dir: str = "output/ecommerce_query_mining",
    require_reply: bool = True,
    skip_llm: bool = False,
    per_theme_limit: int = 0,
) -> dict:
    """端到端挖掘电商平台覆盖率测评 query。"""
    connector = create_mysql_connector(mysql_config_path)
    candidate_stats = fetch_candidate_stats(
        connector=connector,
        customers=customers,
        start_time=start_time,
        end_time=end_time,
        users=users,
        app_ids=app_ids,
        raw_limit=raw_limit,
        require_reply=require_reply,
    )[:max_candidates]
    for offset in range(0, len(candidate_stats), 200):
        chunk = candidate_stats[offset:offset + 200]
        sample_map = fetch_samples_for_queries(
            connector=connector,
            source_queries=[item["source_query"] for item in chunk],
            customers=customers,
            start_time=start_time,
            end_time=end_time,
            users=users,
            app_ids=app_ids,
            per_query=sample_per_query,
            require_reply=require_reply,
        )
        for item in chunk:
            item["samples"] = sample_map.get(item["source_query"], [])

    batch_records = []
    for batch_idx, offset in enumerate(range(0, len(candidate_stats), batch_size), 1):
        batch = candidate_stats[offset:offset + batch_size]
        logging.info("泛化批次 %s，候选 %s-%s/%s", batch_idx, offset + 1, offset + len(batch), len(candidate_stats))
        batch_records.extend(
            llm_generalize_batch(
                batch,
                model_name=model_name,
                provider=provider,
                batch_index=batch_idx,
                skip_llm=skip_llm,
            )
        )

    records = merge_records(batch_records, max_queries=max_queries, per_theme_limit=per_theme_limit)
    metadata = {
        "customers": list(customers),
        "start_time": start_time,
        "end_time": end_time,
        "users": list(users or []),
        "app_ids": list(app_ids or []),
        "raw_limit": raw_limit,
        "max_candidates": max_candidates,
        "max_queries": max_queries,
        "batch_size": batch_size,
        "sample_per_query": sample_per_query,
        "model_name": model_name,
        "provider": provider,
        "require_reply": require_reply,
        "skip_llm": skip_llm,
        "per_theme_limit": per_theme_limit,
        "candidate_count": len(candidate_stats),
        "query_count": len(records),
    }
    files = write_outputs(output_dir, candidate_stats, records, metadata)
    return {"metadata": metadata, "files": files}


def mine_queries_from_sample(
    sample_path: str,
    max_candidates: int = 1000,
    max_queries: int = 500,
    batch_size: int = 50,
    sample_per_query: int = 2,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    output_dir: str = "output/ecommerce_query_mining",
    skip_llm: bool = False,
    per_theme_limit: int = 0,
) -> dict:
    """只基于本地随机样本挖掘 query，不访问数据库。"""
    rows = load_local_sample_rows(sample_path)
    candidate_stats = build_candidate_stats_from_rows(
        rows,
        max_candidates=max_candidates,
        sample_per_query=sample_per_query,
    )

    batch_records = []
    for batch_idx, offset in enumerate(range(0, len(candidate_stats), batch_size), 1):
        batch = candidate_stats[offset:offset + batch_size]
        logging.info("本地样本泛化批次 %s，候选 %s-%s/%s", batch_idx, offset + 1, offset + len(batch), len(candidate_stats))
        batch_records.extend(
            llm_generalize_batch(
                batch,
                model_name=model_name,
                provider=provider,
                batch_index=batch_idx,
                skip_llm=skip_llm,
            )
        )

    records = merge_records(batch_records, max_queries=max_queries, per_theme_limit=per_theme_limit)
    customer_counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        customer_counts[str(row.get("customer") or "")] += 1
    metadata = {
        "mode": "mine_sample",
        "sample_path": sample_path,
        "sample_rows": len(rows),
        "sample_customer_counts": dict(sorted(customer_counts.items())),
        "max_candidates": max_candidates,
        "max_queries": max_queries,
        "batch_size": batch_size,
        "sample_per_query": sample_per_query,
        "model_name": model_name,
        "provider": provider,
        "skip_llm": skip_llm,
        "per_theme_limit": per_theme_limit,
        "candidate_count": len(candidate_stats),
        "query_count": len(records),
    }
    files = write_outputs(output_dir, candidate_stats, records, metadata)
    return {"metadata": metadata, "files": files}


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="从 data_chat_history 随机样本挖掘电商平台知识覆盖率测评 query")
    parser.add_argument(
        "--mode",
        choices=["db_aggregate", "download_sample", "mine_sample"],
        default="db_aggregate",
        help="db_aggregate=旧SQL聚合模式；download_sample=随机下载本地样本；mine_sample=只基于本地样本挖掘",
    )
    parser.add_argument("--mysql-config-path", default="config/mysql_conn_config.json")
    parser.add_argument("--customers", default="", help="逗号分隔 customer 列表，例如 mercado,letain,wayfair")
    parser.add_argument("--users", default="")
    parser.add_argument("--app-ids", default="")
    parser.add_argument("--start-time", default="")
    parser.add_argument("--end-time", default="")
    parser.add_argument("--sample-size", type=int, default=15000)
    parser.add_argument("--sample-output-path", default="output/ecommerce_query_mining/random_sample.jsonl")
    parser.add_argument("--sample-input-path", default="")
    parser.add_argument("--random-seed", type=int, default=None)
    parser.add_argument("--per-customer-even", dest="per_customer_even", action="store_true", default=True)
    parser.add_argument("--no-per-customer-even", dest="per_customer_even", action="store_false")
    parser.add_argument("--raw-limit", type=int, default=20000)
    parser.add_argument("--max-candidates", type=int, default=1000)
    parser.add_argument("--max-queries", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--sample-per-query", type=int, default=2)
    parser.add_argument("--model-name", default="openai/gpt-4.1-mini")
    parser.add_argument("--provider", default="openrouter")
    parser.add_argument("--output-dir", default="output/ecommerce_query_mining")
    parser.add_argument("--per-theme-limit", type=int, default=0)
    parser.add_argument("--require-reply", dest="require_reply", action="store_true", default=True)
    parser.add_argument("--no-require-reply", dest="require_reply", action="store_false")
    parser.add_argument("--skip-llm", action="store_true", help="跳过 LLM，仅用规则泛化，适合连通性测试")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="[%(levelname)s] [%(asctime)s] %(message)s",
    )
    customers = _split_csv(args.customers)
    start_time = parse_time_arg(args.start_time)
    end_time = parse_time_arg(args.end_time, end_of_day=True)
    if args.mode == "download_sample":
        result = download_random_sample(
            mysql_config_path=args.mysql_config_path,
            customers=customers,
            sample_size=args.sample_size,
            sample_output_path=args.sample_output_path,
            start_time=start_time,
            end_time=end_time,
            users=_split_csv(args.users),
            app_ids=_split_csv(args.app_ids),
            require_reply=args.require_reply,
            per_customer_even=args.per_customer_even,
            random_seed=args.random_seed,
        )
    elif args.mode == "mine_sample":
        if not args.sample_input_path:
            raise ValueError("--mode mine_sample 必须提供 --sample-input-path")
        result = mine_queries_from_sample(
            sample_path=args.sample_input_path,
            max_candidates=args.max_candidates,
            max_queries=args.max_queries,
            batch_size=args.batch_size,
            sample_per_query=args.sample_per_query,
            model_name=args.model_name,
            provider=args.provider,
            output_dir=args.output_dir,
            skip_llm=args.skip_llm,
            per_theme_limit=args.per_theme_limit,
        )
    else:
        if not customers:
            raise ValueError("--mode db_aggregate 必须提供 --customers")
        result = mine_queries(
            mysql_config_path=args.mysql_config_path,
            customers=customers,
            start_time=start_time,
            end_time=end_time,
            users=_split_csv(args.users),
            app_ids=_split_csv(args.app_ids),
            raw_limit=args.raw_limit,
            max_candidates=args.max_candidates,
            max_queries=args.max_queries,
            batch_size=args.batch_size,
            sample_per_query=args.sample_per_query,
            model_name=args.model_name,
            provider=args.provider,
            output_dir=args.output_dir,
            require_reply=args.require_reply,
            skip_llm=args.skip_llm,
            per_theme_limit=args.per_theme_limit,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
