from openpyxl import load_workbook
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
import json
import logging

_EXCEL_COLUMN_ALIASES: Dict[str, List[str]] = {
    'title':             ['title', 'question', '问题', '标题', '问法', 'Question', 'q', 'Q',
                          '質問', 'タイトル', '設問'],
    'content':           ['content', 'answer', '答案', '内容', '回复', 'Answer', 'a', 'A',
                          '回答', '答え'],
    'indexes':           ['indexes', 'index', 'keyword', '检索词', '关键词', 'キーワード', '索引'],
    'synonyms_title':    ['synonyms_title', 'synonyms', '相似问', '同义问'],
    'supply_info_query': ['supply_info_query', '补充查询', '扩展查询'],
    'platform':          ['platform', '平台'],
    'category':          ['category', '分类'],
    'from_scene':        ['from_scene', '场景'],
    'data_type':         ['data_type', '数据类型'],
    'from_type':         ['from_type', '来源类型'],
    'audit_result':      ['audit_result', '审核结果'],
    'image_path':        ['image_path', '图片路径'],
    'image_data':        ['image_data', '图片数据'],
}


_STANDARD_QA_HEADER_PAIRS = (
    frozenset({'title', 'content'}),
    frozenset({'question', 'answer'}),
)


def map_excel_columns(headers: List) -> Optional[Dict[str, int]]:
    """
    Map an Excel header row to canonical field names.

    Returns {canonical_name: col_index} when both title and content can be resolved,
    or None when the mapping is incomplete (caller should fall back to unstructured parser).
    """
    alias_lookup: Dict[str, str] = {}
    for canonical, aliases in _EXCEL_COLUMN_ALIASES.items():
        for alias in aliases:
            alias_lookup[str(alias).strip().lower()] = canonical

    mapping: Dict[str, int] = {}
    for idx, header in enumerate(headers):
        if header is None:
            continue
        key = str(header).strip().lower()
        canonical = alias_lookup.get(key)
        if canonical and canonical not in mapping:
            mapping[canonical] = idx

    if 'title' not in mapping or 'content' not in mapping:
        return None
    return mapping


def _canonical_excel_field(header: Any, zero_based_idx: int, canonical_by_idx: Dict[int, str]) -> str:
    """Return a canonical field name when the sheet was confidently mapped."""
    return canonical_by_idx.get(zero_based_idx, header)


def classify_excel_upload(excel_file: str, sample_row_limit: int = 5) -> Dict[str, Any]:
    """
    判定上传 Excel 应走哪条处理链路（deterministic，不调用 LLM）。

    读取首个含表头的 sheet 的表头与若干样本行，返回路由判定：
      - standard_qa：表头已含标准 title/content 或 Question/Answer 成对字面量。
      - mapped_qa：表头可经 map_excel_columns 解析出 title + content（含中文别名）。
      - unstructured_excel：无法映射，走非结构化文档知识流程。

    Returns:
        Dict[str, Any]: {
            "mode": "standard_qa" | "mapped_qa" | "unstructured_excel",
            "mapping": Optional[Dict[str, int]],   # canonical_name -> 0-based col idx
            "reason": str,
            "confidence": float,                   # 0~1
            "headers": List[Any],
            "sheet_name": Optional[str],
            "sample_rows": List[List[Any]],
        }
    """
    result: Dict[str, Any] = {
        "mode": "unstructured_excel",
        "mapping": None,
        "reason": "",
        "confidence": 0.0,
        "headers": [],
        "sheet_name": None,
        "sample_rows": [],
    }

    try:
        wb = load_workbook(excel_file, read_only=True, data_only=True)
    except Exception as exc:
        # 无法读取（损坏/格式异常）时，安全降级到非结构化处理，绝不抛错中断路由。
        result["reason"] = f"无法读取 Excel，降级为非结构化处理: {exc}"
        result["confidence"] = 0.3
        return result

    try:
        headers: List[Any] = []
        sheet_name = None
        sample_rows: List[List[Any]] = []

        # 找到第一个含非空表头的 sheet
        for name in wb.sheetnames:
            ws = wb[name]
            row_iter = ws.iter_rows(values_only=True)
            first_row = next(row_iter, None)
            if first_row is None:
                continue
            candidate_headers = list(first_row)
            if not any(h is not None and str(h).strip() for h in candidate_headers):
                continue
            headers = candidate_headers
            sheet_name = name
            for sample in row_iter:
                if len(sample_rows) >= sample_row_limit:
                    break
                sample_rows.append(list(sample))
            break
    finally:
        wb.close()

    result["headers"] = headers
    result["sheet_name"] = sheet_name
    result["sample_rows"] = sample_rows

    if not headers:
        result["reason"] = "未找到含表头的 sheet，降级为非结构化处理"
        result["confidence"] = 0.3
        return result

    normalized = {str(h).strip().lower() for h in headers if h is not None and str(h).strip()}
    mapping = map_excel_columns(headers)
    result["mapping"] = mapping

    if any(pair.issubset(normalized) for pair in _STANDARD_QA_HEADER_PAIRS):
        result["mode"] = "standard_qa"
        result["confidence"] = 0.95
        result["reason"] = "表头包含标准 title/content 或 Question/Answer 字段对"
        return result

    if mapping:
        # 用样本行的 title/content 填充率辅助置信度（不改变判定结果）。
        title_idx = mapping.get('title')
        content_idx = mapping.get('content')
        filled = 0
        for row in sample_rows:
            t = row[title_idx] if title_idx is not None and title_idx < len(row) else None
            c = row[content_idx] if content_idx is not None and content_idx < len(row) else None
            if t is not None and str(t).strip() and c is not None and str(c).strip():
                filled += 1
        ratio = (filled / len(sample_rows)) if sample_rows else 1.0
        result["mode"] = "mapped_qa"
        result["confidence"] = round(min(0.9, 0.6 + 0.3 * ratio), 3)
        result["reason"] = (
            f"表头可映射为 QA 表 (title/content 别名命中)，样本行填充率={ratio:.2f}"
        )
        return result

    result["mode"] = "unstructured_excel"
    result["confidence"] = 0.6
    result["reason"] = "表头无法解析出 title+content，走非结构化文档知识流程"
    return result


def excel_to_qa_json(excel_file: str):
    """
    将带平台格式的excel数据转换为qa json格式
    
    Args:
        excel_file: Excel文件路径
    
    输出格式示例:
    {
        "title": "问题内容",
        "content": "答案内容",
        "document_name": "sheet名称",
        "platform": "平台名称"
    }
    """
    try:
        wb = load_workbook(excel_file, read_only=False, data_only=True)  # data_only=True 会读取公式的结果值

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            # 获取表头
            headers = [cell.value for cell in next(ws.rows)]

            # 检查必要的列是否存在
            platform_idx = headers.index("平台") if "平台" in headers else None
            question_idx = headers.index("问题")
            answer_idx = headers.index("答案")

            # 遍历数据行
            for row in list(ws.rows)[1:]:  # 跳过表头
                trans_info = {
                    "title": row[question_idx].value,
                    "content": row[answer_idx].value,
                    "document_name": sheet_name
                }

                if platform_idx is not None:
                    platform = row[platform_idx].value
                    if platform:  # 只在平台值非空时添加
                        trans_info["platform"] = platform

                print(json.dumps(trans_info, ensure_ascii=False))

    except Exception as e:
        logging.error(f"处理Excel文件时发生错误: {str(e)}")
        raise
