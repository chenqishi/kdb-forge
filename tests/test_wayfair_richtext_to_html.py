# -*- coding: utf-8 -*-
"""wayfair_developer_portal_fetch 的离线单测：URL 解析 + rich text 渲染。

网络部分（内容 BFF 取数）靠实跑校验，不在这里造 mock。
"""

import pytest

from knowledge_crawler_tool.web_crawl.wayfair_developer_portal_fetch import (
    _is_full_html_document,
    build_html_document,
    parse_post_url,
    richtext_to_html,
)


def text(value, marks=None):
    return {
        'nodeType': 'text',
        'value': value,
        'marks': [{'type': m} for m in (marks or [])],
        'data': {},
    }


def document(*nodes):
    return {'nodeType': 'document', 'data': {}, 'content': list(nodes)}


def block(node_type, *children, **data):
    return {'nodeType': node_type, 'data': data or {}, 'content': list(children)}


class TestParsePostUrl:
    def test_post_url(self):
        assert parse_post_url('https://developer.wayfair.io/posts/introduction') == {
            'kind': 'post',
            'slug': 'introduction',
            'url': 'https://developer.wayfair.io/posts/introduction',
        }

    def test_reference_url(self):
        url = ('https://developer.wayfair.io/posts/docs/inventory-api'
               '/reference/GraphQL/v1.0.0')
        parsed = parse_post_url(url)
        assert parsed['kind'] == 'reference'
        assert parsed['api_id'] == 'inventory-api'
        assert parsed['api_protocol'] == 'GraphQL'
        assert parsed['version'] == 'v1.0.0'

    def test_slug_is_case_sensitive(self):
        assert parse_post_url(
            'https://developer.wayfair.io/posts/Cg-Orders-Guide')['slug'] == 'Cg-Orders-Guide'

    def test_rejects_non_post_url(self):
        with pytest.raises(ValueError):
            parse_post_url('https://developer.wayfair.io/about')

    def test_rejects_incomplete_reference_url(self):
        with pytest.raises(ValueError):
            parse_post_url('https://developer.wayfair.io/posts/docs/inventory-api')


class TestRichTextToHtml:
    def test_headings_and_paragraph(self):
        rendered = richtext_to_html(document(
            block('heading-2', text('接入准备')),
            block('paragraph', text('请先申请 Client ID。')),
            block('hr'),
        ))
        assert '<h2>接入准备</h2>' in rendered
        assert '<p>请先申请 Client ID。</p>' in rendered
        assert '<hr />' in rendered

    def test_nested_list(self):
        rendered = richtext_to_html(document(
            block('unordered-list',
                  block('list-item', block('paragraph', text('第一项'))),
                  block('list-item',
                        block('ordered-list',
                              block('list-item', block('paragraph', text('子项')))))),
        ))
        assert rendered == (
            '<ul><li><p>第一项</p></li>'
            '<li><ol><li><p>子项</p></li></ol></li></ul>'
        )

    def test_table(self):
        rendered = richtext_to_html(document(
            block('table',
                  block('table-row',
                        block('table-header-cell', block('paragraph', text('字段'))),
                        block('table-cell', block('paragraph', text('说明'))))),
        ))
        assert rendered == (
            '<table><tr><th><p>字段</p></th><td><p>说明</p></td></tr></table>'
        )

    def test_hyperlink(self):
        rendered = richtext_to_html(document(
            block('paragraph',
                  text('详见 '),
                  block('hyperlink', text('文档'), uri='https://a.test/x?a=1&b=2')),
        ))
        assert '<a href="https://a.test/x?a=1&amp;b=2">文档</a>' in rendered

    def test_marks_all_four(self):
        rendered = richtext_to_html(document(
            block('paragraph',
                  text('B', ['bold']),
                  text('I', ['italic']),
                  text('U', ['underline']),
                  text('C', ['code'])),
        ))
        assert rendered == (
            '<p><strong>B</strong><em>I</em><u>U</u><code>C</code></p>'
        )

    def test_multiple_marks_nest_in_stable_order(self):
        rendered = richtext_to_html(document(
            block('paragraph', text('x', ['bold', 'code'])),
        ))
        assert rendered == '<p><strong><code>x</code></strong></p>'

    def test_text_is_escaped(self):
        rendered = richtext_to_html(document(
            block('paragraph', text('<script>alert("x")</script> & more')),
        ))
        assert '<script>' not in rendered
        assert '&lt;script&gt;' in rendered
        assert '&amp; more' in rendered

    def test_empty_body_returns_empty_string(self):
        assert richtext_to_html({}) == ''
        assert richtext_to_html(None) == ''


class TestEmbeddedAsset:
    ASSET_NODE = {
        'nodeType': 'embedded-asset-block',
        'content': [],
        'data': {'target': {'sys': {'id': 'asset-1'}}},
    }

    def _render(self, content_type, url='https://cdn.test/a.bin'):
        return richtext_to_html(
            document(self.ASSET_NODE),
            assets=[{'sys': {'id': 'asset-1'}, 'contentType': content_type, 'url': url}],
        )

    def test_image(self):
        assert self._render('image/png', 'https://cdn.test/a.png') == (
            '<img src="https://cdn.test/a.png" />')

    def test_video(self):
        rendered = self._render('video/mp4', 'https://cdn.test/a.mp4')
        assert rendered == (
            '<video controls>'
            '<source src="https://cdn.test/a.mp4" type="video/mp4" />'
            '</video>')

    def test_other_content_type_falls_back_to_link(self):
        rendered = self._render('application/pdf', 'https://cdn.test/a.pdf')
        assert rendered == '<a href="https://cdn.test/a.pdf">https://cdn.test/a.pdf</a>'

    def test_missing_asset_degrades_without_raising(self):
        rendered = richtext_to_html(document(self.ASSET_NODE), assets=[])
        assert rendered == '<!-- missing asset: asset-1 -->'


class TestUnknownNode:
    def test_unknown_node_keeps_children(self):
        rendered = richtext_to_html(document(
            block('embedded-entry-block', block('paragraph', text('重要内容'))),
        ))
        assert 'data-unknown-node="embedded-entry-block"' in rendered
        # 关键：内容不能被静默丢掉
        assert '重要内容' in rendered


class TestIsFullHtmlDocument:
    def test_doctype_and_html_are_full_documents(self):
        assert _is_full_html_document('<!DOCTYPE html>\n<html><body>x</body></html>')
        assert _is_full_html_document('<html lang="zh-CN"><body>x</body></html>')

    def test_leading_whitespace_and_comment_ignored(self):
        assert _is_full_html_document('\n  <!-- built by spectaql -->\n<!doctype html><html>')

    def test_style_fragment_is_not_a_full_document(self):
        assert not _is_full_html_document('<style>body { margin: 0 }</style><div>x</div>')

    def test_inline_body_in_code_sample_does_not_count(self):
        # SpectaQL 会在代码示例里内嵌 <html><head></head><body><pre>，实测 orders-api 有 52 处。
        # 子串判断会误判成完整文档 -> 不加包装 -> html.parser 把正文全归到 head -> 下游整页丢内容
        fragment = (
            '<style>.doc{}</style><div class="doc-copy"><p>訂單管理API</p></div>'
            '<div><html><head></head><body><pre><code>{"a":1}</code></pre></body></html></div>'
        )
        assert '<body' in fragment
        assert not _is_full_html_document(fragment)


class TestBuildHtmlDocument:
    def test_has_body_and_traceability(self):
        rendered = build_html_document(
            '常见问题解答', 'https://developer.wayfair.io/posts/FAQs',
            'zh-CN', '<p>正文</p>', fetched_at='2026-08-07T13:00:00')
        assert '<body>' in rendered and '</body>' in rendered
        assert '<html lang="zh-CN">' in rendered
        assert '<title>常见问题解答</title>' in rendered
        assert '<h1>常见问题解答</h1>' in rendered
        assert 'https://developer.wayfair.io/posts/FAQs' in rendered
        assert '2026-08-07T13:00:00' in rendered
        assert '<p>正文</p>' in rendered

    def test_title_is_escaped(self):
        rendered = build_html_document(
            'a<b>c', 'https://x.test/p', 'zh-CN', '', fetched_at='t')
        assert '<title>a&lt;b&gt;c</title>' in rendered
