# -*- coding:utf8 -*-

"""裁图判据的纯逻辑。

三个必须守住的点：
1. 页码字段 QA 是 `from_page`、segment 是 `start_page`/`end_page` —— 搞错会全裁光或全跳过；
2. 匹配按图片内容 md5，不按路径 —— 同一张图有多个 s3_path；
3. 裁图前要认出「有话术指着这张图」，且 `图中` 不能误伤 视图中 / 屏幕截图中 / 白底图中。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_prune_page_mismatched_images.py')

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))

from data_control_tools.prune_page_mismatched_images import (
    allowed_md5_for_range, append_markers, attach_item_to_multimodal,
    find_pointing_deictic, orphan_deictic, page_items_for_range, parse_page_range,
    plan_row, rebuild_multimodal, rewrite_content,
)

P = '[multimodal_prefix]'


def _mk(path):
    return P + path


# --------------------------------------------------------------------- 页码

def test_qa用from_page():
    assert parse_page_range({'from_page': [3, 5]}, 'qa') == (3, 5)


def test_segment用start_end_page():
    assert parse_page_range({'start_page': 2, 'end_page': 15}, 'segment') == (2, 15)


def test_segment没有from_page也能取到():
    """segment 的 ext_info 里没有 from_page，用错字段会取不到页码而整批跳过。"""
    ext = {'start_page': 7, 'end_page': 8, 'topics': [], 'phrases': []}
    assert parse_page_range(ext, 'segment') == (7, 8)
    assert parse_page_range(ext, 'qa') is None


def test_页码缺失返回None():
    assert parse_page_range({}, 'qa') is None
    assert parse_page_range({'start_page': 1}, 'segment') is None


def test_页码区间是闭区间且允许反序():
    per_page = {1: {'a'}, 2: {'b'}, 3: {'c'}, 9: {'z'}}
    assert allowed_md5_for_range(per_page, (1, 3)) == {'a', 'b', 'c'}
    assert allowed_md5_for_range(per_page, (3, 1)) == {'a', 'b', 'c'}
    assert allowed_md5_for_range(per_page, (2, 2)) == {'b'}


# ----------------------------------------------------------------- 话术判断

def test_如下图所示紧邻标记算指着它():
    content = '在此处填写代码（如下图所示）。\n' + _mk('p/a.png')
    assert find_pointing_deictic(content, content.index(P)) == '如下图所示'


def test_视图中不算指图话术():
    content = '以便您在一个视图中查看所有产品内容的变更情况。\n' + _mk('p/a.png')
    assert find_pointing_deictic(content, content.index(P)) is None


def test_屏幕截图中不算指图话术():
    content = '注意：在此屏幕截图中，您会注意到默认行以黑色表示。\n' + _mk('p/a.png')
    assert find_pointing_deictic(content, content.index(P)) is None


def test_产品白底图中不算指图话术():
    content = '避免从产品白底图中删除某些特征。\n' + _mk('p/a.png')
    assert find_pointing_deictic(content, content.index(P)) is None


def test_图中的编辑按钮算指图话术():
    content = '点击图中的编辑按钮，进入职责勾选界面。\n' + _mk('p/a.png')
    assert find_pointing_deictic(content, content.index(P)) == '图中'


def test_话术离得太远就不算指着():
    content = '请参见下图了解新标签内容：' + ('填' * 200) + '\n' + _mk('p/a.png')
    assert find_pointing_deictic(content, content.index(P)) is None


def test_话术只算到第一张图不会顺延到后面每一张():
    """一串图里，前面那句话术只指第一张，不能被算成指着每一张。"""
    content = '如下图所示。\n' + _mk('p/a.png') + '\n' + _mk('p/b.png')
    first = content.index(_mk('p/a.png'))
    second = content.index(_mk('p/b.png'))
    assert find_pointing_deictic(content, first) == '如下图所示'
    assert find_pointing_deictic(content, second) is None


def test_长话术优先不被短的切断():
    content = '查询方式如下图圆圈所示。\n' + _mk('p/a.png')
    assert find_pointing_deictic(content, content.index(P)) == '如下图圆圈所示'


def test_强话术附近没有任何图算失联():
    content = '可以查看下方海报，了解详情，咨询报名！' + ('字' * 300) + '\n' + _mk('p/a.png')
    assert orphan_deictic(content) == ['下方海报']


def test_强话术紧邻有图就不算失联():
    content = '可以查看下方海报了解详情。\n' + _mk('p/a.png')
    assert orphan_deictic(content) == []


# ------------------------------------------------------------------- 裁剪

PATH_MD5 = {
    'p/a1.png': 'A', 'p/a2.png': 'A',   # 同一张图 A 的两个地址
    'p/b1.png': 'B',
    'p/c1.png': 'C',
}


def test_只留本页的图():
    content = '正文。\n' + _mk('p/a1.png') + '\n' + _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'})
    assert plan['keep_paths'] == ['p/a1.png']
    assert [d['path'] for d in plan['drop']] == ['p/c1.png']
    assert plan['drop'][0]['reason'] == 'page_mismatch'
    assert plan['action'] == 'prune'


def test_同一张图的多个地址只留一个():
    """A 有两个 s3_path，都属于本页，但是同一张图，只应留一个。"""
    content = '正文。\n' + _mk('p/a1.png') + '\n' + _mk('p/a2.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'})
    assert plan['keep_paths'] == ['p/a1.png']
    assert plan['drop'][0]['reason'] == 'duplicate'


def test_按路径比对会误杀所以必须按md5():
    """A 在本页，但 ES 里存的是它的另一个地址 a2；按路径比不上，按 md5 能留住。"""
    content = '正文。\n' + _mk('p/a2.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'})
    assert plan['keep_paths'] == ['p/a2.png']
    assert plan['drop'] == []


def test_md5未知的标记保守保留():
    content = '正文。\n' + _mk('p/unknown.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'})
    assert plan['keep_paths'] == ['p/unknown.png']
    assert plan['unknown_paths'] == 1
    assert plan['action'] == 'noop'


def test_被话术指着的图被裁会标记出来():
    content = '步骤如下图所示。\n' + _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'})
    assert plan['action'] == 'review_deictic'
    assert plan['drop'][0]['deictic'] == '如下图所示'


def test_话术指着的图被裁但还剩别的图算可自动处理():
    content = '正文。\n' + _mk('p/a1.png') + '\n步骤如下图所示。\n' + _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'})
    assert plan['keep_paths'] == ['p/a1.png']
    assert plan['action'] == 'prune_with_deictic'


def test_没有要裁的就是noop():
    content = '正文。\n' + _mk('p/a1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'})
    assert plan['action'] == 'noop'
    assert plan['drop'] == []


# ----------------------------------------------------------------- 正文改写

def test_裁标记不动正文文字():
    content = '第一步。\n第二步。\n' + _mk('p/a1.png') + '\n' + _mk('p/c1.png')
    out = rewrite_content(content, ['p/c1.png'])
    assert out == '第一步。\n第二步。\n' + _mk('p/a1.png')


def test_不传要裁的路径就原样返回():
    content = '正文。\n' + _mk('p/a1.png')
    assert rewrite_content(content, []) == content


def test_同一行多个标记也能裁():
    content = '正文。 ' + _mk('p/a1.png') + ' ' + _mk('p/c1.png')
    out = rewrite_content(content, ['p/c1.png'])
    assert 'p/c1.png' not in out
    assert 'p/a1.png' in out
    assert out.startswith('正文。')


def test_重建multimodal保留文本项并按保留顺序放图():
    texts = [{'type': 'text', 'content': '答案'}]
    images = [{'type': 'image', 'path': 'p/a1.png'}, {'type': 'image', 'path': 'p/c1.png'}]
    out = rebuild_multimodal(images, texts, ['p/a1.png'])
    assert out == [{'type': 'text', 'content': '答案'}, {'type': 'image', 'path': 'p/a1.png'}]


# ------------------------------------------------- 话术指着的图被裁光时补挂正确图

CAND_A = {'md5': 'X', 's3_path': 'p/x.png', 'public_url': 'https://h/p/x.png',
          'fileName': '6_0.png', 'image_ocr': 'OCR-X'}
CAND_NO_URL = {'md5': 'Y', 's3_path': None, 'public_url': None,
               'fileName': '6_1.png', 'image_ocr': ''}


def test_话术指着的图被裁光但该页有图就补挂():
    """实测 大包裹UCC-128标签.docx 页[6,8]：真图 5 张，不该让它变成 0 图。"""
    content = '请参见下图了解新标签内容：\n' + _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'},
                    attach_candidates=[CAND_A])
    assert plan['action'] == 'prune_and_attach'
    assert plan['keep_paths'] == []
    assert [c['s3_path'] for c in plan['attach']] == ['p/x.png']


def test_该页真没有上传过的图就留人工():
    """实测 页[1,1]：真图 0 张，只能删话术或软删，不能自动改。"""
    content = '填写方式如下图所示。\n' + _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'}, attach_candidates=[])
    assert plan['action'] == 'review_deictic'
    assert plan['attach'] == []


def test_该页只有没上传过的图也留人工():
    """s3_path 为空的是判为无效、从未上传的图，挂不回去。"""
    content = '填写方式如下图所示。\n' + _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'},
                    attach_candidates=[CAND_NO_URL])
    assert plan['action'] == 'review_deictic'


def test_没有话术指着就不补挂():
    """没人许诺过有图，裁成 0 图也不该凭空加图。"""
    content = '正文说明。\n' + _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'},
                    attach_candidates=[CAND_A])
    assert plan['action'] == 'prune'
    assert plan['attach'] == []


def test_补挂的图不会和已保留的重复():
    content = '如下图所示。\n' + _mk('p/c1.png')
    same = dict(CAND_A, md5='A', s3_path='p/a9.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'C'}, attach_candidates=[same])
    # C 属于本页所以 c1 被保留，压根没触发补挂
    assert plan['action'] == 'noop'


def test_补挂会追加正文标记():
    content = '请参见下图：\n' + _mk('p/a1.png')
    out = append_markers(content, ['p/x.png'])
    assert out.endswith(_mk('p/x.png'))
    assert _mk('p/a1.png') in out


def test_补挂项转成multimodal图片项格式():
    item = attach_item_to_multimodal(CAND_A)
    assert item == {'type': 'image', 'path': 'p/x.png', 'url': 'https://h/p/x.png',
                    'fileName': '6_0.png', 'image_ocr': 'OCR-X'}


def test_重建multimodal会把补挂的图接在后面():
    texts = [{'type': 'text', 'content': '答案'}]
    images = [{'type': 'image', 'path': 'p/a1.png'}]
    out = rebuild_multimodal(images, texts, ['p/a1.png'], [CAND_A])
    assert len(out) == 3
    assert out[2]['path'] == 'p/x.png'


def test_按页取可挂回的图会跳过没上传的并去重():
    per_page = {
        6: [CAND_A, CAND_NO_URL],
        7: [dict(CAND_A, s3_path='p/x2.png', fileName='7_0.png')],  # 同一张图 X 的另一个地址
        9: [dict(CAND_A, md5='Z', s3_path='p/z.png', fileName='9_0.png')],
    }
    got = page_items_for_range(per_page, (6, 7))
    assert [c['s3_path'] for c in got] == ['p/x.png']      # Y 无 url 被跳过，X 只取一次
    got2 = page_items_for_range(per_page, (6, 9))
    assert [c['s3_path'] for c in got2] == ['p/x.png', 'p/z.png']


# ------------------------------------------- only_duplicate：只裁重复，不按页裁

def test_only_duplicate_不裁超页的图():
    """已用「重跑生成」修过的批次，差一页多半是段落跨页的合法归属，不该再裁。"""
    content = '正文。\n' + _mk('p/a1.png') + '\n' + _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'}, only_duplicate=True)
    assert plan['keep_paths'] == ['p/a1.png', 'p/c1.png']
    assert plan['drop'] == []
    assert plan['action'] == 'noop'


def test_only_duplicate_仍然裁同内容重复图():
    content = '正文。\n' + _mk('p/a1.png') + '\n' + _mk('p/a2.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'}, only_duplicate=True)
    assert plan['keep_paths'] == ['p/a1.png']
    assert [d['reason'] for d in plan['drop']] == ['duplicate']


def test_only_duplicate_超页的图也参与去重():
    """超页的图被保留后要记进 seen，否则它的另一个地址会漏去重。"""
    content = '正文。\n' + _mk('p/c1.png') + '\n' + _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'}, only_duplicate=True)
    assert plan['keep_paths'] == ['p/c1.png']
    assert [d['reason'] for d in plan['drop']] == ['duplicate']


# ------------------------------------- attach_when_no_text：答案本来就是图的那种

def test_正文无文字时补挂该页正确图():
    """Q 本身在问「图片链接是什么」，答案就是图。该页有正确图就该挂回，不该裁空。"""
    content = _mk('p/c1.png')          # 正文除标记外没有一个字
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'},
                    attach_candidates=[CAND_A], attach_when_no_text=True)
    assert plan['action'] == 'prune_and_attach'
    assert [c['s3_path'] for c in plan['attach']] == ['p/x.png']


def test_正文无文字但该页没图仍然留人工():
    content = _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'},
                    attach_candidates=[], attach_when_no_text=True)
    assert plan['action'] == 'review_deictic'


def test_不开开关时正文无文字仍按原样裁():
    content = _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'}, attach_candidates=[CAND_A])
    assert plan['action'] == 'prune'
    assert plan['attach'] == []


def test_正文有文字时开关不生效():
    """有正文的行不该因为图被裁光就凭空补图——正文没许诺过有图。"""
    content = '这里有答案文字。\n' + _mk('p/c1.png')
    plan = plan_row(content, [], PATH_MD5, allowed_md5={'A'},
                    attach_candidates=[CAND_A], attach_when_no_text=True)
    assert plan['action'] == 'prune'
    assert plan['attach'] == []
