#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
通用知识质量后处理。

把 Payoneer 一次性脚本验证有效的策略（repair_self_contained_rows.py）通用化，
解决两类高频问题，且**不硬编码任何具体客户**：

1. 悬空指代：标题/内容以「第一期 / 本次 / 此次 / 该活动 / 该服务 / 该合作 / 该平台 /
   该计划 / 该课程」等开头，脱离原文标题就无法理解。
2. 栏目式泛标题：标题只写「活动概述与目标 / 适合对象 / 推广内容 / 服务内容 / 详情 /
   核心优势」等栏目名，缺少业务主体。

策略：用 from_file_name（或业务上下文给出的实体词）推导一个稳定的“业务主体”，把泛标题
和悬空内容补成自包含表述；无法补全的进入 needs_review。同时拒绝 boilerplate（版权、隐私、
关注公众号、阅读原文等）。所有修改都进入 report，不做静默修改。
"""

import re
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

# 栏目式泛标题词（短标题里出现且没有具体主体时视为泛标题）
GENERIC_TITLE_WORDS = [
    "概述", "目标", "背景", "介绍", "优势", "支持", "服务内容", "服务", "流程", "步骤",
    "要求", "条件", "内容", "方式", "详情", "安排", "对象", "适合对象", "场景", "权益",
    "机制", "能力", "功能", "规划", "建议", "指引", "说明", "机会", "挑战", "解决方案",
    "适用范围", "客户支持", "后续支持", "核心优势", "核心问题", "核心能力", "推广内容",
    "活动概述", "活动内容", "活动安排", "参与方式", "报名方式",
]

# 悬空指代前缀（标题/内容以此开头时缺少主体）
DANGLING_PREFIXES = [
    "本次活动", "本次", "此次合作", "此次活动", "此次", "该活动", "该服务", "该合作",
    "该平台", "该计划", "该课程", "该项目", "该产品", "本期", "本届", "本场", "本计划",
    "该方案", "该政策",
]

# 标题里出现“第N期/第N届/第N场”但缺少活动主体 → 悬空
_ORDINAL_RE = re.compile(r"第[一二三四五六七八九十0-9]+(期|届|场|讲|课|节)")

# boilerplate：命中即拒绝
BOILERPLATE_PATTERNS = [
    "欢迎点击上方", "关注我们", "关注公众号", "扫码关注", "点赞", "在看", "阅读原文",
    "免责声明", "隐私政策", "隐私声明", "版权所有", "版权声明", "Copyright", "Cookies",
    "cookie", "本文内容不代表本号观点", "相关文章", "更多精彩", "长按识别", "转发分享",
]

# 内容里以这些泛词开头时，替换为“主体 + 泛词”
_CONTENT_PREFIX_REPLACE = [
    "活动采用", "活动包含", "活动时间", "活动内容", "计划提供", "课程涵盖", "服务支持",
    "本服务", "该服务", "该活动", "该合作", "本次活动", "此次合作",
]


def _get(row: Dict[str, Any], field: str) -> str:
    return (row.get(field) or "") if isinstance(row, dict) else ""


def source_subject(source: str) -> str:
    """从来源文件名/标题推导一个稳定、较短的业务主体。"""
    cleaned = (source or "").replace("丨", "：").replace("|", "：").strip()
    if not cleaned:
        return ""
    for separator in ["，", ",", "！", "!", "？", "?", "：", ":", "—", "－", "、"]:
        if separator in cleaned:
            candidate = cleaned.split(separator, 1)[0].strip()
            if len(candidate) >= 6:
                return candidate
    return cleaned[:30]


def _entity_markers(business_context: Optional[dict]) -> List[str]:
    """从业务上下文收集实体词（用于判断标题是否已自包含）。"""
    markers: List[str] = []
    if not business_context:
        return markers
    em = business_context.get("entity_markers")
    if isinstance(em, list):
        markers.extend(str(x) for x in em if str(x).strip())
    client = business_context.get("client")
    if client:
        markers.append(str(client))
    # 用意图里的实体提示补充
    for intent in business_context.get("query_intents", []) or []:
        if isinstance(intent, dict):
            txt = str(intent.get("intent", ""))
            for token in re.split(r"[\s/、，,]+", txt):
                if 2 <= len(token) <= 12:
                    markers.append(token)
    return list(dict.fromkeys(m for m in markers if m))


def title_has_entity(title: str, subject: str, markers: List[str]) -> bool:
    """标题是否已包含具体主体/实体（已自包含）。"""
    if not title:
        return False
    if subject and (subject in title or title in subject):
        return True
    return any(m and m in title for m in markers)


def is_generic_heading(title: str, subject: str, markers: List[str]) -> bool:
    """判断是否为缺少主体的栏目式泛标题。"""
    if not title:
        return False
    if title_has_entity(title, subject, markers):
        return False
    if len(title) > 22:
        return False
    return any(word in title for word in GENERIC_TITLE_WORDS)


def has_dangling_reference(text: str) -> bool:
    """文本是否以悬空指代开头，或标题含未指明主体的“第N期”。"""
    if not text:
        return False
    t = text.strip()
    for prefix in DANGLING_PREFIXES:
        if t.startswith(prefix):
            return True
    if _ORDINAL_RE.search(t):
        return True
    return False


def repair_self_contained_knowledge_rows(
    rows: List[Dict[str, Any]],
    *,
    business_context: Optional[dict] = None,
    source_title_field: str = "from_file_name",
    title_field: str = "title",
    content_field: str = "content",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """把悬空指代 / 栏目式泛标题修复成自包含表述。

    Args:
        rows: 知识行列表（dict）。
        business_context: 可选业务上下文（提供 entity_markers / client 提升判断精度）。
        source_title_field: 用作主体兜底的来源字段（默认 from_file_name）。
        title_field/content_field: 标题/内容字段名（QA 流程可传 'q'/'a'）。

    Returns:
        (repaired_rows, report)。report 含每条 changes 与 needs_review 标记。
    """
    markers = _entity_markers(business_context)
    changes: List[Dict[str, Any]] = []
    needs_review: List[Dict[str, Any]] = []
    repaired_rows: List[Dict[str, Any]] = []

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            repaired_rows.append(row)
            continue
        new_row = dict(row)
        before_title = _get(new_row, title_field)
        before_content = _get(new_row, content_field)
        subject = source_subject(_get(new_row, source_title_field))

        changed = False

        # 1. 栏目式泛标题 → 主体：栏目名
        title = _get(new_row, title_field)
        if subject and is_generic_heading(title, subject, markers) and not title.startswith(subject):
            new_row[title_field] = f"{subject}：{title}"
            changed = True

        # 2. 标题悬空指代 → 用主体替换前缀
        title = _get(new_row, title_field)
        if subject and not title_has_entity(title, subject, markers):
            for prefix in DANGLING_PREFIXES:
                if title.startswith(prefix):
                    new_row[title_field] = subject + title[len(prefix):]
                    changed = True
                    break

        # 3. 内容悬空前缀 → 主体 + 泛词
        content = _get(new_row, content_field)
        if subject and not content.startswith(subject):
            for prefix in _CONTENT_PREFIX_REPLACE:
                if content.startswith(prefix):
                    new_row[content_field] = subject + content[len(prefix):]
                    changed = True
                    break

        # 修复后仍悬空 / 仍是泛标题 → 标记 needs_review
        final_title = _get(new_row, title_field)
        still_bad = (
            has_dangling_reference(final_title)
            or is_generic_heading(final_title, subject, markers)
            or (not title_has_entity(final_title, subject, markers)
                and has_dangling_reference(_get(new_row, content_field)))
        )
        if still_bad:
            new_row["needs_review"] = True
            new_row["review_reason"] = "dangling_or_generic_after_repair"
            needs_review.append({
                "index": index,
                "source": _get(new_row, source_title_field),
                "title": final_title,
            })

        if changed:
            changes.append({
                "index": index,
                "source": _get(new_row, source_title_field),
                "before_title": before_title,
                "after_title": _get(new_row, title_field),
                "before_content": before_content,
                "after_content": _get(new_row, content_field),
            })

        repaired_rows.append(new_row)

    report = {
        "total": len(rows),
        "repaired_count": len(changes),
        "needs_review_count": len(needs_review),
        "changes": changes,
        "needs_review": needs_review,
    }
    return repaired_rows, report


# 图片直链：多模态阶段没 OCR 出文字时，QA 生成会直接把图片链接当答案。
# 这种行检索命中了等于没答案，必须拒掉。注意只认**图片**链接——
# 指向官网/入驻通道的普通链接是有价值的答案，不能一起杀。
_IMAGE_URL_RE = re.compile(
    r"!?\[[^\]]*\]\(\s*https?://[^)\s]+\s*\)"          # markdown 图片/链接写法
    r"|https?://[^\s)\]]+?\.(?:png|jpe?g|gif|webp|bmp|svg)(?:\?[^\s)\]]*)?"
    r"|https?://[^\s)\]]*/kgmultimodal/[^\s)\]]*",     # 多模态阶段回传的图片地址（可能不带扩展名）
    re.IGNORECASE,
)


def _is_image_only(content: str) -> bool:
    """答案除了图片链接之外没有任何文字 → 无检索价值。"""
    if not content or not _IMAGE_URL_RE.search(content):
        return False
    remainder = _IMAGE_URL_RE.sub("", content)
    remainder = re.sub(r"[\s\-•·—、,，。;；:：\|]+", "", remainder)
    return not remainder


# 「空转」答案：只是把人指向别处，本身不含信息
_VACUOUS_RE = re.compile(
    r"(请参考(原文|上文|文档|表格|下文)|详见(上文|原文|上图|表格|下文)|见上[图文表]"
    r"|如上所述|具体(请)?(咨询|见|参考)|以.{0,8}为准|请联系.{0,10}客服)"
)

# 列举分隔符：「菲律宾、马来西亚、泰国」这类枚举本身就是实质信息
_ENUM_SEP_RE = re.compile(r"[、，,;；/／]")

# 具体性关键词：数值/步骤之外，操作动词和约束词同样代表可执行信息
_CONCRETE_KEYWORD_RE = re.compile(
    r"(步骤|Step|第[一二三四五六七八九十1-9]步|流程|条件|费率|%"
    r"|点击|选择|进入|打开|填写|上传|提交|勾选|绑定|开通"
    r"|需要提供|需提供|不支持|不得|必须|仅限)"
)


def _enum_item_count(text: str) -> int:
    """按顿号/斜杠等分隔符数一下枚举了几项（只算长度≥2的项，避免标点噪音）。"""
    return len([x for x in _ENUM_SEP_RE.split(text or "") if len(x.strip()) >= 2])


def _is_too_thin(content: str) -> bool:
    """答案是否「没有实质信息」。

    **不要退回到「短就是薄」**：老实现是 `len < 40 且不含数字/URL/步骤词 → 拒`，
    等于用字数当质量代理，结果是**奖励啰嗦、惩罚精炼**：
      · `目前首站可选：菲律宾、马来西亚、泰国、越南、新加坡。`（33字，无数字）被拒
      · `入驻要求提供有限公司资质/个人独资企业资质营业执照/个体工商户执照。`（32字）被拒
    而照抄界面原文的啰嗦答案因为够长反而全过。实测同一篇文档，答案中位长度 49 字的方案
    被拒 22 条，中位 109 字的只被拒 7 条，且前者被拒的内容明显更好。

    现在的判据：
      1. 空转答案（只把人指向别处）→ 薄，不看长度；
      2. 够长（≥40字）→ 不薄；
      3. 短答案看**有没有实质信息**：数值 / URL / 步骤或操作词 / 英文专名 / ≥3 项枚举。
    """
    text = (content or "").strip()
    stripped = re.sub(r"\s+", "", text)
    if not stripped:
        return True

    # 1) 「请参考原文表格中的详细信息」这类：再长也没有自身信息
    if _VACUOUS_RE.search(text) and not re.search(r"https?://", text) and len(stripped) < 60:
        return True

    if len(stripped) >= 40:
        return False

    # 2) 短答案：只要带上任一实质信号就放行
    has_concrete = bool(
        re.search(r"\d", text)
        or re.search(r"https?://", text)
        or _CONCRETE_KEYWORD_RE.search(text)
        or re.search(r"[A-Za-z]{3,}", text)          # TikTok / VAT / FBT 这类专名
        or _enum_item_count(text) >= 3               # 枚举本身就是信息
    )
    return not has_concrete


def filter_business_quality_rows(
    rows: List[Dict[str, Any]],
    *,
    quality_profile: str = "business_task_knowledge",
    title_field: str = "title",
    content_field: str = "content",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """按业务知识质量画像过滤，拒绝 boilerplate / 单薄 / 不可自包含的行。

    Returns:
        (kept_rows, rejected_rows)。被拒行带 reject_reason 字段。
    """
    kept: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            kept.append(row)
            continue
        title = _get(row, title_field)
        content = _get(row, content_field)
        combined = f"{title}\n{content}"

        reason = None
        if any(p.lower() in combined.lower() for p in BOILERPLATE_PATTERNS):
            reason = "boilerplate"
        elif row.get("needs_review"):
            reason = "needs_review_dangling_or_generic"
        elif quality_profile == "business_task_knowledge" and _is_image_only(content):
            # 放在 _is_too_thin 之前：裸 URL 会被 _is_too_thin 当成「有具体值」而放行
            reason = "image_only_no_text"
        elif quality_profile == "business_task_knowledge" and _is_too_thin(content):
            reason = "thin_no_concrete_value"

        if reason:
            rej = dict(row)
            rej["reject_reason"] = reason
            rejected.append(rej)
        else:
            kept.append(row)

    return kept, rejected
