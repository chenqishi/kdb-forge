from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""图片占位符方案的行为测试（离线，不调模型）。

要守住的三条语义：
  1. 同一张图在多次调用里必须拿到**同一个编号** —— `merge_segment_content` 在一次生成里
     会被调用多次（整篇一次、分段各一次），按调用重新计数会让编号乱飘。
  2. 喂给模型的正文里**不能出现图片 URL** —— 模型抄 40 字符的随机 URL 会抄错
     （实测把日期段重复三遍、多个 URL 粘连），链接必须由映射表还原。
  3. 还原时标记对不上要静默丢弃，**不能产出坏链**。
"""
import os
import sys

ROOT = str(_PROJECT_ROOT)

from kdb.mining.transformations.schema_trans import merge_segment_content
from kdb.mining.transformations.schema_trans import restore_image_placeholders
from kdb.mining.transformations.schema_trans import strip_image_placeholders
from kdb.mining.transformations.schema_trans import IMAGE_PLACEHOLDER_GUIDE

URL_A = 'https://file.marsmind.cc/kgmultimodal/knowledge/multimodal/default/20260807/aaa.png'
URL_B = 'https://file.marsmind.cc/kgmultimodal/knowledge/multimodal/default/20260807/bbb.png'


def _doc():
    return {
        '1': [
            {'type': 'text', 'text_content': '入驻需要营业执照。'},
            {'type': 'image', 'is_valid': True, 'public_url': URL_A,
             'image_ocr': '证件要求 图片小于10MB 支持JPG PNG',
             'image_understanding': '这是上传法人证件的界面截图'},
        ],
        '2': [
            {'type': 'text', 'text_content': '审核需要3~10个工作日。'},
            {'type': 'image', 'is_valid': True, 'public_url': URL_B, 'image_ocr': '审核中'},
        ],
    }


def test_placeholder_mode_hides_urls_and_exposes_image_content():
    m = {}
    out = merge_segment_content(_doc(), {'pages': [1, 2]}, use_image_content=1,
                                image_placeholder_map=m)
    assert URL_A not in out and URL_B not in out      # 模型看不到任何 URL
    assert '[图1]' in out and '[图2]' in out
    assert '证件要求 图片小于10MB' in out                 # OCR 喂进去了
    assert '这是上传法人证件的界面截图' in out              # 图片理解喂进去了
    assert out.startswith(IMAGE_PLACEHOLDER_GUIDE)     # 用法说明在最前面


def test_same_image_keeps_same_tag_across_calls():
    """整篇一次 + 分段各一次，同一张图必须是同一个编号。"""
    m = {}
    doc = _doc()
    merge_segment_content(doc, {'pages': [1, 2]}, use_image_content=1, image_placeholder_map=m)
    page1 = merge_segment_content(doc, {'pages': [1, 1]}, use_image_content=1,
                                  image_placeholder_map=m)
    assert len(m) == 2                                  # 没有因为第二次调用而重复编号
    assert m['[图1]'] == URL_A
    assert '[图1]' in page1 and '[图3]' not in page1


def test_add_image_context_mode_unchanged():
    """不传 map 时行为不变：add_image_context=1 仍然铺 OCR，=0 仍然只给裸 URL。"""
    ctx1 = merge_segment_content(_doc(), {'pages': [1, 1]}, use_image_content=1,
                                 add_image_context=1)
    assert URL_A in ctx1 and '<image_ocr>' in ctx1
    ctx0 = merge_segment_content(_doc(), {'pages': [1, 1]}, use_image_content=1,
                                 add_image_context=0)
    assert URL_A in ctx0 and '<image_ocr>' not in ctx0


def test_restore_turns_tag_into_image():
    m = {'[图1]': URL_A}
    out = restore_image_placeholders('材料要求见下。\n[图1]', m)
    assert '![嵌入图片](%s "Flowchart")' % URL_A in out
    assert '[图1]' not in out


def test_restore_handles_fullwidth_brackets():
    """模型有时会写成【图1】，也要认。"""
    assert URL_A in restore_image_placeholders('说明。\n【图1】', {'[图1]': URL_A})


def test_restore_drops_unknown_tag_instead_of_emitting_bad_link():
    out = restore_image_placeholders('说明。\n[图99]', {'[图1]': URL_A})
    assert 'http' not in out          # 宁可少一张图，也不产出坏链
    assert '[图99]' not in out


def test_strip_placeholders_from_question():
    assert strip_image_placeholders('[图3] 上传证件有什么要求？') == '上传证件有什么要求？'


def test_invalid_image_skipped_in_placeholder_mode():
    doc = {'1': [{'type': 'image', 'is_valid': False, 'public_url': URL_A, 'image_ocr': 'x'},
                 {'type': 'text', 'text_content': '正文'}]}
    m = {}
    out = merge_segment_content(doc, {'pages': [1, 1]}, use_image_content=1,
                                image_placeholder_map=m)
    # 说明文案里本来就带 [图1] 字样，所以看映射表而不是看正文
    assert m == {}
    assert out[len(IMAGE_PLACEHOLDER_GUIDE):].strip() == '正文'


# --------------------------------------------------------------------------- 幻觉 URL 清理

from kdb.mining.transformations.schema_trans import strip_hallucinated_image_urls


def test_strip_hallucinated_image_url():
    """占位符模式下模型看不到图床地址，写出来的都是编的，送质检前必须清掉。"""
    text = '入驻需要营业执照。\nhttps://file.marsmind.cc/kgmultimodal/knowledge/x/aaa.png'
    out = strip_hallucinated_image_urls(text)
    assert 'kgmultimodal' not in out
    assert '入驻需要营业执照。' in out


def test_strip_repeated_path_url():
    """实测的退化形态：日期段复读几百次，一条就能撑爆质检的 token 预算。"""
    bad = 'https://file.marsmind.cc/kgmultimodal/a/' + '20260807/' * 200 + 'x.png'
    out = strip_hallucinated_image_urls('说明。\n' + bad)
    assert 'kgmultimodal' not in out and len(out) < 30


def test_strip_keeps_normal_links():
    """官网/入驻通道这类正常链接不能误删。"""
    text = '官方入驻通道：https://seller.tiktokshopglobalselling.com/account/register'
    assert strip_hallucinated_image_urls(text) == text


def test_strip_markdown_image_form():
    out = strip_hallucinated_image_urls('材料清单如下。\n![](https://file.marsmind.cc/kgmultimodal/a/b.png)')
    assert 'kgmultimodal' not in out and '材料清单如下。' in out
