from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把「整篇文档的图挂到每一页」留在库里的错图裁掉。默认 dry-run。

背景：`page.get_images()` 返回页面资源字典，LibreOffice 转出的 PDF 会把全局图片资源在
每页重复列出，于是每一页都挂上整篇文档的所有图。解析侧已在 `c52fd2d3c`（2026-07-29）
用 `wordtotext._extract_rendered_pdf_images` 修掉，但那之前入库的知识仍带着错图。
先用 `refix_doc_images.py` 重新解析拿到正确的页→图映射，本工具再按每条知识自己的
页码区间，把不属于它的图从 **答案正文** 和 `multimodal_contents` 里一起裁掉。

必须按图片内容 md5 匹配，不能按路径
------------------------------------
同一张图在旧数据里被多模态阶段当成新图反复上传，于是有多个 s3_path
（508b09ae 实测：226 张真图对应 2181 个 s3_path，最严重一张图有 22 个地址）。
修复后的解析按 md5 只贴回其中一个地址，所以**按路径比对会把几乎所有图都误判为「不属于本页」**。
这里先用任务的 `multimodal_data_info.json` 建 `s3_path -> 图片内容 md5` 的等价类。

两种数据的页码字段不一样
------------------------
- QA：`ext_info.from_page = [起, 止]`
- segment：`ext_info.start_page` / `ext_info.end_page`（整数）
搞错会导致 segment 全跳过或全裁光。

裁图前先看有没有话术指着这张图
------------------------------
正文里 `[multimodal_prefix]<path>` 就嵌在图片出现的位置，所以「如下图所示」这类话术
与它所指的图是**位置相邻**的。裁掉一张被话术指着的图，会留下
「请看图片：」却没有图的悬空话术。判据见 `find_pointing_deictic`，
三条联合：词边界 + 邻近有图片标记 + 强话术兜底。
"""

import argparse
import collections
import hashlib
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


from kdb.shared.clients.es_http_client import DEFAULT_BULK_BATCH, EsHttpClient

logging.basicConfig(level=logging.INFO,
                    format='[%(levelname)s] [%(asctime)s] %(message)s')

MARKER_RE = re.compile(r'\[multimodal_prefix\]([^\s\]]+)')

# 本身就是完整话术，不可能是别的词的一部分
STRONG_DEICTIC = [
    '如下图圆圈所示', '如下图所示', '如下截图所示', '见下方截图', '参见下方图',
    '请看图片', '请见下图', '请参见下图', '如图所示', '见下图', '下图所示',
    '下方图片', '下方海报', '右侧二维码', '扫描下方二维码', '扫描右侧二维码',
    '扫描二维码', '如下图',
]
# 需要词边界才算话术：`图中` 会撞上 视图中 / 屏幕截图中 / 产品白底图中
BOUNDARY_DEICTIC = ['图中', '上图']
# `图` 前面是这些字时，`图中` 属于别的词
_BAD_PREFIX_CHARS = set('视截底简缩略挂框标制企地意试')

DEFAULT_WINDOW = 60


# ---------------------------------------------------------------------------
# 页 -> 图 映射
# ---------------------------------------------------------------------------

def file_md5(path: str) -> Optional[str]:
    """图片文件内容 md5。文件已不在返回 None。"""
    try:
        with open(path, 'rb') as handle:
            return hashlib.md5(handle.read()).hexdigest()
    except (IOError, OSError):
        return None


def build_path_md5_map(multimodal_data_info_path: str) -> Dict[str, str]:
    """`s3_path -> 图片内容 md5`，把同一张图被重复上传出的多个地址归成一类。"""
    with open(multimodal_data_info_path, 'r', encoding='utf-8') as handle:
        info = json.load(handle)
    out: Dict[str, str] = {}
    for item in info.values():
        s3_path = item.get('s3_path')
        local = item.get('image_path')
        if not s3_path or not local:
            continue
        digest = file_md5(local)
        if digest:
            out[s3_path] = digest
    return out


def build_page_image_index(mapping_file: str) -> Dict[str, Dict[int, List[Dict[str, Any]]]]:
    """`from_file_name -> {页号: [该页真实的图片, ...]}`，读 refix 产出的修复版解析。

    mapping_file 是 `translated_mapping_imgfixed.txt`：列 [1] 是 from_file_name，
    列 [4] 是解析目录，目录下的 `content_multimodal_fixed.json` 是修复后的产物。

    每项带 `md5` / `s3_path` / `public_url` / `fileName` / `image_ocr`。
    `s3_path` 为空的是多模态阶段判为无效、从未上传的图（logo/装饰图），
    它们不会出现在 ES 正文里，但仍要计入 md5 集合（判「属于本页」用），
    只是**不能**被挂回去。
    """
    index: Dict[str, Dict[int, List[Dict[str, Any]]]] = {}
    with open(mapping_file, 'r', encoding='utf-8') as handle:
        for line in handle:
            fields = line.rstrip('\n').split('\t')
            if len(fields) < 5:
                continue
            from_file_name, parse_dir = fields[1], fields[4]
            fixed = os.path.join(parse_dir, 'content_multimodal_fixed.json')
            if not os.path.exists(fixed):
                continue
            with open(fixed, 'r', encoding='utf-8') as fh:
                pages = json.load(fh)
            per_page: Dict[int, List[Dict[str, Any]]] = {}
            for page_key, items in pages.items():
                try:
                    page_no = int(page_key)
                except (TypeError, ValueError):
                    continue
                for item in items:
                    if item.get('type') == 'text':
                        continue
                    digest = file_md5(item.get('image_path') or '')
                    if not digest:
                        continue
                    per_page.setdefault(page_no, []).append({
                        'md5': digest,
                        's3_path': item.get('s3_path'),
                        'public_url': item.get('public_url'),
                        'fileName': item.get('fileName'),
                        'image_ocr': item.get('image_ocr'),
                    })
            index[from_file_name] = per_page
    return index


def build_page_md5_index(mapping_file: str) -> Dict[str, Dict[int, Set[str]]]:
    """`build_page_image_index` 的 md5-only 视图。"""
    return {f: {p: {i['md5'] for i in items} for p, items in per_page.items()}
            for f, per_page in build_page_image_index(mapping_file).items()}


def page_items_for_range(per_page: Dict[int, List[Dict[str, Any]]],
                         page_range: Tuple[int, int]) -> List[Dict[str, Any]]:
    """页码区间内**上传过**（有 s3_path）的图，按页号、再按 fileName 排序。

    用于「话术指着的图被裁光了，而该页确实有图」时把正确的图挂回去。
    同一张图（md5 相同）只取一个地址。
    """
    start, end = page_range
    if start > end:
        start, end = end, start
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for page_no in sorted(p for p in per_page if start <= p <= end):
        for item in sorted(per_page[page_no], key=lambda i: str(i.get('fileName') or '')):
            if not item.get('s3_path') or item['md5'] in seen:
                continue
            seen.add(item['md5'])
            out.append(item)
    return out


def parse_page_range(ext_info: Dict[str, Any], data_type: str) -> Optional[Tuple[int, int]]:
    """QA 用 `from_page=[起,止]`，segment 用 `start_page`/`end_page`。取不到返回 None。"""
    if data_type == 'qa':
        pages = ext_info.get('from_page')
        if isinstance(pages, (list, tuple)) and len(pages) >= 2:
            try:
                return int(pages[0]), int(pages[1])
            except (TypeError, ValueError):
                return None
        return None
    start, end = ext_info.get('start_page'), ext_info.get('end_page')
    if start is None or end is None:
        return None
    try:
        return int(start), int(end)
    except (TypeError, ValueError):
        return None


def allowed_md5_for_range(per_page: Dict[int, Set[str]],
                          page_range: Tuple[int, int]) -> Set[str]:
    """页码区间内所有页的真实图片 md5 并集。区间是闭区间。"""
    start, end = page_range
    if start > end:
        start, end = end, start
    out: Set[str] = set()
    for page_no, digests in per_page.items():
        if start <= page_no <= end:
            out |= digests
    return out


# ---------------------------------------------------------------------------
# 话术指向判断
# ---------------------------------------------------------------------------

def _boundary_ok(content: str, start: int, phrase: str) -> bool:
    """`图中` 这类需要看前一个字，排除 视图中 / 屏幕截图中 / 产品白底图中。"""
    if phrase not in BOUNDARY_DEICTIC:
        return True
    if start == 0:
        return True
    return content[start - 1] not in _BAD_PREFIX_CHARS


def iter_deictic(content: str):
    """按出现位置 yield (起, 止, 话术, 是否强话术)。长话术优先，避免被短的切断。"""
    taken: List[Tuple[int, int]] = []

    def overlaps(a: int, b: int) -> bool:
        return any(not (b <= s or a >= e) for s, e in taken)

    for phrase in sorted(STRONG_DEICTIC + BOUNDARY_DEICTIC, key=len, reverse=True):
        start = 0
        while True:
            idx = content.find(phrase, start)
            if idx < 0:
                break
            end = idx + len(phrase)
            if not overlaps(idx, end) and _boundary_ok(content, idx, phrase):
                taken.append((idx, end))
                yield idx, end, phrase, phrase in STRONG_DEICTIC
            start = idx + 1
    taken.sort()


def find_pointing_deictic(content: str, marker_start: int,
                          window: int = DEFAULT_WINDOW) -> Optional[str]:
    """这个图片标记的前面 `window` 字内有没有话术指着它。

    只认「话术结束位置到标记起点之间不夹着别的图片标记」的那一条——
    否则一串图里最前面那句话术会被算成指着每一张图。
    """
    best: Optional[Tuple[int, str]] = None
    for start, end, phrase, _strong in iter_deictic(content):
        if end > marker_start:
            continue
        if marker_start - end > window:
            continue
        between = content[end:marker_start]
        if MARKER_RE.search(between):
            continue
        if best is None or end > best[0]:
            best = (end, phrase)
    return best[1] if best else None


def orphan_deictic(content: str, window: int = DEFAULT_WINDOW) -> List[str]:
    """没有任何图片标记邻近的强话术——「话术在但图已失联」，交人工，不自动改。"""
    markers = [m.start() for m in MARKER_RE.finditer(content)]
    out: List[str] = []
    for start, end, phrase, strong in iter_deictic(content):
        if not strong:
            continue
        if any(0 <= pos - end <= window for pos in markers):
            continue
        out.append(phrase)
    return out


# ---------------------------------------------------------------------------
# 单条知识的裁剪方案
# ---------------------------------------------------------------------------

def plan_row(content: str, images: Sequence[Dict[str, Any]],
             path_md5: Dict[str, str], allowed_md5: Set[str],
             window: int = DEFAULT_WINDOW,
             attach_candidates: Optional[Sequence[Dict[str, Any]]] = None,
             only_duplicate: bool = False,
             attach_when_no_text: bool = False) -> Dict[str, Any]:
    """算出这条知识该留哪些图、裁哪些图，以及裁的图有没有被话术指着。

    去重口径是图片内容 md5：同一张图重复出现（多个地址）只留第一次。
    md5 查不到的标记保守保留（宁可不动，不误删）。
    """
    keep_paths: List[str] = []
    drop: List[Dict[str, Any]] = []
    seen_md5: Set[str] = set()
    unknown = 0

    for match in MARKER_RE.finditer(content):
        path = match.group(1)
        digest = path_md5.get(path)
        if digest is None:
            unknown += 1
            keep_paths.append(path)
            continue
        # 去重必须先判：否则 only_duplicate 模式下超页的图会被重复保留
        if digest in seen_md5:
            drop.append({'path': path, 'md5': digest, 'reason': 'duplicate',
                         'deictic': find_pointing_deictic(content, match.start(), window)})
            continue
        if digest not in allowed_md5 and not only_duplicate:
            drop.append({'path': path, 'md5': digest, 'reason': 'page_mismatch',
                         'deictic': find_pointing_deictic(content, match.start(), window)})
            continue
        # only_duplicate：已用「重跑生成」修过的批次，图是新管线按页分配的，
        # 差一页多半是段落跨页的合法归属，不该再按严格区间裁。
        seen_md5.add(digest)
        keep_paths.append(path)

    pointed = [d for d in drop if d['deictic']]
    # 正文除了图片标记之外没有一个字 —— 这种 QA 的「答案」本来就是图
    no_text = not MARKER_RE.sub('', content).strip()
    attach: List[Dict[str, Any]] = []
    if not drop:
        action = 'noop'
    elif (pointed or (attach_when_no_text and no_text)) and not keep_paths:
        # 话术指着的图被裁光了，且这条知识一张图都不剩。
        # 该页确实有上传过的图 → 把正确的挂回去，别留下「请看图片：」却没有图。
        # 该页真没有图 → 不能自动改（只能删话术或软删），交人工。
        available = [c for c in (attach_candidates or [])
                     if c.get('s3_path') and c['md5'] not in seen_md5]
        if available:
            attach = available
            action = 'prune_and_attach'
        else:
            action = 'review_deictic'
    elif pointed:
        action = 'prune_with_deictic'
    else:
        action = 'prune'

    return {'keep_paths': keep_paths, 'drop': drop, 'action': action,
            'unknown_paths': unknown, 'attach': attach,
            'orphan_deictic': orphan_deictic(content, window)}


def rewrite_content(content: str, drop_paths: Sequence[str]) -> str:
    """把要裁掉的 `[multimodal_prefix]<path>` 整行去掉，其余原样保留。

    标记是以 `\\n[multimodal_prefix]...` 追加在正文末尾的，所以连同前导换行一起删，
    删完再把行尾多余空白收一下，正文文字本身不动。
    """
    if not drop_paths:
        return content
    remaining = set(drop_paths)
    out_lines = []
    for line in content.split('\n'):
        stripped = line.strip()
        match = MARKER_RE.fullmatch(stripped)
        if match and match.group(1) in remaining:
            continue
        out_lines.append(line)
    text = '\n'.join(out_lines)
    # 同一行里出现多个标记的情况（历史数据里有），逐个替换
    for path in remaining:
        text = text.replace('[multimodal_prefix]%s' % path, '')
    return re.sub(r'[ \t]+\n', '\n', text).rstrip()


def append_markers(content: str, paths: Sequence[str]) -> str:
    """把要补挂的图片标记追加到正文末尾，沿用现有格式（每行一个）。"""
    if not paths:
        return content
    lines = ['[multimodal_prefix]%s' % path for path in paths]
    return content.rstrip() + '\n' + '\n'.join(lines)


def attach_item_to_multimodal(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """把修复版解析里的图转成 `multimodal_contents` 的图片项格式。

    字段取 ES 里现有图片项的形状：`type` / `path` / `url` / `fileName` / `image_ocr`。
    """
    return {'type': 'image', 'path': candidate.get('s3_path'),
            'url': candidate.get('public_url'), 'fileName': candidate.get('fileName'),
            'image_ocr': candidate.get('image_ocr') or ''}


def rebuild_multimodal(images: Sequence[Dict[str, Any]], texts: Sequence[Dict[str, Any]],
                       keep_paths: Sequence[str],
                       attach: Sequence[Dict[str, Any]] = ()) -> List[Dict[str, Any]]:
    """文本项原样保留在前，图片项按 keep_paths 的顺序重建，最后接上补挂的图。"""
    by_path: Dict[str, Dict[str, Any]] = {}
    for item in images:
        by_path.setdefault(item.get('path') or '', item)
    out = list(texts)
    for path in keep_paths:
        item = by_path.get(path)
        if item is not None:
            out.append(item)
    for candidate in attach:
        out.append(attach_item_to_multimodal(candidate))
    return out


# ---------------------------------------------------------------------------
# 跑批
# ---------------------------------------------------------------------------

def _split_multimodal(row: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    texts, images = [], []
    for item in row.get('multimodal_contents') or []:
        if (item.get('type') or 'text') == 'text':
            texts.append(item)
        else:
            images.append(item)
    return texts, images


def iter_task_rows(es: EsHttpClient, index: str, task_id: str):
    query = {'bool': {'must': [{'term': {'del_flag': 0}}, {'term': {'task_id': task_id}}]}}
    fields = ['title', 'content', 'multimodal_contents', 'ext_info', 'data_type', 'task_id']
    for doc_id, src in es.iter_search_after(index, query, fields, page_size=500):
        yield doc_id, src


def run(config_path: str, index: str, task_id: str, work_dir: str,
        embedding_config: str = 'config/config_ali_embedding.json',
        window: int = DEFAULT_WINDOW, execute: bool = False,
        bulk_batch: int = DEFAULT_BULK_BATCH,
        only_duplicate: bool = False,
        attach_when_no_text: bool = False,
        only_ids: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """扫一个任务，算裁剪方案；`execute` 才写回。"""
    task_dir = os.path.join('data/off_task_data', task_id)
    mapping_file = os.path.join(task_dir, 'translated_mapping_imgfixed.txt')
    info_file = os.path.join(task_dir, 'multimodal_data_info.json')
    for path in (mapping_file, info_file):
        if not os.path.exists(path):
            raise RuntimeError('缺少 %s —— 先跑 refix_doc_images.py run --task_id=%s --execute=True'
                               % (path, task_id))

    path_md5 = build_path_md5_map(info_file)
    page_items = build_page_image_index(mapping_file)
    page_index = {f: {p: {i['md5'] for i in items} for p, items in per.items()}
                  for f, per in page_items.items()}
    logging.info('等价类: %d 个 s3_path -> %d 张真图；修复版解析覆盖 %d 个文件',
                 len(path_md5), len(set(path_md5.values())), len(page_index))

    es = EsHttpClient.from_config(config_path)
    os.makedirs(work_dir, exist_ok=True)

    stats = collections.Counter()
    plans: List[Dict[str, Any]] = []
    id_filter = set(only_ids or ())
    for doc_id, src in iter_task_rows(es, index, task_id):
        if id_filter and doc_id not in id_filter:
            continue
        texts, images = _split_multimodal(src)
        content = src.get('content') or ''
        if not images and not MARKER_RE.search(content):
            continue
        stats['带图行'] += 1
        data_type = src.get('data_type') or ''
        ext_info = src.get('ext_info') or {}
        from_file = ext_info.get('from_file_name') or ''
        page_range = parse_page_range(ext_info, data_type)
        per_page = page_index.get(from_file)
        if page_range is None:
            stats['跳过_无页码'] += 1
            continue
        if not per_page:
            stats['跳过_无修复解析'] += 1
            continue
        allowed = allowed_md5_for_range(per_page, page_range)
        # 补挂候选：先严格按本页码区间取。取不到再放宽一页——
        # 段落常在页末断开，「如下图所示」指的图落到了下一页（实测 大包裹 UCC-128 标签.docx 页[1,1]）。
        # 放宽只影响补挂这一档；批量裁剪仍按严格区间，因为 ±1 页的命中率
        # 实测 17.4% vs 随机基线 14.1%（1.24x，接近巧合），且 383 张里只有 1 张有话术指着。
        file_pages = page_items.get(from_file) or {}
        candidates = page_items_for_range(file_pages, page_range)
        widened = False
        if not candidates:
            candidates = page_items_for_range(file_pages,
                                              (page_range[0] - 1, page_range[1] + 1))
            widened = bool(candidates)
        plan = plan_row(content, images, path_md5, allowed, window, candidates,
                        only_duplicate, attach_when_no_text)
        stats['action_' + plan['action']] += 1
        stats['裁掉图次'] += len(plan['drop'])
        stats['补挂图次'] += len(plan['attach'])
        stats['保留图次'] += len(plan['keep_paths'])
        if plan['unknown_paths']:
            stats['md5未知_保守保留'] += plan['unknown_paths']
        if plan['action'] == 'noop':
            continue
        plans.append({'_id': doc_id, 'data_type': data_type, 'from_file_name': from_file,
                      'page_range': list(page_range), 'title': (src.get('title') or '')[:60],
                      'before_images': len(images), 'keep': len(plan['keep_paths']),
                      'drop': len(plan['drop']), 'action': plan['action'],
                      'attach': len(plan['attach']),
                      'attach_widened': widened and bool(plan['attach']),
                      'attach_detail': plan['attach'],
                      'deictic_hits': [d['deictic'] for d in plan['drop'] if d['deictic']],
                      'orphan_deictic': plan['orphan_deictic'],
                      'drop_detail': plan['drop'], 'keep_paths': plan['keep_paths']})

    plan_file = os.path.join(work_dir, 'plan_%s.json' % task_id[:8])
    with open(plan_file, 'w', encoding='utf-8') as handle:
        json.dump(plans, handle, ensure_ascii=False, indent=2)
    logging.info('方案已写 %s（%d 行需要改）', plan_file, len(plans))
    for key in sorted(stats):
        logging.info('  %-20s %d', key, stats[key])

    result: Dict[str, Any] = {'stats': dict(stats), 'plan_file': plan_file,
                              'rows_to_change': len(plans)}
    if not execute:
        result['dry_run'] = True
        logging.info('[dry-run] 未写回，加 --execute 才改 ES')
        return result

    from kdb.shared.clients.embedding_tools import AliEmbedding
    embedder = AliEmbedding(embedding_config)

    rollback_file = os.path.join(work_dir, 'rollback_%s.jsonl' % task_id[:8])
    updates: List[Tuple[str, Dict[str, Any]]] = []
    skipped_review = 0
    skipped_empty: List[str] = []
    image_only: List[str] = []
    row_errors: List[Dict[str, str]] = []
    with open(rollback_file, 'w', encoding='utf-8') as rb:
        for plan in plans:
            if plan['action'] == 'review_deictic':
                skipped_review += 1
                continue
            # 单行出错只跳过这一行。整批被一行打死过一次（DashScope 对空输入返回 400），
            # 那次 271 行一条都没写进去。
            try:
                doc = es.search(index, {'query': {'ids': {'values': [plan['_id']]}}, 'size': 1,
                                        '_source': ['content', 'multimodal_contents']})
                hits = doc['hits']['hits']
                if not hits:
                    continue
                src = hits[0]['_source']
                texts, images = _split_multimodal(src)
                attach = plan.get('attach_detail') or []
                new_content = rewrite_content(src.get('content') or '',
                                              [d['path'] for d in plan['drop_detail']])
                new_content = append_markers(new_content, [c['s3_path'] for c in attach])

                # 有些 QA 的答案正文**本来就只有图片、没有一个字**，裁完会变成空串，
                # DashScope embedding 对空输入返回 400。这种不自动改，交人工。
                if not new_content.strip():
                    skipped_empty.append(plan['_id'])
                    continue
                if not MARKER_RE.sub('', new_content).strip():
                    # 正文无文字、只剩图片标记：仍可写回（原来也是这样），但要报出来
                    image_only.append(plan['_id'])

                rb.write(json.dumps({'_id': plan['_id'], 'content': src.get('content'),
                                     'multimodal_contents': src.get('multimodal_contents')},
                                    ensure_ascii=False) + '\n')
                new_mm = rebuild_multimodal(images, texts, plan['keep_paths'], attach)
                new_embedding = embedder.text2embedding(new_content)
                try:
                    new_embedding = new_embedding.reshape(-1).tolist()
                except AttributeError:
                    new_embedding = list(new_embedding)
                updates.append((plan['_id'], {'content': new_content,
                                              'multimodal_contents': new_mm,
                                              'content_embedding': new_embedding}))
            except Exception as exc:  # noqa: BLE001 - 单行失败不该中断整批
                logging.error('行 %s 处理失败，跳过: %s', plan['_id'], exc)
                row_errors.append({'_id': plan['_id'], 'error': str(exc)[:200]})
    logging.info('回滚文件 %s；待写回 %d 行，留待人工 %d 行，正文裁空跳过 %d 行，'
                 '无文字只剩图 %d 行，处理失败 %d 行',
                 rollback_file, len(updates), skipped_review, len(skipped_empty),
                 len(image_only), len(row_errors))
    bulk = es.bulk_update_doc(index, updates, batch_size=bulk_batch)
    result.update({'updated': bulk.get('updated', 0), 'failed': bulk.get('failed', []),
                   'rollback_file': rollback_file, 'left_for_review': skipped_review,
                   'skipped_empty_text': skipped_empty, 'image_only_rows': image_only,
                   'row_errors': row_errors})
    logging.info('写回完成 updated=%d failed=%d', result['updated'], len(result['failed']))
    return result


def rollback(config_path: str, index: str, rollback_file: str,
             embedding_config: str = 'config/config_ali_embedding.json',
             bulk_batch: int = DEFAULT_BULK_BATCH, execute: bool = False) -> Dict[str, Any]:
    """按 rollback.jsonl 把 content / multimodal_contents 写回原值，并重算 embedding。"""
    es = EsHttpClient.from_config(config_path)
    rows = [json.loads(l) for l in open(rollback_file, 'r', encoding='utf-8') if l.strip()]
    if not execute:
        logging.info('[dry-run] 将回滚 %d 行', len(rows))
        return {'planned': len(rows), 'dry_run': True}
    from kdb.shared.clients.embedding_tools import AliEmbedding
    embedder = AliEmbedding(embedding_config)
    updates = []
    for row in rows:
        emb = embedder.text2embedding(row.get('content') or '')
        try:
            emb = emb.reshape(-1).tolist()
        except AttributeError:
            emb = list(emb)
        updates.append((row['_id'], {'content': row.get('content'),
                                     'multimodal_contents': row.get('multimodal_contents'),
                                     'content_embedding': emb}))
    return es.bulk_update_doc(index, updates, batch_size=bulk_batch)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('run', help='扫一个任务并裁图')
    p.add_argument('--config', default='config/config_es_engine.json')
    p.add_argument('--embedding_config', default='config/config_ali_embedding.json')
    p.add_argument('--index', required=True)
    p.add_argument('--task_id', required=True)
    p.add_argument('--work_dir', required=True)
    p.add_argument('--window', type=int, default=DEFAULT_WINDOW,
                   help='话术到图片标记的最大字符距离，默认 60')
    p.add_argument('--bulk_batch', type=int, default=DEFAULT_BULK_BATCH)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--attach_when_no_text', action='store_true',
                   help='正文除图片标记外没有一个字时（这种 QA 的答案本来就是图），'
                        '若该页有上传过的正确图就补挂，而不是当成裁空跳过')
    p.add_argument('--only_ids', default=None,
                   help='逗号分隔的 _id，只处理这些行。用于精准修单条，不动同任务其余行')
    p.add_argument('--only_duplicate', action='store_true',
                   help='只裁同内容重复图，不按页码区间裁。用于已经「重跑生成」修过的批次：'
                        '它的图是新管线按页分配的，差一页多半是段落跨页的合法归属')

    r = sub.add_parser('rollback', help='按 rollback.jsonl 撤销')
    r.add_argument('--config', default='config/config_es_engine.json')
    r.add_argument('--embedding_config', default='config/config_ali_embedding.json')
    r.add_argument('--index', required=True)
    r.add_argument('--rollback_file', required=True)
    r.add_argument('--bulk_batch', type=int, default=DEFAULT_BULK_BATCH)
    r.add_argument('--execute', action='store_true')

    args = parser.parse_args()
    if args.cmd == 'run':
        ids = [x.strip() for x in args.only_ids.split(',')] if args.only_ids else None
        out = run(args.config, args.index, args.task_id, args.work_dir,
                  args.embedding_config, args.window, args.execute, args.bulk_batch,
                  args.only_duplicate, args.attach_when_no_text, ids)
    else:
        out = rollback(args.config, args.index, args.rollback_file,
                       args.embedding_config, args.bulk_batch, args.execute)
    print(json.dumps({k: v for k, v in out.items() if k != 'failed'},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
