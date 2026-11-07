# -*- coding: utf-8 -*-
"""strip_nav_boilerplate 的离线单测：只测定位逻辑，不打网络。"""

import pytest

from kdb.integrations.data_control.strip_nav_boilerplate import find_nav_prefix_end

NAV = (
    "本网站使用 Cookie 来评估和改善网站性能。如需了解更多信息，请参阅我们的 [Cookie 政策](\n"
    "https://developer.wayfair.io/posts/cookie-policy).\n"
    "关闭\n入门\n"
    "[引言](\nhttps://developer.wayfair.io/posts/introduction)\n"
    "资源\n"
    "[常见问题解答](\nhttps://developer.wayfair.io/posts/FAQs)\n"
    "[词汇表](\nhttps://developer.wayfair.io/posts/glossary)\n"
)
BODY = "# 沙盒测试\n" + "请使用沙盒应用密钥进行 API 调用身份验证，并通过 Postman 执行端到端测试。" * 12


class TestFindNavPrefixEnd:
    def test_strips_nav_and_keeps_body(self):
        end = find_nav_prefix_end(NAV + BODY)
        assert end is not None
        assert (NAV + BODY)[end:].startswith('# 沙盒测试')
        assert '词汇表' not in (NAV + BODY)[end:]

    def test_returns_none_when_marker_absent(self):
        assert find_nav_prefix_end('一段没有导航块的正常正文。' * 20) is None

    def test_returns_none_when_prefix_too_large_ratio(self):
        # 正文很短、导航占比过半 -> 不可信，宁可跳过也不瞎切
        assert find_nav_prefix_end(NAV + '短正文') is None

    def test_returns_none_when_prefix_exceeds_char_cap(self):
        big_nav = ('填充' * 900) + '\n词汇表\nhttps://x.test/g\n'
        assert find_nav_prefix_end(big_nav + BODY, max_prefix_chars=1000) is None

    def test_returns_none_when_remaining_body_too_short(self):
        assert find_nav_prefix_end(NAV + '很短') is None

    def test_uses_last_marker_occurrence(self):
        """正文里再次提到"词汇表"时，rfind 会落到正文，安全阀必须拦住。"""
        content = NAV + BODY + '\n更多术语请见词汇表\n' + BODY
        end = find_nav_prefix_end(content)
        # 要么正确定位到导航块结尾，要么返回 None，绝不能切掉正文开头
        assert end is None or content[end:].startswith('# 沙盒测试')

    def test_empty_input(self):
        assert find_nav_prefix_end('') is None
        assert find_nav_prefix_end(None) is None


class TestGlossaryPageRegression:
    """词汇表页面的正文标题就是 `**词汇表**`，不能被当成导航尾巴切掉。"""

    CONTENT = NAV + "**词汇表**\n* * *\n**提前发货通知**\n**（ASN）：**\n" + "供应商可通过 API 发送 ASN。" * 20

    def test_keeps_glossary_body_heading(self):
        end = find_nav_prefix_end(self.CONTENT)
        assert end is not None
        assert self.CONTENT[end:].startswith('**词汇表**')

    def test_text_marker_would_have_cut_it(self):
        """反证：用文字 marker 就会切掉正文标题——这正是改用 URL 的原因。"""
        end = find_nav_prefix_end(self.CONTENT, tail_markers=['**词汇表**'])
        assert end is not None
        assert not self.CONTENT[end:].startswith('**词汇表**')
