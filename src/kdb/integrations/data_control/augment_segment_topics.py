#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""给段落知识补「用户可能怎么问」的相似语义问法，写回 ES indexes[]。默认 dry-run。

段落自带的 topics 用的是官方译法（曝光量 / 会话 / 列表(listing) / 报告中心），
而卖家实际问的是「链接流量数据怎么导出」。实测同一条段落，问「如何下载报告中心的报告」
能排到向量 top2，问「如何导出链接流量数据」连 top100 都进不去 —— 差距全在问法。

只追加 indexes，不动正文与正文向量。详见 `function_schema/augment_segment_topics.*.md`。
"""

import json
import logging
import os
import re
from datetime import datetime

import fire
import requests

from commons.embedding_tools import AliEmbedding
from commons.local_llm_adapter import request_knowledge_llm

SYSTEM_PROMPT = """你是电商平台知识库的检索优化助手。给定一段平台帮助文档的正文，
写出真实卖家会用来搜索这段内容的问法。

**最关键的一条**：文档用的是官方译法，卖家不会那么说话。你必须把官方词**换成卖家的日常说法**
再提问，而不是照抄文档里的词。对照表（左边是卖家说法，右边是文档说法，你要用左边）：

| 卖家会说 | 文档写的 |
|---|---|
| 链接 / 产品链接 / listing | 列表 / SKU / 商品 |
| 流量 / 访客 / 曝光 / 浏览量 | 会话 / 会话量 / 总曝光量 |
| 转化 | 转化率 / 单位会话百分比 |
| 导出 / 下载 / 拉数据 / 导表 | 下载报告 / 生成报告 |
| 后台 / 卖家后台 | Partner Home |
| 报表 / 数据 | 报告 / 报告中心 |
| 广告花了多少 / 广告效果 | 赞助产品支出 / 广告支出回报率 |
| 差评 / 退货 | 客户反馈 / 退货详情 |

要求：
1. 一行一条，只写问句，不要编号、不要解释、不要空行。
2. **至少一半**的问法要用上表左边的卖家说法，把同一件事换成卖家的问法再问一遍。
3. 动词也换着说：导出 / 下载 / 拉 / 导表 / 在哪看 / 怎么查。
4. 只问这段正文真正能回答的问题，不要编造正文里没有的功能。
5. 不要重复"已有问法"里列出的表述。"""


# 模型即便给了对照表也常常照抄文档词（实测"列表的流量数据在哪看？"只有 0.710，
# 换成"链接的流量数据怎么导出？"就是 0.987）。所以在模型产出之后再做一遍**确定性替换**，
# 把文档说法机械地扩写成卖家说法。这些文本只进 indexes 用于向量匹配，不会展示给用户。
TERM_VARIANTS = [
    ('列表', ['链接', '产品链接']),
    ('SKU', ['链接', '产品链接']),
    ('会话量', ['流量', '访客数']),
    ('会话', ['流量']),
    ('总曝光量', ['曝光量', '流量']),
    ('浏览量', ['流量']),
]
# 顺序无关紧要：_verb_swaps 会按长度从长到短匹配，命中一个就停，
# 避免 '在哪里查询' 被短模式 '在哪里查' 切成 '怎么导出询'。
ACTION_VARIANTS = [
    ('在哪里查询', ['怎么导出', '怎么下载']),
    ('在哪查询', ['怎么导出']),
    ('怎么查询', ['怎么导出']),
    ('在哪里看', ['怎么导出', '怎么下载']),
    ('在哪里查', ['怎么导出']),
    ('在哪看', ['怎么导出', '怎么下载']),
    ('在哪查', ['怎么导出']),
    ('怎么看', ['怎么导出']),
    ('怎么查', ['怎么导出']),
    ('怎么统计', ['怎么导出']),
]
MAX_VARIANTS_PER_TOPIC = 3


# 文档只写指标术语（"会话量计算规则"），卖家问的是"对象+口语指标+动作"
# （"链接的流量数据怎么导出？"）。光靠替换跨不过去，因为原句里既没有对象词也没有动作词。
# 实测同一段落：「会话量怎么统计计算？」对 query「如何导出链接流量数据」只有 0.539，
# 补成「链接的流量数据怎么导出？」是 0.987。
METRIC_TERMS = [
    ('总曝光量', ['曝光', '流量']),
    ('曝光量', ['曝光']),
    ('会话量', ['流量', '访客']),
    ('会话', ['流量']),
    ('浏览量', ['流量']),
    ('转化率', ['转化']),
    ('点击量', ['点击']),
    ('加入购物车率', ['加购']),
]
OBJECT_TERMS = ['产品链接', '链接']
METRIC_TEMPLATES = ['{obj}的{metric}数据怎么导出？', '{obj}的{metric}数据在哪看？']
MAX_METRIC_TOPICS = 12


def build_object_metric_topics(content, existing_texts=None, max_topics=MAX_METRIC_TOPICS):
    """按段落正文里出现的指标词，拼出"对象 × 口语指标 × 动作"的卖家问法。

    只用正文里真的出现过的指标，不会给不谈流量的段落硬塞流量问法。
    """
    body = _clean_content(content)
    if not body:
        return []
    metrics, matched = [], []
    for doc_term, seller_terms in METRIC_TERMS:
        if doc_term not in body:
            continue
        # 长词优先：命中"总曝光量"后不再按"曝光量"重复产一遍
        if any(doc_term in longer for longer in matched):
            continue
        matched.append(doc_term)
        for seller in seller_terms:
            if seller not in metrics:
                metrics.append(seller)

    seen = {_norm(t) for t in (existing_texts or []) if t}
    out = []
    # 模板在最外层：先让每个指标都拿到"怎么导出"，再回头补"在哪看"，
    # 否则上限会被前一两个指标吃满，后面的指标一条都轮不到。
    for template in METRIC_TEMPLATES:
        for metric in metrics:
            for obj in OBJECT_TERMS:
                topic = template.format(obj=obj, metric=metric)
                key = _norm(topic)
                if key in seen:
                    continue
                seen.add(key)
                out.append(topic)
                if len(out) >= max_topics:
                    return out
    return out


def _noun_swaps(text):
    """按术语表做名词替换。长词优先，避免"会话"命中"会话量"的前缀产出"流量量"。"""
    hits = [(doc, sellers) for doc, sellers in TERM_VARIANTS if doc in text]
    # 被更长的命中词包含的短词跳过（会话 ⊂ 会话量）
    hits = [(d, s) for d, s in hits
            if not any(d != other and d in other for other, _ in hits)]
    out = []
    for doc, sellers in hits:
        for seller in sellers:
            out.append(text.replace(doc, seller))
    return out


def _verb_swaps(text):
    """把"在哪看/怎么查"这类换成"怎么导出/怎么下载"。

    按模式长度从长到短匹配，命中第一个就返回：短模式是长模式的前缀
    （'在哪里查' ⊂ '在哪里查询'），先命中短的会切出"怎么导出询"这种废话。
    """
    for view, exports in sorted(ACTION_VARIANTS, key=lambda kv: -len(kv[0])):
        if view not in text:
            continue
        return [text.replace(view, export) for export in exports]
    return []


def expand_term_variants(topics, existing_texts=None, max_variants_per_topic=MAX_VARIANTS_PER_TOPIC):
    """把模型产出的问法按术语对照表机械扩写成卖家说法的变体。

    候选顺序：名词+动词都换过的排最前——实测这种组合才够贴近"导出X数据"的问法
    （"列表的流量数据在哪看？"0.710 → "链接的流量数据怎么导出？"0.987）。
    只在替换真的发生时才产出；结果去重且不与已有文本重复。
    """
    seen = {_norm(t) for t in (existing_texts or []) if t}
    seen |= {_norm(t) for t in topics}
    out = []
    for topic in topics:
        # 去掉"（会话量）"这类夹注：官方词留在句子里会拉低与口语 query 的相似度
        stripped = re.sub(r'[（(][^）)]{1,12}[）)]', '', topic).strip()
        bases = [topic] + ([stripped] if stripped and stripped != topic else [])

        combined, noun_only, verb_only = [], [], []
        for base in bases:
            nouns = _noun_swaps(base)
            noun_only.extend(nouns)
            verb_only.extend(_verb_swaps(base))
            for noun_form in nouns:
                combined.extend(_verb_swaps(noun_form))
        candidates = combined + noun_only + verb_only
        if stripped and stripped != topic:
            candidates.append(stripped)

        made = 0
        for cand in candidates:
            cand = cand.strip()
            key = _norm(cand)
            if not cand or len(cand) < 4 or len(cand) > 60 or key in seen:
                continue
            seen.add(key)
            out.append(cand)
            made += 1
            if made >= max_variants_per_topic:
                break
    return out


def _clean_content(content):
    """去掉图片占位与多余空白，只留可读正文。"""
    text = re.sub(r'\[multimodal_prefix\]\S+', '', str(content or ''))
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'第\d+页内容如下[:：]', '', text)
    return re.sub(r'\n{2,}', '\n', text).strip()


def _norm(text):
    return re.sub(r'\s+', '', str(text or '')).strip('。？?！!').lower()


def generate_similar_topics(content, existing_texts, count=10, model_name=None, provider=None):
    """生成相似语义问法。模型不可用或没解析出东西时返回 []，由调用方跳过。"""
    body = _clean_content(content)
    if not body:
        return []
    existing = [t for t in (existing_texts or []) if t]
    query = (f"正文：\n{body[:4000]}\n\n"
             f"已有问法（不要重复）：\n" + '\n'.join(existing[:40]) +
             f"\n\n请写 {count} 条新的问法。")
    try:
        answer = request_knowledge_llm(query, SYSTEM_PROMPT, model_name=model_name,
                                       provider=provider, temperature=0.6, max_tokens=1200)
    except Exception as exc:
        logging.error(f'生成问法失败: {type(exc).__name__}: {exc}')
        return []
    if not answer:
        return []

    seen = {_norm(t) for t in existing}
    topics = []
    for line in answer.split('\n'):
        line = re.sub(r'^\s*[\d]+[.、)]\s*', '', line).strip().strip('-•* ')
        if not line or len(line) < 4 or len(line) > 60:
            continue
        key = _norm(line)
        if key in seen:
            continue
        seen.add(key)
        topics.append(line)
    topics = topics[:count]
    variants = expand_term_variants(topics, existing)
    metric_topics = build_object_metric_topics(content, existing + topics + variants)
    return topics + variants + metric_topics


def _es_conf(es_config):
    cfg = json.load(open(es_config, 'r', encoding='utf-8'))
    return cfg['hosts'][0].rstrip('/'), (cfg.get('username'), cfg.get('password'))


def _load_name_filter(only_file, only_files):
    """支持单文件名或"每行一个文件名"的清单；清单用于把大批量切片并行跑。"""
    names = set()
    if only_file:
        names.add(only_file)
    if only_files:
        with open(only_files, 'r', encoding='utf-8') as handle:
            names |= {line.strip() for line in handle if line.strip()}
    return names or None


def _scroll_segments(host, auth, index_name, task_id, only_file=None, only_files=None):
    docs, after = [], None
    while True:
        body = {
            'query': {'bool': {'filter': [{'term': {'task_id.keyword': task_id}},
                                          {'term': {'del_flag': 0}}]}},
            'size': 300, 'sort': [{'_id': 'asc'}],
            '_source': ['content', 'data_type', 'indexes.text', 'ext_info.from_file_name'],
        }
        if after:
            body['search_after'] = after
        resp = requests.post(f'{host}/{index_name}/_search', auth=auth, json=body, timeout=180)
        resp.raise_for_status()
        hits = resp.json()['hits']['hits']
        if not hits:
            break
        docs += hits
        after = hits[-1]['sort']
    # data_type 没有 keyword 索引，term 查不到，只能客户端过滤
    out = [h for h in docs if h['_source'].get('data_type') == 'segment']
    names = _load_name_filter(only_file, only_files)
    if names:
        out = [h for h in out
               if (h['_source'].get('ext_info') or {}).get('from_file_name') in names]
    return out


def augment_task_segments(task_id, index_name='wayfair', execute=False, count=10, only_file=None,
                          only_files=None, output_dir='output/augment_segment_topics',
                          es_config='config/config_es_engine.json',
                          embedding_config='config/config_ali_embedding.json',
                          model_name=None, provider=None):
    """批量补问法。默认 dry-run，execute=True 才写库。"""
    os.makedirs(output_dir, exist_ok=True)
    flag = datetime.now().strftime('%Y%m%d_%H%M%S')
    host, auth = _es_conf(es_config)
    segments = _scroll_segments(host, auth, index_name, task_id, only_file, only_files)
    logging.info(f'待处理段落 {len(segments)}')

    embedder = AliEmbedding(embedding_config) if execute else None
    rollback_tag = os.path.splitext(os.path.basename(only_files))[0] + '_' if only_files else ''
    rollback_path = os.path.join(output_dir, f'rollback_{rollback_tag}{flag}.jsonl')
    rollback = open(rollback_path, 'w', encoding='utf-8') if execute else None

    items, added, skipped, failed = [], 0, 0, 0
    for i, hit in enumerate(segments, start=1):
        doc_id, src = hit['_id'], hit['_source']
        existing = [x.get('text') for x in (src.get('indexes') or []) if isinstance(x, dict)]
        record = {'id': doc_id,
                  'file': (src.get('ext_info') or {}).get('from_file_name'),
                  'existing_indexes': len(existing), 'status': 'pending'}
        try:
            topics = generate_similar_topics(src.get('content'), existing, count=count,
                                             model_name=model_name, provider=provider)
            record['new_topics'] = topics
            if not topics:
                record['status'] = 'skipped'
                record['reason'] = '模型没产出可用问法'
                skipped += 1
                items.append(record)
                continue
            if not execute:
                record['status'] = 'dry_run'
                added += len(topics)
                items.append(record)
                continue

            new_entries = []
            for topic in topics:
                vector = embedder.text2embedding(topic)
                if vector is None:
                    raise RuntimeError(f'向量生成返回 None: {topic}')
                new_entries.append({'text': topic, 'embedding': vector.tolist()})

            rollback.write(json.dumps({'id': doc_id, 'added_texts': topics},
                                      ensure_ascii=False) + '\n')
            rollback.flush()

            # 只追加，不重写整个 indexes，避免把已有向量弄丢
            script = {
                'source': 'for (e in params.entries) { ctx._source.indexes.add(e) }',
                'params': {'entries': new_entries},
            }
            resp = requests.post(f'{host}/{index_name}/_update/{doc_id}', auth=auth,
                                 json={'script': script}, timeout=180)
            body = resp.json()
            if resp.status_code >= 300 or body.get('error'):
                raise RuntimeError(f'ES update 失败: {str(body)[:200]}')
            record['status'] = 'augmented'
            added += len(topics)
        except Exception as exc:
            record['status'] = 'failed'
            record['reason'] = f'{type(exc).__name__}: {exc}'
            failed += 1
            logging.error(f'{doc_id} 失败: {record["reason"]}')
        items.append(record)
        if i % 20 == 0:
            logging.info(f'进度 {i}/{len(segments)}，已追加 {added}')

    if rollback:
        rollback.close()

    report = {
        'task_id': task_id, 'index_name': index_name, 'execute': execute,
        'generated_at': flag, 'segments': len(segments),
        'added_topics': added, 'skipped': skipped, 'failed': failed,
        'rollback_file': rollback_path if execute else None, 'items': items,
    }
    tag = os.path.splitext(os.path.basename(only_files))[0] + '_' if only_files else ''
    report_path = os.path.join(output_dir,
                               f'report_{tag}{"execute" if execute else "dryrun"}_{flag}.json')
    with open(report_path, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    logging.info(f'段落 {len(segments)} | 新增问法 {added} | 跳过 {skipped} | 失败 {failed}')
    logging.info(f'报告: {report_path}')
    return report_path


def rollback_augment(rollback_file, index_name='wayfair', es_config='config/config_es_engine.json'):
    """按回滚文件把本次追加的问法从 indexes[] 里剔除。"""
    host, auth = _es_conf(es_config)
    done = failed = 0
    for line in open(rollback_file, 'r', encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        try:
            script = {
                'source': 'ctx._source.indexes.removeIf(e -> params.texts.contains(e.text))',
                'params': {'texts': rec['added_texts']},
            }
            resp = requests.post(f'{host}/{index_name}/_update/{rec["id"]}', auth=auth,
                                 json={'script': script}, timeout=180)
            if resp.status_code >= 300 or resp.json().get('error'):
                raise RuntimeError(str(resp.json())[:200])
            done += 1
        except Exception as exc:
            failed += 1
            logging.error(f'{rec["id"]} 回滚失败: {exc}')
    logging.info(f'回滚完成 {done}，失败 {failed}')
    return done


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)s] %(asctime)s: %(message)s', force=True)
    fire.Fire({'run': augment_task_segments, 'rollback': rollback_augment})
