from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
把 payoneer-olive 的缺口 query 清单与本地「未答 query 复检」结果做对齐。

用途：两套**完全独立**的方法指向同一个知识库——
- payoneer-olive：从抽样 query 入手（865 条时间加权抽样 → 线上检索 → judge → 判缺口）
- 本仓库：从未答对话入手（`data_chat_history` 里被兜底话术回复的 query → 多路改写 → 检索 → 判定）

两边样本可能有重叠但没有共同 id，所以按 query 文本做字面 + 语义匹配，
把命中的 `key`（对方的稳定标识 `pp:NNN`）回给对方，它就能定位到同一条的完整判定链。

**只做对齐，不做数值对比**：两边分母口径不同（我方是"被兜底话术回复的去重 query"，
对方是"865 条抽样里的 A 类"），比数值没有意义；能比的是**结论方向**。
另外对方已声明其 348 条本身带约 43% 的闸门误杀偏差，
所以**匹配不上不代表对方没有该 query**，可能只是被它上游的闸门筛掉了。
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

PROJECT_ROOT = str(_PROJECT_ROOT)

DEFAULT_GAP_CSV = os.environ.get('KDB_GAP_CSV')

_PUNCT_RE = re.compile(r'[\s，。！？!?、,.；;：:（）()【】\[\]「」“”"\'`~\-_/\\|]+')


def normalize(text: str) -> str:
    """归一化：去标点空白、统一大小写。用于字面匹配。"""
    return _PUNCT_RE.sub('', (text or '').lower())


def char_dice(a: str, b: str) -> float:
    """字符级 Dice 相似度（中文短文本上比编辑距离稳）。"""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return 2 * len(sa & sb) / (len(sa) + len(sb))


def load_peer_gaps(path: str, platform: Optional[str] = None) -> List[dict]:
    rows = []
    for r in csv.DictReader(open(path, encoding='utf-8-sig')):
        if platform and (r.get('平台(已纠正)') or '').strip() != platform:
            continue
        q = (r.get('query原文') or '').strip()
        if not q:
            continue
        rows.append({'key': (r.get('key') or '').strip(),
                     'platform': (r.get('平台(已纠正)') or '').strip(),
                     'category': (r.get('类别P/T') or '').strip(),
                     'topic': (r.get('知识主题') or '').strip(),
                     'query': q, 'norm': normalize(q)})
    return rows


def load_local_reviews(path: str) -> List[dict]:
    out = []
    for line in open(path, encoding='utf-8'):
        if not line.strip():
            continue
        r = json.loads(line)
        q = (r.get('query') or '').strip()
        if not q:
            continue
        out.append({'query': q, 'norm': normalize(q), 'verdict': r.get('verdict'),
                    'top_score': r.get('top_score'), 'top_title': r.get('top_title'),
                    'count': r.get('count')})
    return out


def align(peer: List[dict], local: List[dict],
          dice_threshold: float = 0.75) -> Tuple[List[dict], Dict[str, int]]:
    """字面优先、语义（字符 Dice）兜底的匹配。

    先做归一化全等（最可信），再对剩余的做 Dice 匹配并取最高分。
    阈值 0.75 偏保守：宁可少匹配也不要错配，因为错配会让两边的判定张冠李戴。
    """
    by_norm: Dict[str, dict] = {}
    for l in local:
        by_norm.setdefault(l['norm'], l)

    matched, stats = [], {'exact': 0, 'fuzzy': 0, 'none': 0}
    for p in peer:
        hit = by_norm.get(p['norm'])
        how = 'exact'
        if hit is None:
            best, best_s = None, 0.0
            for l in local:
                s = char_dice(p['norm'], l['norm'])
                if s > best_s:
                    best, best_s = l, s
            hit = best if best_s >= dice_threshold else None
            how = 'fuzzy' if hit else 'none'
        stats[how if hit else 'none'] += 1
        matched.append({**p, 'match_type': how if hit else 'none',
                        'local_query': hit['query'] if hit else '',
                        'local_verdict': hit['verdict'] if hit else '',
                        'local_top_score': hit['top_score'] if hit else '',
                        'local_top_title': hit['top_title'] if hit else ''})
    return matched, stats


def main():
    ap = argparse.ArgumentParser(description='缺口 query ↔ 本地未答复检 对齐')
    ap.add_argument('--gap-csv', default=DEFAULT_GAP_CSV, required=not bool(DEFAULT_GAP_CSV),
                    help='缺口CSV路径；也可通过KDB_GAP_CSV配置')
    ap.add_argument('--local-jsonl', required=True,
                    help='本地复检产物 review_*.jsonl')
    ap.add_argument('--platform', default=None, help='只对齐某个平台')
    ap.add_argument('--dice-threshold', type=float, default=0.75)
    ap.add_argument('--out', default=None)
    ap.add_argument('--log-level', default='INFO')
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(message)s')

    peer = load_peer_gaps(args.gap_csv, args.platform)
    local = load_local_reviews(args.local_jsonl)
    print(f'对方缺口 {len(peer)} 条 / 本地复检 {len(local)} 条')
    if not peer or not local:
        raise SystemExit('任一侧为空，无法对齐')

    matched, stats = align(peer, local, dice_threshold=args.dice_threshold)
    hit = [m for m in matched if m['match_type'] != 'none']
    print(f"匹配：精确 {stats['exact']} / 模糊 {stats['fuzzy']} / 未命中 {stats['none']}"
          f"  → 命中率 {100 * len(hit) / len(peer):.0f}%")

    if hit:
        import collections
        print('命中条目的本地判定分布:',
              dict(collections.Counter(m['local_verdict'] for m in hit)))

    out = args.out or os.path.join(PROJECT_ROOT, 'output', 'payoneer_olive_gap',
                                   'cross_align.csv')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fields = ['key', 'platform', 'category', 'topic', 'query', 'match_type',
              'local_query', 'local_verdict', 'local_top_score', 'local_top_title']
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(matched)
    print('输出:', out)
    print('\n注意：匹配不上**不代表对方没有该 query** —— 对方已声明其 348 条'
          '带约 43% 的上游闸门误杀偏差；且两边分母口径不同，**不要比数值，只比结论方向**。')


if __name__ == '__main__':
    main()
