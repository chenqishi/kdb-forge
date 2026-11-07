from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""登录态在线文档爬取器的行为测试（全部离线，不开浏览器、不打网络）。

浏览器交互本身靠真实跑验证，这里只覆盖会静默出错的纯逻辑：
  1. 虚拟滚动的多轮采集必须按文档顺序去重合并，漏一轮或重一轮都看不出来
  2. 容器块不能把后代块的图片再输出一遍（否则正文里全是重复图）
  3. 腾讯文档的 protobuf 正文后面紧跟着 Word 样式表，必须在正确的位置截断
  4. 目录名安全化不能让站点名逃出 root
"""
import base64
import json
import os
import sys

import pytest

ROOT = str(_PROJECT_ROOT)

from kdb.mining.crawlers.web_crawl import login_doc_crawler as crawler


MANIFEST = {
    'root': 'data/payoneer_olive',
    'docs': [
        {'platform': 'TikTok Shop', 'site': '英国', 'doc_type': 'lark', 'url': 'https://x/docx/a'},
        {'platform': 'Noon', 'site': '通用', 'doc_type': 'tencent', 'url': 'https://docs.qq.com/doc/B'},
    ],
}


def _write_manifest(tmp_path, payload):
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return str(path)


# --------------------------------------------------------------------------- 清单

def test_load_url_manifest_reads_root_and_docs(tmp_path):
    root, items = crawler.load_url_manifest(_write_manifest(tmp_path, MANIFEST))
    assert root == 'data/payoneer_olive'
    assert [i['site'] for i in items] == ['英国', '通用']
    assert items[0]['doc_type'] == 'lark'


def test_load_url_manifest_rejects_missing_field(tmp_path):
    bad = {'docs': [{'platform': 'Noon', 'site': '通用', 'doc_type': 'tencent'}]}
    with pytest.raises(ValueError) as err:
        crawler.load_url_manifest(_write_manifest(tmp_path, bad))
    assert 'url' in str(err.value)


def test_load_url_manifest_rejects_unknown_doc_type(tmp_path):
    bad = {'docs': [dict(MANIFEST['docs'][0], doc_type='notion')]}
    with pytest.raises(ValueError):
        crawler.load_url_manifest(_write_manifest(tmp_path, bad))


# --------------------------------------------------------------------------- 目录

def test_build_doc_dir_keeps_space_and_cjk(tmp_path):
    doc_dir = crawler.build_doc_dir(str(tmp_path), 'TikTok Shop', '美国ACCU')
    assert doc_dir.endswith(os.path.join('TikTok Shop', '美国ACCU'))


def test_build_doc_dir_keeps_brackets_and_slash_platform(tmp_path):
    # 线上类目里确实有 Falabella(Linio) 和 Fnac/Darty，前者要原样保留，后者的斜杠必须被替掉
    assert crawler.safe_dir_name('Falabella(Linio)') == 'Falabella(Linio)'
    assert '/' not in crawler.safe_dir_name('Fnac/Darty')


def test_build_doc_dir_cannot_escape_root(tmp_path):
    """站点名里带 ../ 时要被安全化成普通目录名，绝不能落到 root 外面去。"""
    doc_dir = crawler.build_doc_dir(str(tmp_path), '..', '../../etc')
    assert os.path.abspath(doc_dir).startswith(os.path.abspath(str(tmp_path)) + os.sep)
    # 只允许多出 <平台>/<站点> 两层，路径分隔符不能被站点名带进来
    rel = os.path.relpath(doc_dir, str(tmp_path))
    assert len(rel.split(os.sep)) == 2


# --------------------------------------------------------------------------- 虚拟滚动合并

def _blk(key, top, md='', images=None):
    return {'key': key, 'top': top, 'type': 'text', 'text': md,
            'md': md, 'images': images or []}


def test_merge_blocks_dedupes_across_overlapping_rounds():
    collected = {}
    # 三轮采集有重叠，且第二、三轮才出现新块
    crawler.merge_blocks(collected, [_blk('a', 0, 'A'), _blk('b', 100, 'B')])
    crawler.merge_blocks(collected, [_blk('b', 100, 'B'), _blk('c', 200, 'C')])
    crawler.merge_blocks(collected, [_blk('c', 200, 'C'), _blk('d', 300, 'D')])
    ordered = crawler.ordered_blocks(collected)
    assert [b['key'] for b in ordered] == ['a', 'b', 'c', 'd']


def test_merge_blocks_out_of_order_rounds_still_sort_by_position():
    collected = {}
    crawler.merge_blocks(collected, [_blk('c', 200, 'C')])
    crawler.merge_blocks(collected, [_blk('a', 0, 'A')])
    assert [b['key'] for b in crawler.ordered_blocks(collected)] == ['a', 'c']


def test_merge_blocks_keeps_richer_version_of_lazy_block():
    """图片是懒加载的：同一个块第一轮没图，后面几轮才有，要保留信息更全的那份。"""
    collected = {}
    crawler.merge_blocks(collected, [_blk('a', 0, '标题')])
    crawler.merge_blocks(collected, [_blk('a', 0, '标题正文更长了', images=['u1'])])
    merged = collected['a']
    assert merged['images'] == ['u1']
    assert merged['md'] == '标题正文更长了'


def test_merge_blocks_does_not_lose_images_on_later_empty_round():
    collected = {}
    crawler.merge_blocks(collected, [_blk('a', 0, 'x', images=['u1'])])
    crawler.merge_blocks(collected, [_blk('a', 0, 'x')])
    assert collected['a']['images'] == ['u1']


# --------------------------------------------------------------------------- markdown 组装

def test_blocks_to_markdown_rewrites_images_to_local_paths():
    blocks = [_blk('a', 0, '## 入驻材料'), _blk('b', 10, '', images=['https://cdn/x.png'])]
    md = crawler.blocks_to_markdown(blocks, {'https://cdn/x.png': 'abc.png'})
    assert '## 入驻材料' in md
    assert '![](images/abc.png)' in md
    assert 'https://cdn/x.png' not in md


def test_blocks_to_markdown_keeps_remote_url_when_download_failed():
    blocks = [_blk('b', 10, '', images=['https://cdn/x.png'])]
    assert '![](https://cdn/x.png)' in crawler.blocks_to_markdown(blocks, {})


def test_blocks_to_markdown_collapses_repeated_adjacent_image():
    blocks = [_blk('a', 0, '', images=['u']), _blk('b', 10, '', images=['u'])]
    assert crawler.blocks_to_markdown(blocks, {'u': 'i.png'}).count('![](images/i.png)') == 1


def test_blocks_to_markdown_drops_ui_noise_line():
    blocks = [_blk('a', 0, '正文'), _blk('b', 10, '本文暂未被其它文档引用')]
    md = crawler.blocks_to_markdown(blocks)
    assert '正文' in md and '本文暂未被其它文档引用' not in md


def test_markdown_to_text_strips_marks_and_images():
    md = '# 标题\n\n- 一条\n\n![](images/a.png)\n\n---\n\n正文'
    plain = crawler.markdown_to_text(md)
    assert '标题' in plain and '#' not in plain
    assert '一条' in plain and plain.count('- ') == 0
    assert 'images/a.png' not in plain
    assert '---' not in plain


# --------------------------------------------------------------------------- 图片落盘

_PNG_1PX = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)


def test_decode_data_url_and_save_images(tmp_path):
    data_url = 'data:image/png;base64,' + base64.b64encode(_PNG_1PX).decode()
    decoded = crawler.decode_data_url('https://cdn/a.png', data_url)
    saved, failed = crawler.save_images({'https://cdn/a.png': decoded}, str(tmp_path / 'images'))
    assert not failed
    name = saved['https://cdn/a.png']
    assert name.endswith('.png')
    assert (tmp_path / 'images' / name).read_bytes() == _PNG_1PX


def test_save_images_records_failure_instead_of_writing_empty_file(tmp_path):
    results = {'https://cdn/a.png': crawler.decode_data_url('https://cdn/a.png', 'ERR:http_401')}
    saved, failed = crawler.save_images(results, str(tmp_path / 'images'))
    assert saved == {}
    assert failed[0]['reason'] == 'ERR:http_401'
    assert not list((tmp_path / 'images').iterdir())


# --------------------------------------------------------------------------- 落盘产物

def test_write_doc_outputs_writes_all_artifacts(tmp_path):
    blocks = [_blk('a', 0, '# 标题'), _blk('b', 10, '正文'), _blk('c', 20, '', images=['u'])]
    meta = crawler.write_doc_outputs(str(tmp_path), {'platform': 'Noon', 'site': '通用'},
                                     blocks, {'u': 'i.png'}, page_html='<html></html>')
    assert meta['block_count'] == 3
    assert meta['image_count'] == 1
    assert meta['char_count'] > 0
    for name in ('content.md', 'content.txt', 'blocks.json', 'meta.json', 'page.html'):
        assert (tmp_path / name).exists()
    assert '![](images/i.png)' in (tmp_path / 'content.md').read_text(encoding='utf-8')
    assert 'images/i.png' not in (tmp_path / 'content.txt').read_text(encoding='utf-8')


# --------------------------------------------------------------------------- 腾讯文档解码

def _tencent_blob(lines):
    """构造一段和真实 blob 同形的字节流：文本片段之间夹着不可见的 protobuf 框架字节。"""
    raw = b''
    for line in lines:
        raw += b'\x0a\x07' + line.encode('utf-8')
    return base64.b64encode(raw).decode()


def test_decode_tencent_cuts_at_word_style_table():
    """真实数据里正文只占前面一小段，后面整张 Word 样式表都会被当成正文，必须截断。"""
    blob = _tencent_blob([
        'noon入驻运营指南',
        'FBN为noon官方仓海外备货模式，平台对商家进行类目佣金结算。',
        '微软雅黑*',
        '这段在样式表之后，不能算正文',
        'p.144115420359515000@eJ',
    ])
    body, images = crawler.decode_tencent_attributed_text([blob])
    assert body[0] == 'noon入驻运营指南'
    assert any('FBN为noon官方仓' in x for x in body)
    assert all('微软雅黑' not in x for x in body)
    assert all('不能算正文' not in x for x in body)
    assert images == []


def test_decode_tencent_collects_images_from_resource_region():
    """图片直链在正文之后的资源区，截断之前必须先把它们捞出来。"""
    url = 'https://docimg9.docs.qq.com/image/AgAANga6D0LzEJYJIkFF8IOBUcU95FkQ.png?w=2066&h=1252'
    blob = _tencent_blob(['正文第一段内容在这里', '微软雅黑*', 'T' + url])
    body, images = crawler.decode_tencent_attributed_text([blob])
    assert images == [url]
    assert all('docimg9' not in x for x in body)


def test_decode_tencent_dedupes_adjacent_repeats():
    blob = _tencent_blob(['重复的一段内容', '重复的一段内容', '另一段内容'])
    body, _ = crawler.decode_tencent_attributed_text([blob])
    assert body == ['重复的一段内容', '另一段内容']


def test_is_tencent_metadata_line_does_not_eat_real_content():
    assert crawler._is_tencent_metadata_line('微软雅黑*')
    assert crawler._is_tencent_metadata_line('p.144115420359515000@eJ')
    assert crawler._is_tencent_metadata_line('7FD7E9A0')
    # 正文里合法出现的编号/短句不能被当成元数据
    assert not crawler._is_tencent_metadata_line('2.4.1派安盈Payoneer')
    assert not crawler._is_tencent_metadata_line('沙特15%，阿联酋5%')
    assert not crawler._is_tencent_metadata_line('Q8：请问Barcode设置了多个，可以删除吗？')


# --------------------------------------------------------------------------- 企微文档解码

def _wecom_payload(text):
    """企微文档的 opendoc 返回明文 JSON：全部正文塞在一个 ty='is' 的 mutation 里。"""
    return [{'commands': [{'type': 'DocKeyframe',
                           'mutations': [{'ty': 'mp', 'bi': 0},
                                         {'ty': 'is', 'bi': 0, 's': text}]}]}]


def test_parse_wecom_splits_on_carriage_return():
    lines, _ = crawler.parse_wecom_attributed_text(
        _wecom_payload('美客多自发货卖家运营大全\r1. 新卖家入驻\r\r1.1 注册指引'))
    assert lines == ['美客多自发货卖家运营大全', '1. 新卖家入驻', '1.1 注册指引']


def test_parse_wecom_rewrites_hyperlink_marker_to_markdown():
    raw = ('1.1 注册指引\r\x13HYPERLINK https://doc.weixin.qq.com/pdf/d3_x?scode=abc docLink '
           '\\tdft Doc \\tdkey cmlgyz\x14新卖家账号注册指引\x15 后面还有正文')
    lines, _ = crawler.parse_wecom_attributed_text(_wecom_payload(raw))
    assert '[新卖家账号注册指引](https://doc.weixin.qq.com/pdf/d3_x?scode=abc)' in lines[1]
    assert '后面还有正文' in lines[1]
    assert 'HYPERLINK' not in lines[1] and 'tdkey' not in lines[1]


def test_parse_wecom_cuts_comment_region():
    """\x0f 之后是协作评论区（@某某 这里要补充），不截掉会被当成知识抽出来。"""
    raw = ('正文最后一段\r\x0f\x1e\x1e\x1c已补充\r\x1d\x1c'
           '\x13MENTION_WXWORK 168 168\x14@Yoyo\x15这部分我们有卖家文档可以贴进去嘛？\r\x1d')
    lines, _ = crawler.parse_wecom_attributed_text(_wecom_payload(raw))
    assert lines == ['正文最后一段']
    assert all('@Yoyo' not in x and '已补充' not in x for x in lines)


def test_parse_wecom_counts_image_placeholders():
    raw = '第一段\r\x08\r第二段\r\x08\r第三段'
    lines, placeholders = crawler.parse_wecom_attributed_text(_wecom_payload(raw))
    assert placeholders == 2
    # 占位符本身不能留在正文里
    assert lines == ['第一段', '第二段', '第三段']


# --------------------------------------------------------------------------- 登录判定

class _FakePage(object):
    def __init__(self, url, body):
        self.url = url
        self._body = body

    def evaluate(self, _script):
        return self._body


def test_is_login_page_detects_feishu_redirect():
    assert crawler.is_login_page(_FakePage('https://accounts.feishu.cn/accounts/page/login', ''))


def test_is_login_page_detects_wecom_login_shell():
    assert crawler.is_login_page(
        _FakePage('https://doc.weixin.qq.com/doc/w3_x', '企业身份登录\n切换个人身份登录'))


def test_is_login_page_detects_no_permission():
    assert crawler.is_login_page(
        _FakePage('https://bytedance.larkoffice.com/wiki/x', '没有权限访问\n申请阅读权限'))


def test_is_login_page_false_for_real_doc():
    assert not crawler.is_login_page(
        _FakePage('https://bytedance.sg.larkoffice.com/docx/x', '入驻需要用到的材料'))


# --------------------------------------------------------------------------- 表格里的图片

def test_table_cell_images_are_inlined_not_appended():
    """表格单元格里的操作截图必须留在单元格里，且不再单独追加一行（否则同一张图出现两次）。"""
    md = '| 第1步 ⟦IMG:https://cdn/a.png⟧ | 第2步 ⟦IMG:https://cdn/b.png⟧ |\n| --- | --- |'
    blk = {'key': 't', 'top': 0, 'type': 'table', 'text': '', 'md': md,
           'images': ['https://cdn/a.png', 'https://cdn/b.png']}
    out = crawler.blocks_to_markdown([blk], {'https://cdn/a.png': 'a.png',
                                             'https://cdn/b.png': 'b.png'})
    assert '第1步 ![](images/a.png)' in out
    assert '第2步 ![](images/b.png)' in out
    assert out.count('images/a.png') == 1        # 不能再单独追加一行
    assert '⟦IMG:' not in out


def test_table_image_token_falls_back_to_remote_url():
    blk = {'key': 't', 'top': 0, 'type': 'table', 'text': '', 'images': ['https://cdn/x.png'],
           'md': '| 步骤 ⟦IMG:https://cdn/x.png⟧ |\n| --- |'}
    out = crawler.blocks_to_markdown([blk], {})
    assert '![](https://cdn/x.png)' in out
    assert '⟦IMG:' not in out


def test_non_table_images_still_appended_separately():
    blk = {'key': 'i', 'top': 0, 'type': 'image', 'text': '', 'md': '',
           'images': ['https://cdn/c.png']}
    out = crawler.blocks_to_markdown([blk], {'https://cdn/c.png': 'c.png'})
    assert '![](images/c.png)' in out


# --- 飞书表格（canvas 渲染，走剪贴板） -------------------------------------

def test_tsv_to_blocks_keeps_row_column_alignment():
    """短行要补齐到最宽列，否则 markdown 表格错位，行列对应关系就废了。"""
    tsv = '一级类目\t二级类目\t是否定邀\n美妆\t彩妆\t否\n家清\n'
    blocks = crawler.tsv_to_blocks(tsv)
    assert len(blocks) == 1
    lines = blocks[0]['md'].split('\n')
    assert lines[0] == '| 一级类目 | 二级类目 | 是否定邀 |'
    assert lines[1] == '| --- | --- | --- |'
    assert lines[-1] == '| 家清 |  |  |'


def test_tsv_to_blocks_escapes_pipe_in_cell():
    blocks = crawler.tsv_to_blocks('名称\t备注\nA\t限制|定邀\n')
    assert r'限制\|定邀' in blocks[0]['md']


def test_tsv_to_blocks_empty():
    assert crawler.tsv_to_blocks('') == []
    assert crawler.tsv_to_blocks('   \n  \n') == []


class _ToastPage(object):
    def __init__(self, toasts):
        self._toasts = toasts

    def evaluate(self, script, *args):
        return self._toasts


def test_detect_copy_forbidden_matches_permission_toast():
    """飞书禁复制的提示要能认出来，否则会当成技术故障白重试三次。"""
    page = _ToastPage(['评论',
                      '由于文档权限设置，如需复制请联系 @欧向容 开通可编辑权限。\n了解更多'])
    msg = crawler._detect_copy_forbidden(page)
    assert msg and '权限' in msg
    assert '\n' not in msg


def test_detect_copy_forbidden_ignores_unrelated_toast():
    assert crawler._detect_copy_forbidden(_ToastPage(['评论', '已保存'])) is None
    assert crawler._detect_copy_forbidden(_ToastPage([])) is None


def test_detect_copy_forbidden_survives_evaluate_error():
    class _Boom(object):
        def evaluate(self, *a):
            raise RuntimeError('页面已关闭')
    assert crawler._detect_copy_forbidden(_Boom()) is None


# --- crawl_manifest 合并 -----------------------------------------------------

def test_write_crawl_manifest_merges_instead_of_overwriting(tmp_path):
    """同一个 root 被两份清单先后爬时，第二批不能把第一批抹掉。"""
    out = str(tmp_path / 'crawl_manifest.json')
    crawler.write_crawl_manifest(
        out, [{'platform': 'P', 'site': 'web1', 'status': 'ok'}], 'web.json')
    crawler.write_crawl_manifest(
        out, [{'platform': 'P', 'site': 'doc1', 'status': 'ok'}], 'doc.json')
    docs = json.load(open(out, encoding='utf-8'))['docs']
    assert {d['site'] for d in docs} == {'web1', 'doc1'}


def test_write_crawl_manifest_same_doc_takes_latest(tmp_path):
    out = str(tmp_path / 'crawl_manifest.json')
    crawler.write_crawl_manifest(
        out, [{'platform': 'P', 'site': 's', 'status': 'failed'}], 'a.json')
    crawler.write_crawl_manifest(
        out, [{'platform': 'P', 'site': 's', 'status': 'ok', 'char_count': 9}], 'a.json')
    docs = json.load(open(out, encoding='utf-8'))['docs']
    assert len(docs) == 1 and docs[0]['status'] == 'ok'


def test_write_crawl_manifest_tolerates_corrupt_old_file(tmp_path):
    out = str(tmp_path / 'crawl_manifest.json')
    open(out, 'w', encoding='utf-8').write('{ not json')
    crawler.write_crawl_manifest(out, [{'platform': 'P', 'site': 's'}], 'a.json')
    assert len(json.load(open(out, encoding='utf-8'))['docs']) == 1


# --- 目录名撞车 ---------------------------------------------------------------

def test_disambiguate_sites_splits_colliding_slugs():
    """只有 query 尾巴不同的链接会截成同一个 slug，撞名的后一篇会覆盖前一篇。"""
    items = [
        {'platform': 'TikTok Shop-东南亚', 'site': 'essay_identity_1_role',
         'url': 'https://x/essay?identity=1&role=1&knowledge_id=111'},
        {'platform': 'TikTok Shop-东南亚', 'site': 'essay_identity_1_role',
         'url': 'https://x/essay?identity=1&role=1&knowledge_id=222'},
    ]
    crawler.disambiguate_sites(items)
    assert items[0]['site'] != items[1]['site']
    assert all(i['site'].startswith('essay_identity_1_role_') for i in items)


def test_disambiguate_sites_leaves_unique_ones_alone():
    items = [{'platform': 'TikTok Shop', 'site': '美国ACCU', 'url': 'https://a'},
             {'platform': 'TikTok Shop', 'site': '英国', 'url': 'https://b'}]
    crawler.disambiguate_sites(items)
    assert [i['site'] for i in items] == ['美国ACCU', '英国']


def test_disambiguate_sites_is_stable_across_runs():
    """哈希必须只由 URL 决定，否则重跑会换目录名、--skip-existing 全部失效。"""
    def sites():
        items = [{'platform': 'P', 'site': 's', 'url': 'https://a'},
                 {'platform': 'P', 'site': 's', 'url': 'https://b'}]
        crawler.disambiguate_sites(items)
        return [i['site'] for i in items]
    assert sites() == sites()


def test_tsv_to_blocks_splits_large_table_and_repeats_header():
    """大表整块下去会让下游整页超 Dify 上限；切块时表头必须跟着走。"""
    tsv = '\n'.join(['类目\t资质\t是否定邀'] + ['行%d\t值%d\t否' % (i, i) for i in range(3000)])
    blocks = crawler.tsv_to_blocks(tsv, max_chars=8000)
    assert len(blocks) > 1
    assert all(len(b['md']) <= 8000 for b in blocks)
    assert all(b['md'].startswith('| 类目 | 资质 | 是否定邀 |') for b in blocks)
    assert all(b['md'].split('\n')[1] == '| --- | --- | --- |' for b in blocks)
    # 数据行不能丢也不能重
    data = sum(len(b['md'].split('\n')) - 2 for b in blocks)
    assert data == 3000
    assert len({b['key'] for b in blocks}) == len(blocks)


def test_tsv_to_blocks_single_row_table_still_one_block():
    blocks = crawler.tsv_to_blocks('表头A\t表头B\n')
    assert len(blocks) == 1
    assert blocks[0]['md'] == '| 表头A | 表头B |\n| --- | --- |'
