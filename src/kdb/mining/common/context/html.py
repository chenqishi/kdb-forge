import json
import logging

def load_html_business_context(business_context_path):
    """读取业务上下文 JSON。未启用或读取失败时返回 None，保持旧流程行为。"""
    if not business_context_path:
        return None
    try:
        with open(business_context_path, 'r', encoding='utf-8') as f:
            ctx = json.load(f)
        if not ctx or not ctx.get('enabled') or not ctx.get('context_text'):
            return None
        return ctx
    except Exception as e:
        logging.warning(f'读取 HTML 业务上下文失败，忽略: {e}')
        return None


def _trim_context_text(text, max_chars=4000):
    """限制上下文长度，避免挤占网页正文窗口。"""
    if not text:
        return ''
    text = str(text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + '\n[业务上下文因长度限制截断]'


def build_html_context_prefix(business_context, quality_profile=''):
    """构造给 Dify 的抽取约束前缀；该文本只作约束，不作为网页事实。"""
    if not business_context:
        return ''
    context_text = _trim_context_text(business_context.get('context_text', ''))
    boundaries = business_context.get('business_boundaries') or {}
    keep = '、'.join(boundaries.get('keep') or [])
    reject = '、'.join(boundaries.get('reject') or [])
    profile = quality_profile or 'business_task_knowledge'
    return (
        "【抽取约束，禁止作为知识内容输出】\n"
        f"{context_text}\n"
        f"质量画像：{profile}\n"
        f"优先保留：{keep}\n"
        f"优先拒绝：{reject}\n"
        "只基于下面网页正文生成知识；不要把本段约束或用户 query 样例当作答案事实。\n"
        "【网页正文】\n"
    )


def contextualize_html_text(formatted_text, business_context=None, quality_profile=''):
    """为 HTML 正文附加业务抽取约束；无上下文时原样返回。"""
    prefix = build_html_context_prefix(business_context, quality_profile)
    if not prefix:
        return formatted_text
    return prefix + (formatted_text or '')
