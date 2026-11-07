#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
按来源类型导出有效 QA 到 Excel（只读脚本，不写 ES）。

典型场景：导出 mercado / mercado_local 里「文档 / 网页 / 免审录入」三类来源、
且审核通过（audit_result > 0）、未软删（del_flag=0）的 QA。

为什么不直接用 control_script/gen_audit_data.sh（现有导出方法）：

1. gen_audit_data 走 `scroll_search`，而这批索引在阿里云 ES Serverless 上，
   Serverless 不支持 scroll，只能 search_after。
2. gen_audit_data 没有 from_type_norm 过滤，且 dump 的 _source 带 embedding，
   历史产物单文件 100MB+。
3. commons.schema_trans.trans_es_data_to_excel 是扁平 `data.get(header)`，
   取不到嵌套的 primary_category.*。

所以这里只接管「查 ES + 拍平成行」，xlsx 落盘仍复用 trans_es_data_to_excel。

关于 from_type_norm 的历史写法：存量数据里 auto_learning / teacher_training / other
各自还有一份中文旧值（自动学习 / 老师培训 / 其他），按 from_type_norm 过滤有漏数据的风险
（见 docs/payoneer_olive_quality_relabel.md）。本脚本的 --from-type-norm 支持直接把
中文旧值一并传进来；导出前会打印命中分布，务必对着 ES 聚合核一遍。

用法：

    # 抽样看几行
    PYTHONPATH=. python data_control_tools/export_qa_to_excel.py \\
        --indexes mercado,mercado_local --limit 50 \\
        --output-dir output/mercado_qa_export_sample

    # 全量（只要三类来源的 qa）
    PYTHONPATH=. python data_control_tools/export_qa_to_excel.py \\
        --indexes mercado,mercado_local \\
        --from-type-norm document,html,manual \\
        --min-audit-result 1 \\
        --output-dir output/mercado_qa_export_20260811

    # 导「所有知识」：不限来源、qa + segment 都要
    PYTHONPATH=. python data_control_tools/export_qa_to_excel.py \\
        --indexes mercado,mercado_local \\
        --from-type-norm all --data-type all \\
        --min-audit-result 1 \\
        --output-dir output/mercado_all_knowledge_export
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('data_control_tools/export_qa_to_excel.py')

import argparse
import json
import logging
import os
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from commons.es_http_client import EsHttpClient  # noqa: E402
from commons.schema_trans import trans_es_data_to_excel  # noqa: E402

DEFAULT_ES_CONFIG = os.path.join(PROJECT_ROOT, 'config', 'config_es_engine.json')

DEFAULT_INDEXES = ['mercado', 'mercado_local']
DEFAULT_FROM_TYPE_NORMS = ['document', 'html', 'manual']

# from_type_norm -> 中文标签。
# 归一规则见 knowledge_interface_tools.knowledge_tools.get_from_norm_type：
# manual 覆盖 from_type 里所有 handle* / manual*，对应产品侧的「免审录入」。
# 中文 key 是存量数据里的历史写法，原样映射回同一个标签。
FROM_TYPE_NORM_LABELS = {
    'document': '文档',
    'html': '网页',
    'manual': '免审录入',
    'manual_input': '免审录入',
    'auto_learning': '自动学习',
    'teacher_training': '老师培训',
    'other': '其他',
    '自动学习': '自动学习',
    '老师培训': '老师培训',
    '其他': '其他',
}

# primary_category 最深支持到 cate4（见 es_search_interface 的 mapping）
MAX_CATEGORY_LEVEL = 4

# 完全没有类目信息的文档落到默认类目。
# 用「默认分组」而不是别的字面量：category_id=1 在类目树里就叫这个，
# 索引里已有的默认类目文档 category_path 也是它，不要凭空造一个树上没有的名字。
DEFAULT_CATEGORY = '默认分组'

# 只取需要的字段，显式不要 title_embedding / content_embedding / indexes[].embedding
# 只取 ext_info.from_file_name，不要整个 ext_info：里面的 topics / phrases / tags
# 是几十条的长数组，整对象拉下来白白几倍流量。
SOURCE_FIELDS = [
    'title', 'content', 'dataset', 'data_type', 'platform', 'from_type', 'from_type_norm',
    'audit_result', 'quality_level', 'primary_category', 'category_infos',
    'ext_info.from_file_name', 'insert_time',
]

# 全量表头 = 行 dict 的 key，trans_es_data_to_excel 按 header 逐个 data.get()。
# JSONL 永远落全量字段，只有 xlsx 的列可以用 --columns 裁剪。
HEADERS = [
    '_id', 'index_name', 'dataset', 'data_type', 'from_type_norm', 'from_file_name',
    'category_path', 'title', 'content', 'audit_result', 'quality_level', 'insert_time',
]


# openpyxl 遇到这些控制字符会抛 IllegalCharacterError，
# 而 trans_es_data_to_excel 是逐行 try/except continue —— 抛了就**整行被静默丢掉**。
# 所以在拍平阶段就洗掉，保证 JSONL 与 xlsx 行数一致。
_ILLEGAL_XLSX_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

# Excel 单元格上限 32767 字符，超了同样是抛错 -> 整行丢失
MAX_CELL_LEN = 32767


# ---------------------------------------------------------------------------
# 纯函数：查询构造 / 字段抽取
# ---------------------------------------------------------------------------

def select_headers(columns: Optional[str]) -> List[str]:
    """
    `--columns` 解析成 xlsx 表头。传空/all 就是全量 HEADERS。

    只允许从 HEADERS 里挑，且保留传入顺序；写错列名直接抛错——
    trans_es_data_to_excel 对取不到的 header 是写空单元格，
    拼错一个列名就会安静地出一整列空白。
    """
    if not columns or columns.strip().lower() == 'all':
        return list(HEADERS)
    picked = [x.strip() for x in columns.split(',') if x.strip()]
    unknown = [c for c in picked if c not in HEADERS]
    if unknown:
        raise ValueError(f'未知列 {unknown}，可选：{HEADERS}')
    if not picked:
        raise ValueError('--columns 不能是空列表')
    return picked


def clean_cell_text(value: Any) -> Any:
    """洗掉 Excel 不接受的控制字符并截断超长文本；非字符串原样返回。"""
    if not isinstance(value, str):
        return value
    cleaned = _ILLEGAL_XLSX_CHARS.sub('', value)
    if len(cleaned) > MAX_CELL_LEN:
        cleaned = cleaned[:MAX_CELL_LEN - 10] + '…[已截断]'
    return cleaned


def normalize_data_types(data_type: Any) -> List[str]:
    """
    `--data-type` 取值归一成列表。

    `all` / 空 -> 空列表（不加 data_type 过滤，qa 与 segment 全导）；
    `qa,segment` 这类逗号串 -> 列表。
    知识不止 qa 一种：文档挖掘同时产出 `data_type=segment` 的长文片段，
    只按 `term data_type=qa` 过滤会把 segment 整批漏掉。
    """
    if data_type is None:
        return []
    if isinstance(data_type, (list, tuple, set)):
        values = [str(x).strip() for x in data_type]
    else:
        values = [x.strip() for x in str(data_type).split(',')]
    values = [v for v in values if v]
    if not values or any(v.lower() == 'all' for v in values):
        return []
    return values


def build_export_query(from_type_norms: List[str], min_audit_result: int = 1,
                       data_type: Any = 'qa',
                       include_deleted: bool = False,
                       missing_fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    构造导出过滤条件：来源类型 + data_type + audit_result 下限 + 未软删。

    min_audit_result 用 gte 而不是 terms：审核值的口径历史上变过
    （老文档写 1=通过/2=不通过，当前自动审核是 high -> 2），
    「有效」统一按 audit_result > 0 理解，新增取值也不会漏。

    missing_fields：只导「缺这些字段里任意一个」的文档，用于盘点脏数据
    （如 payoneer_olive 有 2629 条缺 `dataset`，前端保存时会报错）。
    传了它就**不再加 audit_result 下限**——盘点脏数据要的是全量，
    按"有效知识"的口径筛会把 audit_result<=0 的漏掉。
    多字段用 should + minimum_should_match=1，不能写成 must_not 全列
    （那是「全都缺」，会静默少捞，`supply_missing_field` 上踩过）。
    """
    filters: List[Dict[str, Any]] = []
    if from_type_norms:
        filters.append({'terms': {'from_type_norm': list(from_type_norms)}})
    data_types = normalize_data_types(data_type)
    if len(data_types) == 1:
        filters.append({'term': {'data_type': data_types[0]}})
    elif data_types:
        filters.append({'terms': {'data_type': data_types}})
    if not missing_fields:
        filters.append({'range': {'audit_result': {'gte': min_audit_result}}})
    if not include_deleted:
        filters.append({'term': {'del_flag': 0}})
    query: Dict[str, Any] = {'bool': {'filter': filters}}
    if missing_fields:
        query['bool']['should'] = [
            {'bool': {'must_not': {'exists': {'field': name}}}} for name in missing_fields]
        query['bool']['minimum_should_match'] = 1
    return query


def norm_from_type_label(from_type_norm: Optional[str]) -> str:
    """from_type_norm -> 中文标签；认不出来的原样返回，绝不静默吞掉。"""
    if not from_type_norm:
        return ''
    return FROM_TYPE_NORM_LABELS.get(from_type_norm, from_type_norm)


def extract_from_file_name(source: Dict[str, Any]) -> str:
    """
    来源文件/网页：网页类是原文 URL，文档类是文件名（`xxx.docx`），
    免审录入 / 早期导入是 Excel 表名。

    存在 `ext_info` 里而不是顶层，字段名也是 `from_file_name`
    （`es_search_interface` 里按条件查时要显式映射成 `ext_info.from_file_name.keyword`）。
    没有的返回空串：mercado 334 条、mercado_local 16 条原数据就没有这个字段。
    """
    ext = source.get('ext_info') or {}
    return ext.get('from_file_name') or ''


def extract_category(source: Dict[str, Any],
                     default_category: str = DEFAULT_CATEGORY) -> str:
    """
    取类目全路径（如 `运营问题类型-Listing管理`）。

    primary_category 里**没有** category_name 这个子字段（见
    search_index_data_interface 构造 primary_category 的那段），
    只有 category_path 和 cate1_name/cate2_name/...，所以全路径取 category_path，
    它为空时用 cate1..cateN 名字自己拼一条。

    再退一步：primary_category 整个缺失时回落到 category_infos 里 score 最高那条的
    category_name；两者皆无则给默认类目，不留空。
    """
    primary = source.get('primary_category') or {}
    path = primary.get('category_path')
    if path:
        return path

    names = [primary.get(f'cate{level}_name') for level in range(1, MAX_CATEGORY_LEVEL + 1)]
    names = [n for n in names if n]
    if names:
        return '-'.join(names)

    infos = [c for c in (source.get('category_infos') or []) if c.get('category_name')]
    if infos:
        best = sorted(infos, key=lambda x: x.get('score') or 0, reverse=True)[0]
        return best['category_name']

    return default_category


def flatten_doc(doc_id: str, source: Dict[str, Any], index_name: str,
                default_category: str = DEFAULT_CATEGORY) -> Dict[str, Any]:
    """ES _source -> 扁平行 dict，key 与 HEADERS 一一对应。"""
    row = {
        '_id': doc_id,
        'index_name': index_name,
        'dataset': source.get('dataset') or '',
        'data_type': source.get('data_type') or '',
        'from_type_norm': norm_from_type_label(source.get('from_type_norm')),
        'from_file_name': extract_from_file_name(source),
        'category_path': extract_category(source, default_category),
        'title': source.get('title') or '',
        'content': source.get('content') or '',
        'audit_result': source.get('audit_result'),
        'quality_level': source.get('quality_level') or '',
        # 录入时间取 insert_time，不能用 update_time：批量重打标 / 批量改字段
        # 会把整批 update_time 刷成同一个时间（mercado_local 里就是 2026-07-23），
        # 那不是知识录入时间。
        'insert_time': source.get('insert_time') or '',
    }
    return {k: clean_cell_text(v) for k, v in row.items()}


# ---------------------------------------------------------------------------
# 导出流程
# ---------------------------------------------------------------------------

def export_rows(es: EsHttpClient, indexes: List[str], query: Dict[str, Any],
                rows_file: str, page_size: int = 1000,
                limit: Optional[int] = None,
                default_category: str = DEFAULT_CATEGORY) -> List[Dict[str, Any]]:
    """逐索引 search_after 拉取并拍平，写 JSONL（一行一条），返回全部行。"""
    rows: List[Dict[str, Any]] = []
    with open(rows_file, 'w', encoding='utf-8') as f:
        for index in indexes:
            got = 0
            for doc_id, source in es.iter_search_after(index, query, SOURCE_FIELDS,
                                                       page_size=page_size, limit=limit):
                row = flatten_doc(doc_id, source, index, default_category)
                rows.append(row)
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
                got += 1
                if got % 2000 == 0:
                    logging.info('%s 已拉取 %d 条', index, got)
            logging.info('%s 拉取完成，共 %d 条', index, got)
    logging.info('明细已落盘 %s，共 %d 条', rows_file, len(rows))
    return rows


def reconcile(es: EsHttpClient, indexes: List[str], query: Dict[str, Any],
              rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """
    与 ES _count 对账，数量对不上直接抛错。

    导出类脚本最容易的失败方式是「少了一批却看起来跑成功了」，所以这里不是可选步骤。
    """
    exported = Counter(row['index_name'] for row in rows)
    report: Dict[str, Dict[str, int]] = {}
    mismatched = []
    for index in indexes:
        expected = es.count(index, query)
        actual = exported.get(index, 0)
        report[index] = {'es_count': expected, 'exported': actual}
        if expected != actual:
            mismatched.append(f'{index}: ES {expected} != 导出 {actual}')
    if mismatched:
        raise RuntimeError('行数对账失败：' + '；'.join(mismatched))
    return report


def verify_excel_rows(excel_file: str, expected: int) -> int:
    """
    复核 xlsx 里真实写进去了多少数据行。

    trans_es_data_to_excel 对单行异常是 log + continue，行会被静默丢掉，
    单看日志很难发现，所以写完必须回读一次。
    """
    from openpyxl import load_workbook

    wb = load_workbook(excel_file, read_only=True)
    try:
        actual = max(wb.active.max_row - 1, 0)  # 减去表头
    finally:
        wb.close()
    if actual != expected:
        raise RuntimeError(f'Excel 行数对账失败：期望 {expected}，实际写入 {actual}')
    return actual


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """按 index_name x (data_type, from_type_norm) 统计，供人工与 ES 聚合逐格核对。"""
    summary: Dict[str, Dict[str, int]] = {}
    for row in rows:
        key = f"{row.get('data_type') or '-'}/{row['from_type_norm']}"
        summary.setdefault(row['index_name'], Counter())[key] += 1
    return {k: dict(v) for k, v in summary.items()}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='按来源类型导出有效 QA 到 Excel')
    p.add_argument('--es-config', default=DEFAULT_ES_CONFIG, help='ES 连接配置')
    p.add_argument('--indexes', default=','.join(DEFAULT_INDEXES), help='索引名，逗号分隔')
    p.add_argument('--from-type-norm', default=','.join(DEFAULT_FROM_TYPE_NORMS),
                   help='from_type_norm 取值，逗号分隔；all 表示不限制')
    p.add_argument('--data-type', default='qa',
                   help='data_type，逗号分隔；all 表示不限制（qa + segment 全导），默认只导 qa')
    p.add_argument('--min-audit-result', type=int, default=1,
                   help='audit_result 下限（含），默认 1，即「审核通过」')
    p.add_argument('--include-deleted', action='store_true', help='连 del_flag=1 的软删数据一起导')
    p.add_argument('--missing-fields', default='',
                   help='只导「缺这些字段里任意一个」的文档，逗号分隔（盘点脏数据用，'
                        '如 dataset）。传了它就不再按 audit_result 下限过滤')
    p.add_argument('--default-category', default=DEFAULT_CATEGORY,
                   help='完全没有类目信息的文档填什么，默认「%(default)s」')
    p.add_argument('--columns', default=None,
                   help=f'xlsx 要哪几列，逗号分隔（按传入顺序）；默认全量 {",".join(HEADERS)}。'
                        'JSONL 不受影响，永远是全量字段')
    p.add_argument('--output-dir', required=True, help='产物目录')
    p.add_argument('--output-name', default=None, help='产物文件名前缀，默认取 output-dir 目录名')
    p.add_argument('--page-size', type=int, default=1000, help='search_after 每页大小')
    p.add_argument('--limit', type=int, default=None, help='每个索引最多导多少条（抽样用）')
    return p.parse_args(argv)


def main(argv=None):
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    args = parse_args(argv)

    indexes = [x.strip() for x in args.indexes.split(',') if x.strip()]
    from_type_norms = ([] if args.from_type_norm.strip().lower() == 'all'
                       else [x.strip() for x in args.from_type_norm.split(',') if x.strip()])
    missing_fields = [x.strip() for x in args.missing_fields.split(',') if x.strip()]
    query = build_export_query(from_type_norms, args.min_audit_result,
                               args.data_type, args.include_deleted,
                               missing_fields=missing_fields)
    logging.info('查询条件: %s', json.dumps(query, ensure_ascii=False))

    os.makedirs(args.output_dir, exist_ok=True)
    name = args.output_name or os.path.basename(os.path.normpath(args.output_dir))
    rows_file = os.path.join(args.output_dir, f'{name}_rows.jsonl')
    excel_file = os.path.join(args.output_dir, f'{name}.xlsx')

    es = EsHttpClient.from_config(args.es_config)
    rows = export_rows(es, indexes, query, rows_file,
                       page_size=args.page_size, limit=args.limit,
                       default_category=args.default_category)

    if args.limit is None:
        report = reconcile(es, indexes, query, rows)
        logging.info('行数对账通过: %s', json.dumps(report, ensure_ascii=False))
    else:
        logging.warning('指定了 --limit，跳过行数对账')

    headers = select_headers(args.columns)
    if headers != HEADERS:
        logging.info('xlsx 只出这几列: %s', ','.join(headers))
    trans_es_data_to_excel(rows_file, excel_file, headers=headers)
    verify_excel_rows(excel_file, len(rows))

    summary = summarize(rows)
    logging.info('分布: %s', json.dumps(summary, ensure_ascii=False))
    logging.info('导出完成，共 %d 条 -> %s', len(rows), excel_file)
    return 0


if __name__ == '__main__':
    sys.exit(main())
