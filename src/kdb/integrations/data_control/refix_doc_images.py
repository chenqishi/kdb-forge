#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""修复离线任务里「每页重复列出全文档图片」的解析产物。默认 dry-run。

背景：`page.get_images()` 返回的是页面资源字典，LibreOffice 转出的 PDF 会把全局
图片资源在每页重复列出，于是每一页都挂上了整篇文档的所有图。解析侧已在
`wordtotext._extract_rendered_pdf_images`（2026-07-29）改用 `page.get_text("dict")`
的图片 block 修掉，但那之前跑的任务产物仍是坏的。

本工具用当前代码重新解析，再把已有的图片理解/OCR/公网 URL 按**内容 md5** 贴回去
——实测新旧两条提取路径产出的图片字节完全一致，所以不需要重跑 VLM、也不需要重传。

详见 `function_schema/refix_doc_images.*.md`。
"""

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime

import fire

from kdb.mining.generation.processing.wordtotext import convert_docx_to_pdf, parse_pdf_to_json

IMAGE_EXTS = ('.jpeg', '.jpg', '.png', '.gif', '.bmp', '.webp')


def _file_md5(path):
    with open(path, 'rb') as handle:
        return hashlib.md5(handle.read()).hexdigest()


def build_image_md5_map(multimodal_data_info_path):
    """{图片内容 md5: 多模态 item}。本地文件已不在则跳过。"""
    with open(multimodal_data_info_path, 'r', encoding='utf-8') as handle:
        info = json.load(handle)
    md5_map, missing = {}, 0
    for item in info.values():
        path = (item or {}).get('image_path')
        if not path or not os.path.exists(path):
            missing += 1
            continue
        digest = _file_md5(path)
        md5_map.setdefault(digest, item)
    logging.info(f'多模态条目 {len(info)}，可用 md5 {len(md5_map)}，本地文件缺失 {missing}')
    return md5_map


def build_file_md5_map(old_parsed_json):
    """从该文件**自己**的旧解析产物建 md5 映射。

    比全局 multimodal_data_info.json 更全：后者只收录上传成功的图，
    而旧解析里那些被多模态阶段判为无效（public_url 为空）的图也要能对上，
    否则会被误报成"未命中"。
    """
    md5_map = {}
    for items in old_parsed_json.values():
        for item in items:
            if item.get('type') != 'image':
                continue
            path = item.get('image_path')
            if not path or not os.path.exists(path):
                continue
            md5_map.setdefault(_file_md5(path), item)
    return md5_map


# 这些字段来自多模态处理，按内容复用；image_path/fileName 用新解析的（页归属变了）
_REUSE_FIELDS = ('public_url', 's3_path', 'image_understanding', 'image_ocr',
                 'is_valid', 'is_valid_by_img_info', 'is_valid_by_ocr', 'extern_url')


def remap_parsed_images(parsed_json, md5_map):
    """把新解析结果里的图片补上已有的多模态字段。未命中的保持原样，不中断。"""
    stats = {'images': 0, 'matched': 0, 'matched_no_mm': 0, 'missed': 0, 'missed_files': []}
    result = {}
    for page, items in parsed_json.items():
        new_items = []
        for item in items:
            if item.get('type') != 'image':
                # 文本项补齐下游期望的空字段，与 content_multimodal.json 保持同构
                filled = dict(item)
                for key in ('public_url', 'image_understanding', 'image_ocr',
                            's3_path', 'fileName', 'extern_url'):
                    filled.setdefault(key, None)
                filled.setdefault('is_valid', 'False')
                new_items.append(filled)
                continue
            stats['images'] += 1
            filled = dict(item)
            path = item.get('image_path')
            digest = _file_md5(path) if path and os.path.exists(path) else None
            source = md5_map.get(digest) if digest else None
            if source:
                for key in _REUSE_FIELDS:
                    if key in source:
                        filled[key] = source[key]
                filled['fileName'] = os.path.basename(path)
                # 旧数据里本来就没多模态结果（多模态阶段判为无效图）不算问题，单独计数
                if source.get('public_url'):
                    stats['matched'] += 1
                else:
                    stats['matched_no_mm'] += 1
            else:
                for key in _REUSE_FIELDS:
                    filled.setdefault(key, None)
                filled['is_valid'] = 'False'
                filled['fileName'] = os.path.basename(path) if path else None
                stats['missed'] += 1
                stats['missed_files'].append(os.path.basename(path or ''))
            new_items.append(filled)
        result[page] = new_items
    return result, stats


def _page_text(page_items):
    return ''.join(x.get('text_content') or '' for x in page_items)


def refix_task_documents(task_id, script_dir=None, only_files=None,
                         mapping_name='translated_mapping.txt',
                         output_mapping='translated_mapping_imgfixed.txt',
                         execute=False):
    """重解析 + 贴回多模态结果。默认 dry-run。"""
    script_dir = script_dir or os.getcwd()
    task_dir = os.path.join(script_dir, 'data/off_task_data', task_id)
    mapping_path = os.path.join(task_dir, mapping_name)
    md5_map = build_image_md5_map(os.path.join(task_dir, 'multimodal_data_info.json'))

    wanted = None
    if only_files:
        with open(only_files, 'r', encoding='utf-8') as handle:
            wanted = {line.strip() for line in handle if line.strip()}

    lines = [l.rstrip('\n') for l in open(mapping_path, 'r', encoding='utf-8') if l.strip()]
    items, out_lines = [], []
    for line in lines:
        fields = line.split('\t')
        name, json_path = fields[1], fields[-1]
        if wanted is not None and name not in wanted:
            out_lines.append(line)          # 不处理的原样带过，保证文件数不丢
            continue
        record = {'file': name, 'status': 'pending'}
        docx_path = fields[3]
        try:
            old = json.load(open(json_path, 'r', encoding='utf-8'))
            record['old_images'] = sum(1 for p in old for x in old[p] if x.get('type') == 'image')

            work_dir = os.path.join(os.path.dirname(json_path), 'reparsed')
            if execute:
                if os.path.isdir(work_dir):
                    shutil.rmtree(work_dir)
                os.makedirs(work_dir, exist_ok=True)
            else:
                os.makedirs(work_dir, exist_ok=True)

            pdf_path = convert_docx_to_pdf(docx_path, output_dir=work_dir, re_parse=True)
            parsed = json.loads(parse_pdf_to_json(pdf_path, work_dir))
            if 'error' in parsed:
                raise RuntimeError(f"解析失败: {parsed['error']}")

            # 先用该文件自己的旧解析对齐，全局表只作兜底
            local_map = dict(md5_map)
            local_map.update(build_file_md5_map(old))
            fixed, stats = remap_parsed_images(parsed, local_map)
            record.update(new_images=stats['images'], matched=stats['matched'],
                          matched_no_mm=stats['matched_no_mm'],
                          missed=stats['missed'], missed_files=stats['missed_files'][:10])
            # 文本必须逐页一致，否则说明分页变了，QA 与 segment 会对不上。
            # 例外：旧解析里"零文本页"只是被 bug 挂上了整篇文档的图才显得非空，
            # 新解析该页真的没内容就会被 parse_pdf_to_json 丢掉，这不算分页变化。
            record['pages_old'], record['pages_new'] = len(old), len(fixed)
            dropped = sorted(set(old) - set(fixed), key=int)
            record['dropped_pages'] = dropped
            record['dropped_pages_had_text'] = [p for p in dropped if _page_text(old[p]).strip()]
            record['text_same'] = (
                not set(fixed) - set(old)                       # 不能凭空多出页
                and not record['dropped_pages_had_text']        # 丢掉的页必须本来就没文字
                and all(_page_text(old[p]) == _page_text(fixed[p]) for p in fixed)
            )

            fixed_path = os.path.join(os.path.dirname(json_path), 'content_multimodal_fixed.json')
            if execute and record['text_same']:
                with open(fixed_path, 'w', encoding='utf-8') as handle:
                    json.dump(fixed, handle, ensure_ascii=False, indent=2)
                fields[-1] = fixed_path
                record['status'] = 'fixed'
            elif not record['text_same']:
                record['status'] = 'skipped_text_mismatch'
            else:
                record['status'] = 'dry_run'
            out_lines.append('\t'.join(fields))
        except Exception as exc:
            record['status'] = 'failed'
            record['reason'] = f'{type(exc).__name__}: {exc}'
            logging.error(f"{name} 处理失败: {record['reason']}")
            out_lines.append(line)          # 失败沿用旧解析，不丢文件
        items.append(record)
        logging.info(f"[{len(items)}] {name} -> {record['status']} "
                     f"图 {record.get('old_images')}→{record.get('new_images')} "
                     f"复用 {record.get('matched')}/本就无 {record.get('matched_no_mm')}/"
                     f"未命中 {record.get('missed')}")

    if execute:
        with open(os.path.join(task_dir, output_mapping), 'w', encoding='utf-8') as handle:
            handle.write('\n'.join(out_lines) + '\n')

    flag = datetime.now().strftime('%Y%m%d_%H%M%S')
    report = {
        'task_id': task_id, 'execute': execute, 'generated_at': flag,
        'processed': len(items),
        'fixed': sum(1 for x in items if x['status'] == 'fixed'),
        'failed': sum(1 for x in items if x['status'] == 'failed'),
        'text_mismatch': sum(1 for x in items if x['status'] == 'skipped_text_mismatch'),
        'total_old_images': sum(x.get('old_images') or 0 for x in items),
        'total_new_images': sum(x.get('new_images') or 0 for x in items),
        'total_matched': sum(x.get('matched') or 0 for x in items),
        'total_matched_no_mm': sum(x.get('matched_no_mm') or 0 for x in items),
        'total_missed': sum(x.get('missed') or 0 for x in items),
        'output_mapping': os.path.join(task_dir, output_mapping) if execute else None,
        'items': items,
    }
    out_dir = os.path.join(script_dir, 'output/refix_doc_images')
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, f'report_{"execute" if execute else "dryrun"}_{flag}.json')
    with open(report_path, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    logging.info(f"处理 {report['processed']} | 修复 {report['fixed']} | "
                 f"失败 {report['failed']} | 分页不一致 {report['text_mismatch']} | "
                 f"图 {report['total_old_images']}→{report['total_new_images']} "
                 f"复用多模态 {report['total_matched']} | 本就无多模态 {report['total_matched_no_mm']} | "
                 f"未命中 {report['total_missed']}")
    logging.info(f'报告: {report_path}')
    return report_path


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)s] %(asctime)s: %(message)s', force=True)
    fire.Fire({'run': refix_task_documents, 'build_map': build_image_md5_map})
