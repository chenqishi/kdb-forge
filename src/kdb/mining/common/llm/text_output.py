import re

_THINK_RE = re.compile(r'<think>[\s\S]*?</think>')


def clear_think(result: str) -> str:
    """去掉 <think></think> 及其中内容，对应原 Dify 流的代码节点"""
    if not result:
        return ''
    if '<think>' in result and '</think>' in result:
        result = _THINK_RE.sub('', result)
    return result.strip()
