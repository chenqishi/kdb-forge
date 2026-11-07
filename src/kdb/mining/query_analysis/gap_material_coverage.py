from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
「缺口 query ↔ 已爬材料」覆盖对照。

用途：灌库**之前**先回答一个问题——爬回来的这批材料，到底能覆盖多少条缺口 query？
避免"爬了一堆、灌进去才发现答不上"的浪费。

做法：
1. 把每篇材料按段落切成块（挖掘流程也是按段抽 QA，按块比按整篇更接近真实效果）
2. 对每条 query，用 DeepSeek 从候选块里判断「这些材料能不能回答这个问题」
3. 候选块先用字面+关键词粗召回（本地、零成本），再交给 LLM 精判

判定三档，与 payoneer-olive 的口径对齐：
- covered  : 材料里有能直接回答的内容
- partial  : 沾边但不足以完整回答
- missing  : 材料里没有 → 要么公开材料真没有（渠道内部口径），要么没爬到

输出 CSV/JSONL/Markdown，missing 那部分正是「要不要继续找材料」的依据。
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = str(_PROJECT_ROOT)

DEFAULT_JUDGE_MODEL = 'deepseek-v4-pro'

_SPACE_RE = re.compile(r'\s+')
_CJK_RE = re.compile(r'[\u4e00-\u9fff]')
_WORD_RE = re.compile(r'[a-zA-Z]{3,}')


# ---------------------------------------------------------------------------
# 材料切块
# ---------------------------------------------------------------------------

def load_material_chunks(material_dir: str, chunk_chars: int = 900,
                         min_chars: int = 120) -> List[dict]:
    """把材料目录下的 .txt 切成块。

    第一行是标题，正文按句子边界累积到 chunk_chars 左右切一刀。
    """
    chunks: List[dict] = []
    for name in sorted(os.listdir(material_dir)):
        if not name.endswith('.txt'):
            continue
        path = os.path.join(material_dir, name)
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
        parts = raw.split('\n\n', 1)
        title = parts[0].strip()
        rest = parts[1] if len(parts) > 1 else ''

        # 优先按爬取阶段写入的 '## 小节标题' 边界切块。
        # 盲切字符数会把不同主题混进一块，块向量代表的是开头那段话而不是块里的答案
        # （实测：EU-partner 页回答「没通过能否补资料」的关键句被切进以营销话术开头的块，
        #  相似度 0.4451、排名 680/2492，永远召不回）。按小节切后标题即主题。
        sec_parts = re.split(r'(?m)^## (.+)$', rest)
        if len(sec_parts) > 1:
            for i in range(1, len(sec_parts) - 1, 2):
                head = sec_parts[i].strip()
                text = _SPACE_RE.sub(' ', sec_parts[i + 1]).strip()
                if len(text) < min_chars:
                    continue
                # 小节过长时仍按句子切，但每块都带上小节标题作为主题锚
                if len(text) <= chunk_chars * 2:
                    chunks.append({'source': name, 'title': f'{title} / {head}',
                                   'text': text})
                    continue
                sentences = re.split(r'(?<=[.!?。！？])\s+', text)
                buf = ''
                for sent in sentences:
                    if len(buf) + len(sent) + 1 > chunk_chars and buf:
                        chunks.append({'source': name, 'title': f'{title} / {head}',
                                       'text': buf.strip()})
                        buf = sent
                    else:
                        buf = (buf + ' ' + sent).strip()
                if len(buf) >= min_chars:
                    chunks.append({'source': name, 'title': f'{title} / {head}',
                                   'text': buf.strip()})
            continue

        # 没有小节标记的旧格式：退回按句子累积
        body = _SPACE_RE.sub(' ', rest).strip()
        if len(body) < min_chars:
            continue
        sentences = re.split(r'(?<=[.!?。！？])\s+', body)
        buf = ''
        for sent in sentences:
            if len(buf) + len(sent) + 1 > chunk_chars and buf:
                chunks.append({'source': name, 'title': title, 'text': buf.strip()})
                buf = sent
            else:
                buf = (buf + ' ' + sent).strip()
        if len(buf) >= min_chars:
            chunks.append({'source': name, 'title': title, 'text': buf.strip()})
    return chunks


# ---------------------------------------------------------------------------
# 粗召回：本地零成本，只为把候选缩小到 LLM 能吃下的量
# ---------------------------------------------------------------------------

# query 是中文、材料是英文，字面重合度很低，所以中文侧靠术语词典映射到英文关键词。
# 只放**高置信**的对应，宁可少召回也不要引入噪声。
_TERM_MAP = {
    'vat': ['vat', 'tax'], '增值税': ['vat', 'tax'], '税': ['vat', 'tax'],
    '发票': ['invoice', 'invoicing'], '形式发票': ['proforma', 'invoice'],
    '开票': ['invoice'], '税号': ['vat number', 'vat'],
    '佣金': ['commission'], '费用': ['commission', 'rates', 'costs', 'fee'],
    '结算': ['payment', 'settlement', 'payout'], '回款': ['payment', 'payout'],
    '物流': ['shipping', 'logistics', 'delivery'], '发货': ['shipping', 'ship'],
    '仓': ['warehouse', 'logistics', 'stock'], '库存': ['stock', 'inventory'],
    '退货': ['return', 'returns'], '退款': ['refund', 'return'],
    '面单': ['label', 'shipping label'], '标签': ['label'],
    '入驻': ['sell', 'selling', 'start', 'register', 'account'],
    '注册': ['register', 'account', 'sign up'], '开店': ['selling', 'account'],
    '主体': ['company', 'legal', 'entity', 'established'],
    '资料': ['requirements', 'documents'], '资质': ['requirements', 'certification'],
    '审核': ['review', 'verification', 'check'], 'kyc': ['verification', 'kyc'],
    '店铺': ['seller account', 'account', 'shop'],
    '品牌': ['brand'], '类目': ['category', 'assortment'], '品类': ['category', 'assortment'],
    '价格': ['price', 'pricing'], '促销': ['promotion'], '广告': ['advertising'],
    '评分': ['score', 'performance', 'rating'], '绩效': ['performance'],
    '客服': ['customer service', 'customer contact'], '联系': ['contact'],
    '欧盟': ['eu', 'european'], '非欧盟': ['non-eu'], '荷兰': ['dutch', 'netherlands'],
    '比利时': ['belgian', 'belgium'], '波兰': ['poland', 'polish'],
    '取消': ['cancel', 'cancellation'], '订单': ['order'],
    '报错': ['error', 'problem'], '异常': ['error', 'issue'],
}


def query_keywords(query: str) -> List[str]:
    """把中文 query 映射成英文检索关键词（含 query 里原有的英文词）。"""
    q = query.lower()
    kws: List[str] = []
    for zh, ens in _TERM_MAP.items():
        if zh in q:
            kws.extend(ens)
    kws.extend(w.lower() for w in _WORD_RE.findall(query))
    out, seen = [], set()
    for k in kws:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


_EMB = None
_CHUNK_VECS = None


def _get_embedder():
    """复用项目里的阿里 embedding（与线上检索同一套配置）。"""
    global _EMB
    if _EMB is None:
        from kdb.shared.clients.embedding_tools import AliEmbedding
        _EMB = AliEmbedding(os.path.join(PROJECT_ROOT, 'config', 'config_ali_embedding.json'))
    return _EMB


def _vec_cache_path(material_dir: str) -> str:
    """向量缓存路径。key 里含语料指纹，语料变了自动失效。"""
    import hashlib
    sig = hashlib.md5()
    for name in sorted(os.listdir(material_dir)):
        if name.endswith('.txt'):
            fp = os.path.join(material_dir, name)
            sig.update(name.encode())
            sig.update(str(os.path.getsize(fp)).encode())
    cache_dir = os.path.join(PROJECT_ROOT, 'output', 'payoneer_olive_gap', '.veccache')
    os.makedirs(cache_dir, exist_ok=True)
    base = os.path.basename(material_dir.rstrip('/'))
    return os.path.join(cache_dir, f'{base}_{sig.hexdigest()[:12]}.npy')


def build_chunk_vectors(chunks: List[dict], batch: int = 10,
                        material_dir: Optional[str] = None) -> None:
    """给所有材料块算一次向量，缓存在模块级。

    为什么必须做：query 是中文口语、材料是英文政策文本，**关键词表跨不过去**。
    实测反例：「如果一次没成功可以补资料吗？还是就pass了」的答案明确写在
    `selling-via-bol-as-an-eu-partner`（"we will not proceed this time.
    You are always welcome to try again next year."），但关键词映射出的是
    requirements/documents/pass，召回的全是 assortment-policy 页，原文块**一次都没被召回**。
    向量检索是跨语言的，能接上这类语义。

    注意：DashScope embeddings 单次请求**最多 10 条**（实测 25 条即 400），
    而 `AliEmbedding.text2embedding` 传 list 时 `len(input_text)` 取的是列表长度
    不是文本长度，所以它的 max_length 截断对 list 入参是失效的，长文本要调用方自己截。
    """
    global _CHUNK_VECS
    import numpy as np

    # 3600+ 块每轮都重算要几百次 API 调用，语料没变就直接复用缓存
    cache = _vec_cache_path(material_dir) if material_dir else None
    if cache and os.path.exists(cache):
        mat = np.load(cache)
        if mat.shape[0] == len(chunks):
            _CHUNK_VECS = mat
            logging.info('复用向量缓存 %s', cache)
            return
        logging.warning('向量缓存块数不匹配(%s vs %s)，重算', mat.shape[0], len(chunks))

    emb = _get_embedder()
    vecs = []
    for i in range(0, len(chunks), batch):
        texts = [(c['title'] + '. ' + c['text'])[:2000] for c in chunks[i:i + batch]]
        arr = np.asarray(emb.text2embedding(texts), dtype='float32')
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        vecs.append(arr)
        if (i // batch) % 20 == 0:
            logging.info('材料块向量化 %s/%s', min(i + batch, len(chunks)), len(chunks))
    mat = np.vstack(vecs)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    _CHUNK_VECS = mat / np.clip(norms, 1e-8, None)
    if cache:
        np.save(cache, _CHUNK_VECS)
        logging.info('向量缓存已写入 %s', cache)


def recall_chunks_vector(query: str, chunks: List[dict], top_k: int = 8) -> List[dict]:
    """向量粗召回（跨语言）。"""
    import numpy as np
    if _CHUNK_VECS is None:
        return []
    emb = _get_embedder()
    qv = np.asarray(emb.text2embedding(query), dtype='float32').reshape(-1)
    qv = qv / max(float(np.linalg.norm(qv)), 1e-8)
    sims = _CHUNK_VECS @ qv
    idx = np.argsort(-sims)[:top_k]
    return [chunks[i] for i in idx]


def recall_chunks_hybrid(query: str, chunks: List[dict], top_k: int = 8) -> List[dict]:
    """关键词 + 向量双路合并去重，两边各取一半，避免任一路的盲区。"""
    half = max(1, top_k // 2)
    kw = recall_chunks(query, chunks, top_k=half)
    vec = recall_chunks_vector(query, chunks, top_k=top_k)
    out, seen = [], set()
    for c in kw + vec:
        key = (c['source'], c['text'][:60])
        if key not in seen:
            seen.add(key)
            out.append(c)
        if len(out) >= top_k:
            break
    return out


def recall_chunks(query: str, chunks: List[dict], top_k: int = 8) -> List[dict]:
    """按关键词命中数粗召回候选块。"""
    kws = query_keywords(query)
    if not kws:
        return []
    scored = []
    for ch in chunks:
        hay = (ch['title'] + ' ' + ch['text']).lower()
        hits = sum(1 for k in kws if k in hay)
        if hits:
            # 标题命中加权：标题最能代表这块讲什么
            title_hits = sum(1 for k in kws if k in ch['title'].lower())
            scored.append((hits + 2 * title_hits, ch))
    scored.sort(key=lambda x: -x[0])
    return [c for _s, c in scored[:top_k]]


# ---------------------------------------------------------------------------
# LLM 判定
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = """你在评估「一批平台官方material能不能回答卖家的问题」。

给你一个卖家的原始提问（中文，口语化，来自企微群聊）和若干段平台官方材料（英文）。
请判断这些材料能否回答该提问。

判定：
- covered : 材料里有能直接回答该问题的内容
- partial : 材料沾边但不足以完整回答（只答了一部分、或只有上位概念、缺关键细节）
- missing : 材料里没有相关内容

重要判定原则：
1. 卖家问的是**操作细节**（多久、能不能、在哪里、怎么填、超了会怎样），
   材料只给出泛泛的政策介绍不算 covered，最多 partial。
2. 有些问题问的是**渠道内部口径**（如 Payoneer 的入驻名额、账号经理、扶持政策、
   申请表怎么填、审核时效），平台官网天然不会有 —— 这类判 missing，
   并把 channel_internal 置为 true。
3. 提问若是寒暄、卖家自我介绍、或群发的资料推送（不是真的在提问），
   判 verdict="invalid"。

严格只输出一个 JSON 对象：
{"verdict":"covered|partial|missing|invalid","channel_internal":true/false,"reason":"一句话理由","evidence_sources":["文件名"]}
不要输出 markdown 代码块，不要输出多余文字。"""


def _ensure_llm():
    from kdb.mining.quality.chat_qa_extract import config as llm_config
    from kdb.mining.quality.chat_qa_extract import llm_client
    llm_config.load_llm_config()
    return llm_client


def _extract_json(text: str) -> Optional[dict]:
    """从模型输出里抠 JSON（复用 wayfair 复检里验证过的括号配平思路）。"""
    if not text:
        return None
    cleaned = re.sub(r'^```(?:json)?', '', text.strip()).strip()
    cleaned = re.sub(r'```$', '', cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:  # noqa: BLE001
        pass
    start = cleaned.find('{')
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(cleaned)):
        c = cleaned[i]
        if esc:
            esc = False
            continue
        if c == '\\':
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[start:i + 1])
                except Exception:  # noqa: BLE001
                    return None
    try:
        return json.loads(cleaned[start:] + '}' * depth)
    except Exception:  # noqa: BLE001
        return None


def judge_one(query: str, topic: str, candidates: List[dict],
              model: str = DEFAULT_JUDGE_MODEL, max_retries: int = 3,
              snippet_chars: int = 700) -> dict:
    """判断候选材料能否回答该 query。"""
    llm_client = _ensure_llm()
    if not candidates:
        return {'verdict': 'missing', 'channel_internal': False,
                'reason': '关键词粗召回没有命中任何材料块', 'evidence_sources': []}

    payload = {
        'seller_question': query,
        'topic': topic,
        'materials': [{'source': c['source'], 'title': c['title'],
                       'text': c['text'][:snippet_chars]} for c in candidates],
    }
    for _ in range(max_retries):
        content, _detail = llm_client.request_llm(
            model_name=model, query=json.dumps(payload, ensure_ascii=False),
            system_message=_JUDGE_SYSTEM, temperature=0.1, max_tokens=8000)
        parsed = _extract_json(content)
        if isinstance(parsed, dict) and parsed.get('verdict'):
            v = str(parsed['verdict']).strip().lower()
            if v not in ('covered', 'partial', 'missing', 'invalid'):
                v = 'missing'
            return {
                'verdict': v,
                'channel_internal': bool(parsed.get('channel_internal')),
                'reason': (parsed.get('reason') or '').strip(),
                'evidence_sources': [str(s) for s in (parsed.get('evidence_sources') or [])][:3],
            }
    return {'verdict': 'unknown', 'channel_internal': False,
            'reason': 'LLM 判定失败', 'evidence_sources': []}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def load_gap_queries(csv_path: str, platform: Optional[str]) -> List[dict]:
    """读缺口 CSV，按「归属平台(已纠正)」过滤。"""
    rows = list(csv.DictReader(open(csv_path, encoding='utf-8-sig')))
    out = []
    seen = set()
    for r in rows:
        plat = (r.get('归属平台(已纠正)') or '').strip()
        if platform and plat != platform:
            continue
        q = (r.get('客户原话') or '').strip()
        if not q or q in seen:      # 按原话去重（已知有 3 组重复行）
            continue
        seen.add(q)
        out.append({'platform': plat, 'topic': (r.get('知识主题') or '').strip(),
                    'query': q, 'time': (r.get('时间') or '').strip()})
    return out


def main():
    ap = argparse.ArgumentParser(description='缺口 query ↔ 已爬材料 覆盖对照')
    ap.add_argument('--gap-csv', default=os.environ.get('KDB_GAP_CSV'),
                    required=not bool(os.environ.get('KDB_GAP_CSV')),
                    help='缺口CSV路径；也可通过KDB_GAP_CSV配置')
    ap.add_argument('--platform', default='Bol')
    ap.add_argument('--material-dir', default=os.path.join(PROJECT_ROOT, 'data', 'payoneer_olive', 'Bol'))
    ap.add_argument('--out-dir', default=os.path.join(PROJECT_ROOT, 'output', 'payoneer_olive_gap'))
    ap.add_argument('--model', default=DEFAULT_JUDGE_MODEL)
    ap.add_argument('--top-k', type=int, default=8)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--no-vector', action='store_true', help='只用关键词召回（会漏跨语言语义匹配）')
    ap.add_argument('--stamp', default=None)
    ap.add_argument('--log-level', default='INFO')
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(message)s')

    queries = load_gap_queries(args.gap_csv, args.platform)
    chunks = load_material_chunks(args.material_dir)
    print(f'{args.platform}: 缺口 query {len(queries)} 条，材料块 {len(chunks)} 个')
    if not args.no_vector:
        print('  正在向量化材料块（跨语言召回必需）...')
        build_chunk_vectors(chunks, material_dir=args.material_dir)
    if not queries or not chunks:
        raise SystemExit('query 或材料为空')

    def review(item: dict) -> dict:
        cands = recall_chunks_hybrid(item['query'], chunks, top_k=args.top_k)
        judged = judge_one(item['query'], item['topic'], cands, model=args.model)
        return {**item, **judged,
                'candidate_sources': [c['source'] for c in cands][:5]}

    records: List[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, rec in enumerate(pool.map(review, queries), 1):
            records.append(rec)
            if i % 10 == 0 or i == len(queries):
                print(f'  进度 {i}/{len(queries)}')

    os.makedirs(args.out_dir, exist_ok=True)
    stamp = args.stamp or 'latest'
    base = f'{args.platform.lower()}_material_coverage_{stamp}'
    jsonl_p = os.path.join(args.out_dir, base + '.jsonl')
    csv_p = os.path.join(args.out_dir, base + '.csv')
    md_p = os.path.join(args.out_dir, base + '.md')

    with open(jsonl_p, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    with open(csv_p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['verdict', 'channel_internal', 'topic', 'query',
                                          'reason', 'evidence_sources'],
                           extrasaction='ignore')
        w.writeheader()
        for r in records:
            w.writerow({**r, 'evidence_sources': ','.join(r.get('evidence_sources') or [])})

    counts = Counter(r['verdict'] for r in records)
    chan = sum(1 for r in records if r.get('channel_internal'))
    answerable = [r for r in records if r['verdict'] != 'invalid'
                  and not r.get('channel_internal')]
    got = sum(1 for r in answerable if r['verdict'] in ('covered', 'partial'))
    rate = (100.0 * got / len(answerable)) if answerable else 0.0

    # 口径必须写进报告：只报覆盖率不报 top_k，下一个人复现会对不上
    # （payoneer-olive 就吃过这个亏：报告只写"平均召回 77 条"，
    #  读起来像 judge 看了 77 条，实际 KEEP_DETAIL=12 只送了 12 条）
    lines = [f'# {args.platform} 缺口 ↔ 已爬材料 覆盖对照（{stamp}）', '',
             f'- 缺口 query：{len(queries)} 条（按原话去重后）',
             f'- 材料：{args.material_dir}，{len(chunks)} 个块',
             f'- 判定模型：{args.model}',
             f'- **候选数 top_k={args.top_k}**（关键词+向量双路合并后送判定的块数）',
             f'- 召回方式：{"关键词" if args.no_vector else "关键词 + 向量双路"}',
             f'- 切块方式：优先按材料里的 `## 小节` 边界，无标记时按句子累积', '',
             '## 判定分布', '', '| 判定 | 条数 |', '|---|---:|']
    for v in ('covered', 'partial', 'missing', 'invalid', 'unknown'):
        if counts.get(v):
            lines.append(f'| {v} | {counts[v]} |')
    lines += ['', f'- 判为**渠道内部口径**（公开材料天然没有）：{chan} 条',
              f'- **可由公开材料回答的分母**：{len(answerable)} 条'
              f'（剔除 invalid 与渠道内部）',
              f'- 其中已被本批材料覆盖(covered+partial)：{got} 条 → **{rate:.0f}%**', '']

    for v, title in (('missing', '材料未覆盖（需继续找材料或确属渠道内部）'),
                     ('partial', '部分覆盖（材料沾边但不够细）'),
                     ('covered', '已覆盖')):
        sub = [r for r in records if r['verdict'] == v]
        if not sub:
            continue
        lines += ['', f'## {title}（{len(sub)}）', '',
                  '| 主题 | query | 渠道内部 | 说明 |', '|---|---|---|---|']
        for r in sub:
            esc = lambda s: str(s or '').replace('|', '\\|').replace('\n', ' ')[:110]
            lines.append(f'| {esc(r["topic"])} | {esc(r["query"])} | '
                         f'{"是" if r.get("channel_internal") else ""} | {esc(r["reason"])} |')

    with open(md_p, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print('判定分布:', dict(counts), '| 渠道内部:', chan)
    print(f'可公开回答分母 {len(answerable)}，已覆盖 {got} → {rate:.0f}%')
    for p in (jsonl_p, csv_p, md_p):
        print(p)


if __name__ == '__main__':
    main()
