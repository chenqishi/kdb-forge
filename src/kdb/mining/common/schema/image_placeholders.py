import re

IMAGE_PLACEHOLDER_RE = re.compile(r'[\[【]图(\d+)[\]】]')


_MULTIMODAL_URL_RE = re.compile(
    r'!?\[[^\]]*\]\(\s*https?://[^)\s]*kgmultimodal[^)\s]*\s*\)'
    r'|https?://[^\s)\]"\'>]*kgmultimodal[^\s)\]"\'>]*'
)


def _placeholder_for(url, placeholder_map):
    """同一张图始终拿到同一个编号。

    编号必须按 URL 建一次映射：`merge_segment_content` 在一次生成里会被调用多次
    （整篇一次、分段各一次），如果每次调用都重新计数，同一张图会拿到不同编号，
    模型看到 [图76] 这种大数字还容易把占位符本身当成提问对象。
    """
    for tag, mapped in placeholder_map.items():
        if mapped == url:
            return tag
    tag = '[图%d]' % (len(placeholder_map) + 1)
    placeholder_map[tag] = url
    return tag


def restore_image_placeholders(text, placeholder_map):
    """把答案里的 [图N] 还原成 markdown 图片。

    URL 从映射表取，**不经过模型**——模型只需要抄对 4 个字符的标记。
    实测让模型直接抄 40 字符的图片 URL 会抄错（把日期段重复三遍、多个 URL 粘连），
    改成占位符后链接正确率 100%。标记对不上时返回空串，最坏情况是少一张图，不会产生坏链。
    """
    if not text or not placeholder_map:
        return text or ''

    def _sub(match):
        url = placeholder_map.get('[图%s]' % match.group(1))
        return '![嵌入图片](%s "Flowchart")' % url if url else ''

    return IMAGE_PLACEHOLDER_RE.sub(_sub, text)


def strip_image_placeholders(text):
    """问题里不该出现占位符，直接去掉。"""
    return IMAGE_PLACEHOLDER_RE.sub('', text or '').strip()


def strip_hallucinated_image_urls(text):
    """去掉答案里模型自己编的图床 URL。

    占位符模式下模型根本看不到图片地址，写出来的必然是幻觉。而且实测它会**退化成复读**
    （`/20260807/20260807/...` 重复几百次），这一条就能吃光后续质检调用的 token 预算，
    导致整批 QA 拿不到质量标签、全部降级——一次实跑里 42 条只解析出 1 条。
    真正的配图由 `restore_image_placeholders` 按映射还原，不依赖模型写地址。
    """
    if not text:
        return text or ''
    cleaned = _MULTIMODAL_URL_RE.sub('', text)
    return re.sub(r'\n{3,}', '\n\n', cleaned).strip()
