# -*- coding:utf8 -*-

"""删死链裸 URL 的纯逻辑。

覆盖我已经栽过的点：
1. 多个 URL 无分隔符粘在一起，贪婪正则会跨过边界把拼接串当一个 URL 测（虚报死链）；
2. `content` 是 `multimodal_contents` 拼出来的，改完要重拼、而不是对 content 做字符串手术；
3. 重拼前必须自检能复现现有 content，不一致就不改。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_prune_dead_raw_urls.py')

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))

from data_control_tools.prune_dead_raw_urls import (
    clean_multimodal, extract_raw_image_urls, has_dangling_colon,
    join_multimodal_contents, rebuild_matches_current, strip_urls_from_text,
)

U1 = 'https://file.marsmind.cc/kgmultimodal/knowledge/multimodal/default/20260723/aaaaaaaa.jpeg'
U2 = 'https://file.marsmind.cc/kgmultimodal/knowledge/multimodal/default/20260723/bbbbbbbb.png'


# ------------------------------------------------------------------ URL 提取

def test_粘在一起的两个url能切开():
    """实测正文里是 `….pnghttps://…` 这种无分隔符粘连，贪婪正则会切成一个。"""
    got = extract_raw_image_urls(U2 + U1)
    assert got == [U2, U1]


def test_三个粘在一起也能切开():
    got = extract_raw_image_urls(U1 + U2 + U1)
    assert got == [U1, U2]          # 去重，保持出现顺序


def test_独占一行的url():
    assert extract_raw_image_urls('说明文字。\n%s\n结尾' % U1) == [U1]


def test_不抓非图片url():
    text = '见 https://developer.wayfair.io/vendor-marketplace 和 %s' % U1
    assert extract_raw_image_urls(text) == [U1]


def test_扩展名大小写都认():
    up = U1.replace('.jpeg', '.JPEG')
    assert extract_raw_image_urls(up) == [up]


def test_空文本不报错():
    assert extract_raw_image_urls('') == []
    assert extract_raw_image_urls(None) == []


# -------------------------------------------------------------------- 拼接

def test_拼接规则_文本加图片():
    mm = [{'type': 'text', 'content': '答案文字'},
          {'type': 'image', 'path': 'p/a.png'},
          {'type': 'image', 'path': 'p/b.png'}]
    assert join_multimodal_contents(mm) == (
        '答案文字\n[multimodal_prefix]p/a.png\n[multimodal_prefix]p/b.png')


def test_拼接规则_没有path时用url():
    mm = [{'type': 'text', 'content': '答案'},
          {'type': 'image', 'url': 'https://ext/x.png'}]
    assert join_multimodal_contents(mm) == '答案\nhttps://ext/x.png'


def test_拼接规则_path和url都没有就跳过():
    mm = [{'type': 'text', 'content': '答案'}, {'type': 'image'}]
    assert join_multimodal_contents(mm) == '答案'


def test_自检_能复现现有content():
    mm = [{'type': 'text', 'content': '答案'}, {'type': 'image', 'path': 'p/a.png'}]
    assert rebuild_matches_current(mm, '答案\n[multimodal_prefix]p/a.png')


def test_自检_复现不了就返回False():
    """content 不是纯拼接产物时不能动它。"""
    mm = [{'type': 'text', 'content': '答案'}]
    assert not rebuild_matches_current(mm, '答案\n多出来的一行')


# ---------------------------------------------------------------- 删除与收尾

def test_删掉独占一行的url不留空行():
    text = '第一句。\n%s\n第二句。' % U1
    assert strip_urls_from_text(text, {U1}) == '第一句。\n\n第二句。'


def test_删掉末尾的url不留尾部空白():
    text = '第一句。\n%s' % U1
    assert strip_urls_from_text(text, {U1}) == '第一句。'


def test_删掉粘连的两个url():
    text = '第一句。\n%s%s' % (U1, U2)
    assert strip_urls_from_text(text, {U1, U2}) == '第一句。'


def test_只删死的保留活的():
    text = '第一句。\n%s\n%s' % (U1, U2)
    assert strip_urls_from_text(text, {U1}) == '第一句。\n\n%s' % U2


def test_冒号结尾会被标出来():
    text = '需要提供以下信息：\n%s' % U1
    assert has_dangling_colon(text, {U1})


def test_正常句子结尾不算悬空():
    text = '这是完整的一句话。\n%s' % U1
    assert not has_dangling_colon(text, {U1})


# ------------------------------------------------------- 只改 text 项不动图片项

def test_只改text项图片项原样保留():
    mm = [{'type': 'text', 'content': '答案。\n%s' % U1},
          {'type': 'image', 'path': 'p/a.png', 'image_ocr': 'x'}]
    new, removed = clean_multimodal(mm, {U1})
    assert removed == 1
    assert new[0]['content'] == '答案。'
    assert new[1] == mm[1]                      # 图片项对象内容不变


def test_没有死链时原样返回():
    mm = [{'type': 'text', 'content': '答案。\n%s' % U1}]
    new, removed = clean_multimodal(mm, {U2})
    assert removed == 0
    assert new[0]['content'] == mm[0]['content']


def test_清完重拼与手动删除结果一致():
    """这是本工具的核心不变量：改 multimodal_contents 后重拼 == 期望的新 content。"""
    mm = [{'type': 'text', 'content': '答案。\n%s' % U1},
          {'type': 'image', 'path': 'p/a.png'}]
    content = join_multimodal_contents(mm)
    assert rebuild_matches_current(mm, content)
    new, _ = clean_multimodal(mm, {U1})
    assert join_multimodal_contents(new) == '答案。\n[multimodal_prefix]p/a.png'


def test_不修改原始对象():
    mm = [{'type': 'text', 'content': '答案。\n%s' % U1}]
    clean_multimodal(mm, {U1})
    assert U1 in mm[0]['content']               # 原 dict 不能被就地改


# ------------------------------------ 兜底：mm 顺序与 content 不一致时就地删

def test_就地删_正常情况():
    from data_control_tools.prune_dead_raw_urls import surgery_on_content
    content = '第一段。\n%s\n第二段。\n[multimodal_prefix]p/a.png' % U1
    got = surgery_on_content(content, {U1})
    assert got == '第一段。\n\n第二段。\n[multimodal_prefix]p/a.png'
    assert U1 not in got
    assert '[multimodal_prefix]p/a.png' in got


def test_就地删_只删指定的保留其他url():
    from data_control_tools.prune_dead_raw_urls import surgery_on_content
    content = '正文。\n%s\n%s' % (U1, U2)
    got = surgery_on_content(content, {U1})
    assert U1 not in got and U2 in got


def test_就地删_不动正文文字():
    from data_control_tools.prune_dead_raw_urls import surgery_on_content
    content = '需要注意以下三点：甲、乙、丙。\n%s' % U1
    got = surgery_on_content(content, {U1})
    assert got == '需要注意以下三点：甲、乙、丙。'


def test_就地删_粘连的url():
    from data_control_tools.prune_dead_raw_urls import surgery_on_content
    content = '正文。\n%s%s' % (U1, U2)
    got = surgery_on_content(content, {U1, U2})
    assert got == '正文。'
