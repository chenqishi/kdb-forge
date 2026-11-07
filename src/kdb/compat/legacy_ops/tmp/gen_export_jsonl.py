#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json, os, openpyxl, requests

XLSX = '/root/knowledge_database_builder/data/payoneer_olive/群聊总结知识_合并版_20260905.xlsx'
OUT = '/root/knowledge_database_builder/tmp/群聊总结知识_合并版_20260905.jsonl'
CLIENT = 'payoneer_olive'
INDEX = 'payoneer_olive'
PLATFORM = 'payoneer'

tree_resp = requests.get('https://admin.marsmind.cc/api/rufit-ai/intranet/knowledge/qaCategory/tree?client=%s' % CLIENT, timeout=30).json()
tree = tree_resp.get('data', [])

def flatten(nodes, prefix=''):
    out = []
    for n in nodes:
        name = n.get('categoryName')
        cid = n.get('categoryId')
        path = (prefix + '-' + name) if prefix else name
        out.append((path, cid))
        for c in (n.get('children') or []):
            out.extend(flatten([c], path))
    return out

flat = flatten(tree)
name_to_id = {}
for p, cid in flat:
    top = p.split('-')[0]
    name_to_id.setdefault(top, cid)
print('category names available:', sorted(name_to_id.keys()))

wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb['合并总表']
rows = list(ws.iter_rows(values_only=True))
headers = rows[0]
idx = {h: i for i, h in enumerate(headers)}
TITLE=idx['问题']; CONTENT=idx['答案']; SYN=idx['同义问题']; PLAT=idx['平台']; CAT=idx['类别']; BATCH=idx['批次']; MERGE=idx['合并条数']; RECHK=idx['回指检查']

def get_cat(platform):
    p = (str(platform).strip() if platform is not None else '')
    if not p:
        return ('1', '默认分组', 'default')
    if p in name_to_id:
        return (str(name_to_id[p]), p, 'manual')
    return ('1', '默认分组', 'default')

docs = []
matched = 0
default_cnt = 0
missing_platform = 0
recheck = 0
unmatched_names = set()
for r in rows[1:]:
    title = r[TITLE]; content = r[CONTENT]
    if title is None or content is None:
        continue
    title = str(title).strip(); content = str(content).strip()
    if not title or not content:
        continue
    syn_raw = r[SYN]
    synonyms = []
    if syn_raw is not None:
        for line in str(syn_raw).splitlines():
            line = line.strip()
            if line:
                synonyms.append(line)
    platform_val = r[PLAT]
    if platform_val is None or not str(platform_val).strip():
        missing_platform += 1
    cid, cname, csrc = get_cat(platform_val)
    if cname == '默认分组':
        default_cnt += 1
        if platform_val is not None and str(platform_val).strip():
            unmatched_names.add(str(platform_val).strip())
    else:
        matched += 1
    if r[RECHK] is not None and str(r[RECHK]).strip() == '需复核':
        recheck += 1
    doc = {
        'title': title,
        'content': content,
        'synonyms_title': synonyms,
        'data_type': 'qa',
        'platform': PLATFORM,
        'from_type': 'chat_auto',
        'from_type_norm': 'auto_learning',
        'audit_result': 1,
        'quality_level': 'high',
        'del_flag': 0,
        'client': CLIENT,
        'dataset': INDEX,
        'index_name': INDEX,
        'category_infos': [{'category_id': cid, 'category_name': cname, 'score': 1.0, 'source': csrc}],
        'task_id': '群聊总结知识_合并版_20260905',
        'ext_info': {
            'from_file_name': '群聊总结知识_合并版_20260905',
            'quality_info': ['优质'],
            'batch': str(r[BATCH]) if r[BATCH] is not None else '',
            'merge_count': str(r[MERGE]) if r[MERGE] is not None else '',
            'category_hint': str(r[CAT]) if r[CAT] is not None else '',
        }
    }
    docs.append(doc)

with open(OUT, 'w', encoding='utf-8') as f:
    for d in docs:
        f.write(json.dumps(d, ensure_ascii=False) + chr(10))

print('total docs:', len(docs))
print('matched platform category:', matched)
print('default group (fallback):', default_cnt)
print('missing platform value:', missing_platform)
print('需复核 rows:', recheck)
print('unmatched platform names (fell to default):', sorted(unmatched_names))
print('out:', OUT)
