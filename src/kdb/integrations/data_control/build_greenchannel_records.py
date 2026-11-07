#!/usr/bin/env python
# -*- coding:utf8 -*-
"""把绿通官网抓下来的板块直接转成 ES 知识记录 —— **不过 LLM**。

## 为什么不调 Dify 清洗
这些页面本身就是**结构化且写好的**：标题、要点列表、分档要求都清清楚楚。
实测对比（美客多 id=8 入驻介绍）：
    原文 1464 字  →  2025 年 Dify 改写后 663 字
改写把这些**全丢了**，而它们恰恰是卖家最常问的：
    「请使用 Gmail\\Outlook\\Hotmail 邮箱，勿用 126\\163\\QQ」
    「单品重量必须小于 400g」「件单价 25 美元以下」
    「单店过去一年年均流水 30W 美元以上」「需 R 标或 TM 标」「半托管模式」
结论：结构化页面**直接留原文**，只做去广告和轻度归一，别让 LLM 复述。

## indexes（检索索引项）也不需要 LLM 生成
板块名 + 平台名的组合就是用户的真实问法，按模板拼即可：
    「{平台}入驻要求是什么？」「{平台}回款周期多久？」…
比 LLM 编的问句更贴合，也稳定可复现。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('data_control_tools/build_greenchannel_records.py')
import argparse
import json
import logging
import os
import re
import time

LOGGER = logging.getLogger(__name__)

# 广告/引流话术，逐行剔除
AD_WORDS = ['点击右上方', '加入橄榄枝计划会员', '立即解锁', '购买会员',
            '更多资讯请', '扫码', '长按识别', '点击链接', '立即咨询']

# 同义问法模板（{p}=平台名）。写进 `synonyms_title` 字段 ——
# `search_index_data_interface.py:503` 会把它逐条追加进 indexes[] 并生成 embedding，
# 所以这些问法**直接参与向量召回**，是补检索最有效的位置。
# 注意：data_type=segment 会被 pop 掉 synonyms_title，只有 qa/doc 保留；本批是 qa。
SYNONYM_TPL = {
    '入驻介绍': ['{p}入驻要求是什么？', '{p}怎么入驻？', '{p}入驻需要什么资料？',
                 '{p}入驻门槛是什么', '{p}开店条件', '入驻{p}要多少流水？',
                 '{p}对主体有什么要求？', '如何通过派安盈橄榄枝计划入驻{p}？',
                 '{p}可以个体户入驻吗', '{p}入驻流程'],
    '平台特点': ['{p}是什么平台？', '{p}平台介绍', '{p}覆盖哪些国家和地区？',
                 '{p}怎么样', '{p}平台优势'],
    '热卖品类': ['{p}热卖品类有哪些？', '{p}适合卖什么？', '{p}主推类目',
                 '{p}什么产品好卖', '{p}优势类目'],
    '平台数据': ['{p}平台数据如何？', '{p}流量和市场规模', '{p}体量怎么样？',
                 '{p}有多少用户', '{p}市场份额'],
    '回款周期': ['{p}回款周期多久？', '{p}怎么结算？', '{p}支持哪些币种回款？',
                 '{p}什么时候放款', '{p}账期多长', '{p}提现要多久'],
}

# 关键词（keyword 类型，精确匹配用）。板块固有词 + 从正文抽的高价值实体。
SEC_KW = {
    '入驻介绍': ['入驻', '开店', '资质', '门槛', '流水', '营业执照', '申请'],
    '平台特点': ['平台介绍', '站点', '国家', '优势'],
    '热卖品类': ['品类', '类目', '选品', '热卖'],
    '平台数据': ['平台数据', '流量', '市场规模', 'GMV'],
    '回款周期': ['回款', '结算', '账期', '币种', '提现'],
}
# 正文里出现就收进 keywords 的高价值词（卖家实际会搜的）
CONTENT_KW = ['半托管', '全托管', '自发货', '海外仓', '本对本', 'VAT', '欧代',
              'R标', 'TM标', '品牌备案', '保证金', '佣金', '月租', '香港主体',
              '大陆主体', '个体户', '企业主体', 'EPR', '质检报告', '免流水']


# 平台名 → 线上类目名。绿通页面用中文名/变体，类目树用英文名，模糊匹配对不上，
# 只能显式映射。找不到类目宁可报错也不要落到默认分组（会污染所有平台的检索）。
PLATFORM_ALIAS = {
    '沃尔玛全球电商-美国站': 'Walmart',
    '沃尔玛全球电商-墨西哥站': 'Walmart',
    '沃尔玛全球电商-加拿大站': 'Walmart',
    '沃尔玛全球电商-美国站-台湾主体入驻': 'Walmart',
    '美客多 半托管/全托管模式': 'Mercado Libre',
    '美客多Mercado Libre': 'Mercado Libre',
    'Cross Commerce Store（CCS）': 'CCS(跨贸商店)',
    'Lowe‘s': 'Lowes',
    "Lowe's": 'Lowes',
}


def clean_text(text):
    """去广告行、压缩空白、去掉纯分隔线。"""
    out = []
    for line in text.split('\n'):
        s = line.strip()
        if not s:
            continue
        if re.fullmatch(r'[-—=_*·\s]{6,}', s):     # 分隔线
            continue
        if any(w in s for w in AD_WORDS):
            continue
        out.append(s)
    return '\n'.join(out).strip()


def build_records(manifest_path, category_map):
    """manifest → ES 记录列表。每个板块一条。"""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))
    from knowledge_crawler_tool.web_crawl.greenchannel_catalog_fetch import parse_detail

    man = json.load(open(manifest_path, encoding='utf-8'))
    recs = []
    for pid, meta in sorted(man.items(), key=lambda x: int(x[0])):
        platform, data = parse_detail(meta['html_file'])
        platform = platform or meta.get('platform') or meta.get('catalog_name')
        for sec_name, sec in data.items():
            content = clean_text(sec['text_content'])
            if len(content) < 20:
                continue
            title = '%s%s' % (platform, sec_name)
            syns = [t.format(p=platform) for t in SYNONYM_TPL.get(sec_name, [])]
            kws = [platform] + SEC_KW.get(sec_name, []) + \
                  [w for w in CONTENT_KW if w in content]
            cid, cname = category_map.get(platform, ('', ''))
            recs.append({
                'title': title,
                'content': content,
                'platform': 'payoneer',
                'from_type': 'html',
                'from_type_norm': 'html',
                'data_type': 'qa',
                'dataset': 'payoneer_olive',
                'quality_level': 'high',
                'synonyms_title': syns,
                'keywords': sorted(set(kws)),
                'tags': [sec_name, '入驻', '平台', '绿通'],
                'ext_info': {'ecommerce_platform': platform,
                             'platform_id': pid,
                             'from_file_name': meta['html_file'],
                             'source_url': 'https://greenchannel.payoneer.com.cn/GCPortal/PlatformDetail?PlatformId=%s' % pid},
                '_category_id': cid, '_category_name': cname,
            })
    return recs


def main():
    ap = argparse.ArgumentParser(description='绿通板块 → ES 记录（不过 LLM）')
    ap.add_argument('--manifest', default='data/payoneer/greenchannel_20260901/manifest.json')
    ap.add_argument('--out', default='data/payoneer/greenchannel_20260901/records.json')
    ap.add_argument('--client', default='payoneer_olive')
    ap.add_argument('--log-level', default='INFO')
    args = ap.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(message)s')

    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))
    from data_control_tools.build_doc_mining_tasks import load_category_map
    cm = load_category_map(args.client)
    # 平台名 → (category_id, category_name)：先精确、再去空格/大小写模糊
    norm = {k.lower().replace(' ', ''): (v, k) for k, v in cm.items()}
    cat = {}

    recs = build_records(args.manifest, {})
    hit = miss = 0
    for r in recs:
        p = r['ext_info']['ecommerce_platform']
        p = PLATFORM_ALIAS.get(p, p)
        key = p.lower().replace(' ', '')
        found = norm.get(key)
        if not found:
            for nk, nv in norm.items():
                if nk and (nk in key or key.startswith(nk[:6])):
                    found = nv
                    break
        if found:
            r['_category_id'], r['_category_name'] = found[0], found[1]
            hit += 1
        else:
            miss += 1
    json.dump(recs, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('生成 %d 条记录 → %s' % (len(recs), args.out))
    print('类目匹配：命中 %d / 未匹配 %d' % (hit, miss))
    if miss:
        um = sorted({r['ext_info']['ecommerce_platform'] for r in recs if not r['_category_id']})
        print('未匹配平台(%d):' % len(um), um)


if __name__ == '__main__':
    main()
