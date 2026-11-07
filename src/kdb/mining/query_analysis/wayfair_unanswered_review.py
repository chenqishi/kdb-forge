from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
Wayfair「答不上来」的 query 复检流程。

背景：线上 Wayfair 机器人对答不上来的问题会回一句固定兜底话术
（「抱歉，目前我无法回答这个问题，建议您优先咨询账号经理或者是 desk 团队…」）。
这些 query 未必真的是知识缺失，也可能是**检索没召回**或**线上精排全否**
（MEMORY 记录近期 rerank 有 34% 的请求 kept=0）。本流程把两者区分开。

四步：
  1. fetch   : 从 data_chat_history 捞出被兜底话术回复的对话，抽 query 去重
  2. rewrite : DeepSeek 对每条 query 做多次转换/补全，产出多路检索式
  3. search  : 用线上同款 SearchDataInterface 多路检索 wayfair 知识库并合并
  4. judge   : DeepSeek 判断检索到的知识能否回答该 query → covered/partial/missing

产出 CSV + JSONL + Markdown 报告，missing/partial 即真正需要补的知识缺口。

用法：
  # 全流程（默认近 30 天）
  python query_understanding_analysis/wayfair_unanswered_review.py --mode all

  # 分步（fetch 结果落盘后可离线反复跑 review，不用反复读库）
  python query_understanding_analysis/wayfair_unanswered_review.py --mode fetch
  python query_understanding_analysis/wayfair_unanswered_review.py --mode review

注意：需用装了 elasticsearch==7.10 的解释器，见 config/python_env.sh。
"""

import argparse
import copy
import csv
import json
import logging
import os
import re
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = str(_PROJECT_ROOT)

from kdb.shared.clients.mysql_connector import MySQLConnector

DEFAULT_MYSQL_CONFIG = os.path.join(PROJECT_ROOT, 'config', 'mysql_conn_config.json')
DEFAULT_SEARCH_CONFIG = os.path.join(PROJECT_ROOT, 'config', 'config_for_search_index.json')
DEFAULT_FALLBACK_CONFIG = os.path.join(PROJECT_ROOT, 'config', 'wayfair_fallback_patterns.json')
DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output', 'wayfair_unanswered')

DEFAULT_REWRITE_MODEL = 'deepseek-v4-flash'
DEFAULT_JUDGE_MODEL = 'deepseek-v4-pro'

# 线上主流检索口径：纯 QA + 已审核。见 MEMORY 2026-08-20 条。
DEFAULT_CONDITION_DICTS = [{'audit_result': [1, 2], 'data_type': ['qa']}]

_SPACE_RE = re.compile(r'\s+')

# 群聊 @机器人 的消息格式噪声。实测近 30 天 243 条 query 里 231 条(95%)含 @提及，
# 31 条是「真实问题」+ ` - - - - - @Wayfair AI助理(运营指导)(🤖)` 的引用格式。
# 不清掉的话，@名字会污染检索词并白烧 LLM token。
_QUOTE_TAIL_RE = re.compile(r'(?:\s*-\s*){3,}.*$')          # 尾部 - - - - 分隔线及其后内容
_AT_MENTION_RE = re.compile(
    r'@[^\s@，,。:：]{1,40}(?:\([^)]{0,40}\))*(?:（[^）]{0,40}）)*')  # @昵称(角色)(🤖)
_WRAP_QUOTE_RE = re.compile(r'^[「“"\'](.*)[」”"\']$', re.S)
# 只剩前引号没有后引号的情况：@提及原本在收尾引号之前，剥掉后收尾引号也跟着没了
_DANGLING_QUOTE_RE = re.compile(r'^[「“](.*)$', re.S)
_CJK_RE = re.compile(r'[\u4e00-\u9fff]')
_PUNCT_STRIP_RE = re.compile(r'[\s，。！？!?、,.；;：:（）()【】\[\]「」“”"\'`~\-_/\\|]+')


def clean_query_text(text: str) -> str:
    """剥掉群聊 @机器人 的格式噪声，取出真正的问题文本。

    处理顺序有讲究：先砍尾部分隔线（后面挂的是被 @ 的机器人名），
    再剥 @提及，最后脱「」引号——反过来会把引号里的正文一起砍掉。
    """
    if not text:
        return ''
    # 砍尾部分隔线之前先看一眼：尾巴里剥掉 @提及后如果还剩实质内容，
    # 说明那不是单纯的"被@的机器人名"，而是真问题被排在了分隔线之后。
    # 实测 259 条里 29 条尾巴含中文，其中 28 条是机器人把问题复述了一遍（丢掉无损），
    # 但有 1 条（`这个开t咨询，选什么路径`）是**与前半段不同的另一个问题**，砍掉就丢了。
    head = _QUOTE_TAIL_RE.sub('', text)
    tail = text[len(head):] if len(head) < len(text) else ''
    tail_rest = _SPACE_RE.sub(' ', re.sub(r'[-\s]+', ' ', _AT_MENTION_RE.sub(' ', tail))).strip()
    if tail_rest and len(_CJK_RE.findall(tail_rest)) >= 8:
        head_norm = _PUNCT_STRIP_RE.sub('', head)
        tail_norm = _PUNCT_STRIP_RE.sub('', tail_rest)
        # 尾巴是前半段的复述（互为子串或高度重合）→ 丢掉无损；否则拼回来
        overlap = tail_norm and head_norm and (
            tail_norm in head_norm or head_norm in tail_norm
            or len(set(tail_norm) & set(head_norm)) / max(len(set(tail_norm)), 1) > 0.8)
        if not overlap:
            head = f'{head} {tail_rest}'.strip()
    cleaned = head
    cleaned = _AT_MENTION_RE.sub(' ', cleaned)
    cleaned = _SPACE_RE.sub(' ', cleaned).strip()
    match = _WRAP_QUOTE_RE.match(cleaned)
    if match:
        cleaned = match.group(1).strip()
    else:
        # 剥 @ 之后收尾引号可能已丢失，只脱开头的孤立引号，且引号内不能再有引号
        dangling = _DANGLING_QUOTE_RE.match(cleaned)
        if dangling and '「' not in dangling.group(1) and '」' not in dangling.group(1):
            cleaned = dangling.group(1).strip()
    # 收尾残留的孤立标点/分隔符
    cleaned = cleaned.strip(' -—、,，。:：;；')
    return _SPACE_RE.sub(' ', cleaned).strip()


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

def load_fallback_config(path: str = DEFAULT_FALLBACK_CONFIG,
                        platform: Optional[str] = None) -> Dict[str, Any]:
    """读取兜底话术与客户/索引配置。

    支持两种文件格式：
    - 单平台（旧）：顶层直接是 `fallback_patterns/customers/index_names`
    - 多平台（新）：`{"platforms": {"<名字>": {...}, ...}}`，用 platform 选一个

    **各平台的兜底话术完全不同**（wayfair 是"目前我无法回答这个问题"、
    mercado_local 是"超出了我目前的知识库覆盖范围"），所以不能共用一份 pattern；
    加新平台前必须先跑一次高频短回复统计确认真实话术，不要凭猜写。
    """
    with open(path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    if 'platforms' in cfg:
        platforms = cfg['platforms']
        if not platform:
            raise ValueError(f'{path} 是多平台配置，必须用 --platform 指定其中之一：'
                             f'{sorted(platforms.keys())}')
        if platform not in platforms:
            raise ValueError(f'{path} 里没有平台 {platform!r}，可选：{sorted(platforms.keys())}')
        cfg = dict(platforms[platform])
        cfg.setdefault('platform', platform)

    patterns = [p for p in (cfg.get('fallback_patterns') or []) if p and p.strip()]
    if not patterns:
        raise ValueError(f'{path} 里 fallback_patterns 为空，无法识别未答对话')
    cfg['fallback_patterns'] = patterns
    cfg.setdefault('customers', ['wayfair'])
    cfg.setdefault('index_names', 'wayfair')
    cfg.setdefault('platform', 'wayfair')
    return cfg


def list_platforms(path: str) -> List[str]:
    """列出多平台配置里的平台名。"""
    with open(path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    return sorted((cfg.get('platforms') or {}).keys())


# ---------------------------------------------------------------------------
# 1. 捞未答对话
# ---------------------------------------------------------------------------

def fetch_unanswered_chats(
    mysql_config_path: str,
    customers: Sequence[str],
    fallback_patterns: Sequence[str],
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[dict]:
    """从 data_chat_history 捞被兜底话术回复的对话（只读）。

    兜底话术是短特征串，用 LIKE 而不是 REGEXP，避免大文本字段上的慢查询。
    """
    clean_customers = [c.strip() for c in customers if c and c.strip()]
    if not clean_customers:
        raise ValueError('customers 不能为空')

    clauses = [
        f"customer IN ({','.join(['%s'] * len(clean_customers))})",
        "send_type = 'TEXT'",
        "send_content IS NOT NULL",
        "send_content != ''",
        "(channel_type IS NULL OR channel_type != 'wework_juhe')",
    ]
    params: List[Any] = list(clean_customers)

    like_parts = []
    for pattern in fallback_patterns:
        like_parts.append('reply_content LIKE %s')
        params.append(f'%{pattern}%')
    clauses.append('(' + ' OR '.join(like_parts) + ')')

    if start_time:
        clauses.append('create_time >= %s')
        params.append(start_time)
    if end_time:
        clauses.append('create_time < %s')
        params.append(end_time)

    sql = f"""
        SELECT
            id, customer, user, app_id, send_type, send_content, reply_content,
            msg_id, content_category, norm_content, regular_content,
            create_time, channel_type
        FROM data_chat_history
        WHERE {' AND '.join(clauses)}
        ORDER BY create_time DESC
    """
    if limit:
        sql += ' LIMIT %s'
        params.append(int(limit))

    connector = MySQLConnector(mysql_config_path)
    conn = connector.get_connection()
    if conn is None:
        raise RuntimeError('获取 MySQL 连接失败')
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    finally:
        connector.close_connection(conn, cursor)

    result = []
    for row in rows:
        normalized = {
            k: (v.strftime('%Y-%m-%d %H:%M:%S') if isinstance(v, datetime) else v)
            for k, v in row.items()
        }
        result.append(normalized)
    logging.info('捞到未答对话 %s 条', len(result))
    return result


def pick_query_text(row: dict) -> str:
    """取用于检索的 query 文本，并剥掉群聊 @ 噪声。

    优先 regular_content/norm_content（已做过规整），其次 send_content。
    某个字段清洗后变空（例如整条只有一个 @机器人）时继续尝试下一个字段。
    """
    for key in ('regular_content', 'norm_content', 'send_content'):
        value = (row.get(key) or '').strip()
        if not value:
            continue
        cleaned = clean_query_text(value)
        if cleaned:
            return cleaned
    return ''


def dedup_queries(rows: List[dict]) -> "OrderedDict[str, dict]":
    """按 query 文本去重，保留出现次数与样例记录。"""
    bucket: "OrderedDict[str, dict]" = OrderedDict()
    for row in rows:
        query = pick_query_text(row)
        if not query:
            continue
        item = bucket.setdefault(query, {
            'query': query,
            'count': 0,
            'first_seen': row.get('create_time'),
            'last_seen': row.get('create_time'),
            'sample_msg_ids': [],
        })
        item['count'] += 1
        create_time = row.get('create_time')
        if create_time:
            if not item['first_seen'] or create_time < item['first_seen']:
                item['first_seen'] = create_time
            if not item['last_seen'] or create_time > item['last_seen']:
                item['last_seen'] = create_time
        if len(item['sample_msg_ids']) < 3 and row.get('msg_id'):
            item['sample_msg_ids'].append(str(row['msg_id']))
    return bucket


# ---------------------------------------------------------------------------
# LLM 调用（DeepSeek 官方）
# ---------------------------------------------------------------------------

def _ensure_llm():
    """加载 chat_qa_extract 的多渠道 LLM 客户端并注入凭证。"""
    from kdb.mining.quality.chat_qa_extract import config as llm_config
    from kdb.mining.quality.chat_qa_extract import llm_client
    llm_config.load_llm_config()
    return llm_client


def _extract_json(text: str) -> Optional[Any]:
    """从模型输出里抠出 JSON。

    flash 类模型约 20% 会吐坏 JSON（漏右括号 / 尾部带解释文字），
    所以先剥 code fence，再按括号配平截取。见 MEMORY payoneer 去重那条。
    """
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?', '', cleaned).strip()
    cleaned = re.sub(r'```$', '', cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:  # noqa: BLE001
        pass

    for opener, closer in (('[', ']'), ('{', '}')):
        start = cleaned.find(opener)
        if start < 0:
            continue
        depth, in_str, escape = 0, False, False
        for idx in range(start, len(cleaned)):
            ch = cleaned[idx]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start:idx + 1])
                    except Exception:  # noqa: BLE001
                        break
        # 括号没配平：补齐右括号再试一次
        snippet = cleaned[start:]
        if depth > 0:
            try:
                return json.loads(snippet + closer * depth)
            except Exception:  # noqa: BLE001
                pass
    return None


def _request_json(llm_client, model: str, system_message: str, query: str,
                  max_retries: int = 3, temperature: float = 0.1) -> Optional[Any]:
    """请求模型并解析 JSON，坏 JSON 时重试。"""
    for attempt in range(max_retries):
        content, _detail = llm_client.request_llm(
            model_name=model,
            query=query,
            system_message=system_message,
            temperature=temperature,
            # DeepSeek 是 reasoning 模型，**思考 token 计入 max_tokens**。
            # 8000 在「10 条长群聊消息一批」的改写任务上实测会被思考吃光、正文为空
            # （日志里 `思考 token(7999) 已耗尽 max_tokens(8000)`）。给到 16000 留足余量。
            max_tokens=16000,
        )
        parsed = _extract_json(content)
        if parsed is not None:
            return parsed
        logging.warning('模型 %s 输出无法解析为 JSON（第 %s/%s 次）', model, attempt + 1, max_retries)
    return None


# ---------------------------------------------------------------------------
# 2. query 改写 / 补全
# ---------------------------------------------------------------------------

_REWRITE_SYSTEM = """你是跨境电商 Wayfair 平台的知识库检索专家。
用户给你一批来自卖家群聊的原始提问，这些提问口语化、常有指代不明、缺少平台词、错别字或缩写。
你的任务是把每条问题改写成适合在 Wayfair 知识库里检索的形式，目的是**提高召回**。

对每条问题输出：
- normalized: 补全主语和平台后的自包含问句（一句话，不要加解释）
- variants: 最多 3 条等价问法，换用同义词或平台术语（例如「回款」≈「付款周期」≈「结算」）。要与 normalized 表述不同，不要只改标点
- keywords: 该问题的核心关键词，空格分隔，2-6 个词
- skip: 如果是寒暄、闲聊、纯噪声、或完全看不出在问什么，置 true，其余置 false
- skip_reason: skip 为 true 时简述原因，否则空字符串

严格只输出 JSON 数组，每个元素形如：
{"id": 原样回传输入的 id, "normalized": "...", "variants": ["..."], "keywords": "...", "skip": false, "skip_reason": ""}
不要输出 markdown 代码块，不要输出任何解释文字。必须为每个输入 id 都返回一个元素。"""


def rewrite_queries(
    queries: Sequence[str],
    model: str = DEFAULT_REWRITE_MODEL,
    batch_size: int = 10,
    max_retries: int = 3,
) -> Dict[str, dict]:
    """用 DeepSeek 做多次转换/补全，产出多路检索式。"""
    llm_client = _ensure_llm()
    result: Dict[str, dict] = {}

    def fallback(q: str) -> dict:
        return {'normalized': q, 'variants': [], 'keywords': '', 'skip': False,
                'skip_reason': '', 'llm_ok': False}

    for start in range(0, len(queries), batch_size):
        batch = list(queries[start:start + batch_size])
        payload = [{'id': idx, 'question': q} for idx, q in enumerate(batch)]
        parsed = _request_json(
            llm_client, model, _REWRITE_SYSTEM,
            json.dumps(payload, ensure_ascii=False),
            max_retries=max_retries,
        )

        got = {}
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                try:
                    idx = int(item.get('id'))
                except (TypeError, ValueError):
                    continue
                if 0 <= idx < len(batch):
                    got[idx] = item

        for idx, q in enumerate(batch):
            item = got.get(idx)
            if not item:
                # 模型漏返：降级为原文检索，只会少改写不会误判
                result[q] = fallback(q)
                continue
            variants = [v.strip() for v in (item.get('variants') or []) if isinstance(v, str) and v.strip()]
            result[q] = {
                'normalized': (item.get('normalized') or q).strip() or q,
                'variants': variants[:3],
                'keywords': (item.get('keywords') or '').strip(),
                'skip': bool(item.get('skip')),
                'skip_reason': (item.get('skip_reason') or '').strip(),
                'llm_ok': True,
            }
        logging.info('query 改写进度 %s/%s', min(start + batch_size, len(queries)), len(queries))

    return result


def build_search_variants(query: str, rewrite: dict) -> List[str]:
    """汇总一条 query 的所有检索式（原文 + 补全 + 变体 + 关键词），去重保序。"""
    candidates = [query, rewrite.get('normalized') or '']
    candidates.extend(rewrite.get('variants') or [])
    if rewrite.get('keywords'):
        candidates.append(rewrite['keywords'])
    seen, ordered = set(), []
    for c in candidates:
        c = (c or '').strip()
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


# ---------------------------------------------------------------------------
# 3. 检索知识库
# ---------------------------------------------------------------------------

def build_search_interface(search_config_path: str = DEFAULT_SEARCH_CONFIG):
    """初始化线上同款检索接口。"""
    from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
    return SearchDataInterface(config_path=search_config_path)


def search_knowledge(
    sdi,
    query_variants: Sequence[str],
    index_names: str = 'wayfair',
    condition_dicts: Optional[List[dict]] = None,
    top_k: int = 5,
) -> List[dict]:
    """多路检索并按 _id 合并去重，保留各路最高分。"""
    if condition_dicts is None:
        condition_dicts = DEFAULT_CONDITION_DICTS
    # search_data_by_query 会就地给条件补 audit_result（:741），传共享常量进去等于
    # 跨线程改同一个 dict。这里深拷贝一份，隔离调用方的对象。
    condition_dicts = copy.deepcopy(condition_dicts)
    merged: Dict[str, dict] = {}
    for variant in query_variants:
        try:
            docs, _total = sdi.search_data_by_query(
                variant, index_names=index_names,
                condition_dicts=condition_dicts, size=top_k)
        except Exception as exc:  # noqa: BLE001
            logging.warning('检索失败 query=%r err=%s', variant, exc)
            continue
        for doc in docs or []:
            doc_id = str(doc.get('_id') or doc.get('title'))
            score = float(doc.get('similarity') or 0.0)
            existing = merged.get(doc_id)
            if existing is None:
                merged[doc_id] = {
                    '_id': doc_id,
                    'title': doc.get('title') or '',
                    'content': doc.get('content') or '',
                    'similarity': score,
                    'hit_by': [variant],
                }
            else:
                existing['similarity'] = max(existing['similarity'], score)
                if variant not in existing['hit_by']:
                    existing['hit_by'].append(variant)
    return sorted(merged.values(), key=lambda d: d['similarity'], reverse=True)


# ---------------------------------------------------------------------------
# 4. LLM 判定覆盖情况
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = """你是 Wayfair 跨境电商知识库的质量审核员。
线上机器人对某个卖家问题回答不上来，我们已经用多种改写去知识库检索，把候选知识给你。
请判断：**现有知识库里的这些知识，是否足以回答这个问题**。

判定三档：
- covered : 候选知识里有能直接、完整回答该问题的内容。说明知识本身不缺，是线上检索或精排的问题
- partial : 有相关知识但不足以完整回答（只答了一部分、或只有上位概念、缺关键细节数据）
- missing : 候选知识与该问题无关，或完全没有涉及，属于真正的知识缺口

判定要求：
1. 以「卖家看到这些知识能不能解决他的问题」为准，不要因为词面相似就判 covered
2. 标题像但讲的是另一件事，判 missing
3. 问题本身无意义、闲聊、信息不足以判断在问什么，判 verdict="invalid"
4. evidence_ids 只填真正支撑你结论的知识 id，最多 3 个；missing 时留空数组

严格只输出一个 JSON 对象：
{"verdict": "covered|partial|missing|invalid", "reason": "一句话理由", "evidence_ids": ["..."], "suggested_knowledge": "missing/partial 时写一句应补充什么知识，否则空字符串"}
不要输出 markdown 代码块，不要输出任何额外文字。"""


def judge_coverage(
    query: str,
    normalized_query: str,
    candidates: List[dict],
    model: str = DEFAULT_JUDGE_MODEL,
    max_retries: int = 3,
    max_candidates: int = 8,
    content_limit: int = 500,
) -> dict:
    """让 DeepSeek 判断知识库是否真的答不了这条 query。"""
    llm_client = _ensure_llm()

    if not candidates:
        return {'verdict': 'missing', 'reason': '多路检索均无候选知识',
                'evidence_ids': [], 'suggested_knowledge': '', 'llm_ok': True}

    listed = []
    for doc in candidates[:max_candidates]:
        listed.append({
            'id': doc['_id'],
            'title': doc['title'],
            'content': (doc['content'] or '')[:content_limit],
            'similarity': round(doc['similarity'], 4),
        })
    user_payload = {
        'question': query,
        'normalized_question': normalized_query,
        'candidate_knowledge': listed,
    }
    parsed = _request_json(
        llm_client, model, _JUDGE_SYSTEM,
        json.dumps(user_payload, ensure_ascii=False),
        max_retries=max_retries,
    )
    if not isinstance(parsed, dict) or not parsed.get('verdict'):
        return {'verdict': 'unknown', 'reason': 'LLM 判定失败',
                'evidence_ids': [], 'suggested_knowledge': '', 'llm_ok': False}

    verdict = str(parsed.get('verdict', '')).strip().lower()
    if verdict not in ('covered', 'partial', 'missing', 'invalid'):
        verdict = 'unknown'
    evidence = [str(e) for e in (parsed.get('evidence_ids') or []) if e][:3]
    return {
        'verdict': verdict,
        'reason': (parsed.get('reason') or '').strip(),
        'evidence_ids': evidence,
        'suggested_knowledge': (parsed.get('suggested_knowledge') or '').strip(),
        'llm_ok': True,
    }


# ---------------------------------------------------------------------------
# 产出
# ---------------------------------------------------------------------------

def write_outputs(records: List[dict], output_dir: str, stamp: str,
                  meta: Dict[str, Any]) -> Dict[str, str]:
    """写 JSONL / CSV / Markdown 报告。"""
    os.makedirs(output_dir, exist_ok=True)
    jsonl_path = os.path.join(output_dir, f'review_{stamp}.jsonl')
    csv_path = os.path.join(output_dir, f'review_{stamp}.csv')
    md_path = os.path.join(output_dir, f'report_{stamp}.md')

    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    fields = ['verdict', 'query', 'count', 'normalized', 'top_score', 'top_title',
              'reason', 'suggested_knowledge', 'last_seen']
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for rec in records:
            writer.writerow({
                'verdict': rec['verdict'],
                'query': rec['query'],
                'count': rec['count'],
                'normalized': rec.get('normalized', ''),
                'top_score': round(rec.get('top_score') or 0.0, 4),
                'top_title': rec.get('top_title', ''),
                'reason': rec.get('reason', ''),
                'suggested_knowledge': rec.get('suggested_knowledge', ''),
                'last_seen': rec.get('last_seen', ''),
            })

    counts = Counter(r['verdict'] for r in records)
    total_hits = sum(r['count'] for r in records)
    lines = [
        f'# Wayfair 未答 query 复检报告 {stamp}',
        '',
        f'- 时间范围：{meta.get("start_time") or "不限"} ~ {meta.get("end_time") or "不限"}',
        f'- 命中兜底话术的对话：{meta.get("raw_rows", 0)} 条',
        f'- 去重后 query：{len(records)} 条（累计出现 {total_hits} 次）',
        f'- 改写模型：{meta.get("rewrite_model")}；判定模型：{meta.get("judge_model")}',
        f'- 检索索引：{meta.get("index_names")}；口径：{json.dumps(meta.get("condition_dicts"), ensure_ascii=False)}',
        '',
        '## 判定分布',
        '',
        '| 判定 | query 数 | 出现次数 | 说明 |',
        '|------|---------|---------|------|',
    ]
    desc = {
        'covered': '库里有知识能答 → 检索/精排问题，非知识缺失',
        'partial': '有相关知识但不完整 → 需补细节',
        'missing': '真知识缺口 → 需补录',
        'invalid': '无效问题（闲聊/信息不足）',
        'unknown': 'LLM 判定失败，需人工复核',
    }
    for verdict in ('missing', 'partial', 'covered', 'invalid', 'unknown'):
        if counts.get(verdict):
            hits = sum(r['count'] for r in records if r['verdict'] == verdict)
            lines.append(f'| {verdict} | {counts[verdict]} | {hits} | {desc[verdict]} |')

    for verdict, title in (('missing', '真知识缺口（missing）'),
                           ('partial', '知识不完整（partial）'),
                           ('covered', '知识已存在但线上没答上（covered）')):
        subset = [r for r in records if r['verdict'] == verdict]
        if not subset:
            continue
        subset.sort(key=lambda r: r['count'], reverse=True)
        lines += ['', f'## {title}', '',
                  '| 次数 | query | 补全后 | top1 分 | 说明 |',
                  '|------|-------|--------|---------|------|']
        for rec in subset[:100]:
            def esc(text):
                return str(text or '').replace('|', '\\|').replace('\n', ' ')[:120]
            note = rec.get('suggested_knowledge') or rec.get('reason') or ''
            lines.append(
                f'| {rec["count"]} | {esc(rec["query"])} | {esc(rec.get("normalized"))} | '
                f'{round(rec.get("top_score") or 0.0, 3)} | {esc(note)} |')
        if len(subset) > 100:
            lines.append(f'| ... | 其余 {len(subset) - 100} 条见 CSV | | | |')

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    return {'jsonl': jsonl_path, 'csv': csv_path, 'markdown': md_path}


# ---------------------------------------------------------------------------
# 流程编排
# ---------------------------------------------------------------------------

def run_fetch(args, cfg) -> str:
    rows = fetch_unanswered_chats(
        mysql_config_path=args.mysql_config,
        customers=cfg['customers'],
        fallback_patterns=cfg['fallback_patterns'],
        start_time=args.start_time,
        end_time=args.end_time,
        limit=args.limit,
    )
    os.makedirs(args.output_dir, exist_ok=True)
    path = args.raw_path or os.path.join(args.output_dir, 'unanswered_raw.jsonl')
    with open(path, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(f'未答对话 {len(rows)} 条 → {path}')
    return path


def run_review(args, cfg) -> None:
    path = args.raw_path or os.path.join(args.output_dir, 'unanswered_raw.jsonl')
    if not os.path.exists(path):
        raise SystemExit(f'未找到 {path}，请先跑 --mode fetch')
    rows = [json.loads(line) for line in open(path, encoding='utf-8') if line.strip()]
    bucket = dedup_queries(rows)
    queries = list(bucket.keys())
    if args.max_queries:
        queries = queries[:args.max_queries]
    print(f'待复检 query {len(queries)} 条（原始对话 {len(rows)} 条）')
    if not queries:
        return

    rewrites = rewrite_queries(queries, model=args.rewrite_model,
                               batch_size=args.batch_size)
    sdi = build_search_interface(args.search_config)

    def review_one(query: str) -> dict:
        """单条 query 的检索 + 判定。纯 I/O，可并发。"""
        info = bucket[query]
        rw = rewrites.get(query) or {'normalized': query, 'variants': [], 'keywords': ''}
        base = {
            'query': query, 'count': info['count'],
            'normalized': rw.get('normalized', query),
            'variants': rw.get('variants', []),
            'first_seen': info['first_seen'], 'last_seen': info['last_seen'],
            'sample_msg_ids': info['sample_msg_ids'],
        }
        if rw.get('skip'):
            base.update({
                'verdict': 'invalid',
                'reason': rw.get('skip_reason') or '改写阶段判为无效问题',
                'evidence_ids': [], 'suggested_knowledge': '',
                'top_score': 0.0, 'top_title': '', 'candidates': [],
            })
            return base

        variants = build_search_variants(query, rw)
        candidates = search_knowledge(
            sdi, variants, index_names=cfg['index_names'],
            condition_dicts=DEFAULT_CONDITION_DICTS, top_k=args.top_k)
        judged = judge_coverage(query, rw.get('normalized', query), candidates,
                                model=args.judge_model)
        base.update({
            'verdict': judged['verdict'],
            'reason': judged['reason'],
            'evidence_ids': judged['evidence_ids'],
            'suggested_knowledge': judged['suggested_knowledge'],
            'top_score': candidates[0]['similarity'] if candidates else 0.0,
            'top_title': candidates[0]['title'] if candidates else '',
            'candidates': [{k: c[k] for k in ('_id', 'title', 'similarity')}
                           for c in candidates[:5]],
        })
        return base

    # 检索 + 判定都是纯 I/O（ES 往返 + DeepSeek reasoning 单条约 10s），
    # 串行跑 243 条要 40 分钟以上，用线程池并发。并发数别开太大：
    # 阿里云 ES 在并发 4 附近就到吞吐天花板（见 MEMORY 2026-08-20 压测）。
    records: List[dict] = []
    if args.workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for idx, rec in enumerate(pool.map(review_one, queries), 1):
                records.append(rec)
                if idx % 10 == 0 or idx == len(queries):
                    print(f'  复检进度 {idx}/{len(queries)}')
    else:
        for idx, query in enumerate(queries, 1):
            records.append(review_one(query))
            if idx % 10 == 0 or idx == len(queries):
                print(f'  复检进度 {idx}/{len(queries)}')

    stamp = args.stamp or datetime.now().strftime('%Y%m%d_%H%M%S')
    paths = write_outputs(records, args.output_dir, stamp, {
        'start_time': args.start_time, 'end_time': args.end_time,
        'raw_rows': len(rows), 'rewrite_model': args.rewrite_model,
        'judge_model': args.judge_model, 'index_names': cfg['index_names'],
        'condition_dicts': DEFAULT_CONDITION_DICTS,
    })
    counts = Counter(r['verdict'] for r in records)
    print('判定分布:', dict(counts))
    for key, value in paths.items():
        print(f'{key}: {value}')


def main():
    parser = argparse.ArgumentParser(description='Wayfair 未答 query 知识库复检')
    parser.add_argument('--mode', choices=['fetch', 'review', 'all'], default='all')
    parser.add_argument('--mysql-config', default=DEFAULT_MYSQL_CONFIG)
    parser.add_argument('--search-config', default=DEFAULT_SEARCH_CONFIG)
    parser.add_argument('--fallback-config', default=DEFAULT_FALLBACK_CONFIG)
    parser.add_argument('--platform', default=None,
                        help='多平台配置时指定平台名（不给则报错并列出可选）')
    parser.add_argument('--all-platforms', action='store_true',
                        help='对配置里所有平台依次跑一遍')
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR)
    parser.add_argument('--raw-path', default=None, help='未答对话 JSONL 路径')
    parser.add_argument('--start-time', default=None, help='起始时间，默认近 N 天')
    parser.add_argument('--end-time', default=None)
    parser.add_argument('--recent-days', type=int, default=30,
                        help='未显式给 start-time 时，取最近 N 天')
    parser.add_argument('--limit', type=int, default=None, help='最多捞多少条对话')
    parser.add_argument('--max-queries', type=int, default=None, help='最多复检多少条 query')
    parser.add_argument('--top-k', type=int, default=5, help='每路检索取回条数')
    parser.add_argument('--batch-size', type=int, default=10, help='改写每批 query 数')
    parser.add_argument('--workers', type=int, default=4,
                        help='检索+判定的并发线程数，1 为串行。ES 在并发 4 附近到天花板')
    parser.add_argument('--rewrite-model', default=DEFAULT_REWRITE_MODEL)
    parser.add_argument('--judge-model', default=DEFAULT_JUDGE_MODEL)
    parser.add_argument('--stamp', default=None, help='产出文件时间戳后缀')
    parser.add_argument('--log-level', default='INFO')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format='%(asctime)s %(levelname)s %(message)s')

    if not args.start_time and args.recent_days:
        args.start_time = (datetime.now() - timedelta(days=args.recent_days)
                           ).strftime('%Y-%m-%d %H:%M:%S')

    if args.all_platforms:
        names = list_platforms(args.fallback_config)
        if not names:
            raise SystemExit(f'{args.fallback_config} 不是多平台配置，无法 --all-platforms')
        print(f'将依次处理 {len(names)} 个平台: {names}')
        base_out, base_stamp = args.output_dir, args.stamp
        for name in names:
            print(f'\n{"=" * 60}\n== 平台 {name}\n{"=" * 60}')
            cfg = load_fallback_config(args.fallback_config, platform=name)
            # 每个平台独立目录，避免产出互相覆盖
            args.output_dir = os.path.join(base_out, name)
            args.stamp = base_stamp
            args.raw_path = os.path.join(args.output_dir, 'unanswered_raw.jsonl')
            try:
                if args.mode in ('fetch', 'all'):
                    run_fetch(args, cfg)
                if args.mode in ('review', 'all'):
                    run_review(args, cfg)
            except Exception as exc:  # noqa: BLE001
                # 一个平台失败不该中断其余平台
                logging.error('平台 %s 处理失败: %s', name, exc)
        return

    cfg = load_fallback_config(args.fallback_config, platform=args.platform)

    if args.mode in ('fetch', 'all'):
        run_fetch(args, cfg)
    if args.mode in ('review', 'all'):
        run_review(args, cfg)


if __name__ == '__main__':
    main()
