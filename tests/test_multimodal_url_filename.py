"""检索返回时 [multimodal_prefix] 占位符渲染成真实 URL 并带上 filename 参数。

见 function_schema/search_index_data_interface.render_multimodal_urls.md
"""
from knowledge_interface_tools.search_index_data_interface import SearchDataInterface


PREFIX = 'https://file.marsmind.cc/'


def _render(doc):
    """不连 ES，直接在裸实例上跑渲染逻辑。"""
    interface = SearchDataInterface.__new__(SearchDataInterface)
    interface.multimodal_prefix = PREFIX
    interface.render_multimodal_urls(doc)
    return doc.get('content')


def test_internal_path_gets_filename_param():
    doc = {
        'content': '这是一个表格\n[multimodal_prefix]boot-admin/mercado/20260807/2085635537046671362.xls',
        'multimodal_contents': [
            {'type': 'text', 'content': '这是一个表格'},
            {
                'type': 'file',
                'path': 'boot-admin/mercado/20260807/2085635537046671362.xls',
                'fileName': 'test_name.xls',
                'url': '',
            },
        ],
    }
    assert _render(doc) == (
        '这是一个表格\n'
        'https://file.marsmind.cc/boot-admin/mercado/20260807/2085635537046671362.xls'
        '?filename=test_name.xls'
    )


def test_external_url_untouched():
    """外链入库时就没有占位符，渲染后必须原样保留，不能被塞 filename。"""
    doc = {
        'content': '见附件\nhttps://external.com/doc.pdf?token=abc',
        'multimodal_contents': [
            {'type': 'file', 'path': None, 'fileName': 'doc.pdf', 'url': 'https://external.com/doc.pdf?token=abc'},
        ],
    }
    assert _render(doc) == '见附件\nhttps://external.com/doc.pdf?token=abc'


def test_missing_filename_falls_back_to_prefix_only():
    doc = {
        'content': '[multimodal_prefix]kgmultimodal/knowledge/aaa.png',
        'multimodal_contents': [
            {'type': 'image', 'path': 'kgmultimodal/knowledge/aaa.png', 'fileName': '', 'url': ''},
        ],
    }
    assert _render(doc) == 'https://file.marsmind.cc/kgmultimodal/knowledge/aaa.png'


def test_doc_without_multimodal_contents_falls_back_to_prefix_only():
    doc = {'content': '[multimodal_prefix]kgmultimodal/knowledge/bbb.png'}
    assert _render(doc) == 'https://file.marsmind.cc/kgmultimodal/knowledge/bbb.png'


def test_path_prefix_collision_replaces_longest_first():
    """a/b.png 是 a/b.png.thumb 的前缀，先替短的会把长的截断。"""
    doc = {
        'content': '[multimodal_prefix]a/b.png\n[multimodal_prefix]a/b.png.thumb',
        'multimodal_contents': [
            {'type': 'image', 'path': 'a/b.png', 'fileName': '原图.png'},
            {'type': 'image', 'path': 'a/b.png.thumb', 'fileName': 'thumb.png'},
        ],
    }
    assert _render(doc) == (
        'https://file.marsmind.cc/a/b.png?filename=%E5%8E%9F%E5%9B%BE.png\n'
        'https://file.marsmind.cc/a/b.png.thumb?filename=thumb.png'
    )


def test_render_is_idempotent():
    """多 query 检索的回退路径会重复渲染同一条 doc，第二次必须是空操作。"""
    doc = {
        'content': '[multimodal_prefix]boot-admin/x/1.xls',
        'multimodal_contents': [{'type': 'file', 'path': 'boot-admin/x/1.xls', 'fileName': 'a.xls'}],
    }
    once = _render(doc)
    assert _render(doc) == once


def test_non_string_content_is_left_alone():
    doc = {'content': None, 'multimodal_contents': []}
    assert _render(doc) is None
