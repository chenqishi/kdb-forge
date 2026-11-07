# -*- coding: utf-8 -*-
"""把爬下来的文档投递成挖掘任务的行为测试（全部离线，不打 MinIO / 类目接口 / 任务服务）。

覆盖的是几处「错了不会报错、只会悄悄出错」的地方：
  1. 对象键 slug：站点名全是中文时会被剥空，退回固定串会让多个站点互相覆盖
  2. 类目解析：站点有二级类目就必须挂二级，找不到要炸而不是默默落到默认分组
  3. 图片引用改写：漏改的话解析阶段找不到图，截图里的信息全丢且不报错
  4. 上下文增强开关：这是用户明确要的「带检索和历史对话优化」的流程，不能悄悄退化
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_build_doc_mining_tasks.py')
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
sys.path.insert(0, ROOT)

from data_control_tools import build_doc_mining_tasks as builder  # noqa: E402


# --------------------------------------------------------------------------- slug

def test_slugify_keeps_ascii_part():
    assert builder.slugify('美国ACCU', 'site') == 'accu'
    assert builder.slugify('TikTok Shop', 'platform') == 'tiktok_shop'


def test_slugify_cjk_only_sites_do_not_collide():
    """英国/东南亚/印尼 都会被剥成空串，退回固定串就会共用同一个对象键互相覆盖。"""
    sites = ['英国', '东南亚', '印尼', '墨西哥', '全托管', '欧盟(西德意法)', '通用']
    slugs = [builder.slugify(s, 'site') for s in sites]
    assert all(s for s in slugs)
    assert len(set(slugs)) == len(sites)


def test_slugify_is_stable_across_calls():
    assert builder.slugify('东南亚', 'site') == builder.slugify('东南亚', 'site')


# --------------------------------------------------------------------------- 类目

TREE = [
    {'categoryName': 'Noon', 'categoryId': 1, 'children': []},
    {'categoryName': 'TikTok Shop', 'categoryId': 2, 'children': [
        {'categoryName': '美国ACCU', 'categoryId': 21, 'children': []},
        {'categoryName': '英国', 'categoryId': 22, 'children': []},
    ]},
]


def test_flatten_category_tree_builds_dash_joined_paths():
    mapping = builder.flatten_category_tree(TREE)
    assert mapping['Noon'] == '1'
    assert mapping['TikTok Shop'] == '2'
    assert mapping['TikTok Shop-美国ACCU'] == '21'
    assert mapping['TikTok Shop-英国'] == '22'


def test_resolve_category_prefers_site_level():
    name, cid = builder.resolve_category('TikTok Shop', '美国ACCU',
                                         builder.flatten_category_tree(TREE))
    assert (name, cid) == ('TikTok Shop-美国ACCU', '21')


def test_resolve_category_falls_back_to_platform_when_no_site_category():
    name, cid = builder.resolve_category('Noon', '通用', builder.flatten_category_tree(TREE))
    assert (name, cid) == ('Noon', '1')


def test_resolve_category_raises_instead_of_silently_defaulting():
    """类目缺失时必须炸。默默落到默认分组的话，知识进了库但没人知道它没归类。"""
    with pytest.raises(KeyError):
        builder.resolve_category('Shopee', '通用', builder.flatten_category_tree(TREE))


# --------------------------------------------------------------------------- 图片引用

def test_rewrite_image_refs_replaces_relative_paths():
    md = '正文\n\n![](images/a.png)\n\n![说明](images/b.jpg)'
    out, missing = builder.rewrite_image_refs(
        md, {'a.png': 'https://cdn/x/a.png', 'b.jpg': 'https://cdn/x/b.jpg'})
    assert '![](https://cdn/x/a.png)' in out
    assert '![说明](https://cdn/x/b.jpg)' in out
    assert 'images/' not in out
    assert missing == []


def test_rewrite_image_refs_reports_missing_and_keeps_original():
    out, missing = builder.rewrite_image_refs('![](images/gone.png)', {})
    assert missing == ['gone.png']
    assert '![](images/gone.png)' in out


def test_rewrite_image_refs_leaves_absolute_urls_alone():
    md = '![](https://already/abs.png)'
    out, missing = builder.rewrite_image_refs(md, {'abs.png': 'https://cdn/abs.png'})
    assert out == md
    assert missing == []


# --------------------------------------------------------------------------- 文件名

def test_build_source_file_name_strips_host_suffix():
    name = builder.build_source_file_name(
        'TikTok Shop', '美国ACCU', '[TikTok Shop官方社群]美区跨境POP ACCU开店攻略 - 飞书云文档')
    assert '飞书云文档' not in name
    assert name.startswith('美国ACCU ')


def test_build_source_file_name_does_not_double_prefix_site():
    name = builder.build_source_file_name('TikTok Shop', '英国', 'TikTok Shop英国跨境POP入驻攻略')
    assert name.count('英国') == 1


def test_build_source_file_name_skips_prefix_for_generic_site():
    name = builder.build_source_file_name('Noon', '通用', 'noon入驻指南笔记')
    assert name == 'noon入驻指南笔记'


# --------------------------------------------------------------------------- 任务载荷

class _Args(object):
    client = 'payoneer_olive'
    index_name = 'payoneer_olive'
    user = 'payoneer_olive_admin'
    bucket = 'boot-admin'
    knowledge_objective = '只抽取平台官方入驻与运营规则'
    context_cache_ttl_days = 30
    review_only = False
    need_translate = False   # 默认不翻译；英文源文档由 --need-translate 打开


def _payload():
    record = {'platform': 'TikTok Shop', 'site': '美国ACCU',
              'source_url': 'https://x/docx/a', 'char_count': 3843}
    meta = {'title': 'ACCU 开店攻略 - 飞书云文档'}
    upload = {'md_key': 'p/o/content.md', 'image_count': 18, 'missing_images': []}
    return builder.build_task_payload(record, meta, upload, _Args(),
                                      'TikTok Shop-美国ACCU', '21')


def test_build_task_payload_enables_context_enrichment():
    """用户要的是「带检索和历史对话优化」那条流程，这三个开关是它的定义。"""
    info = _payload()['task_info']
    assert info['enable_context_enrichment'] is True
    assert info['enable_chat_query_context'] is True
    assert info['enable_web_context'] is False          # 网络检索必须保持关闭
    assert info['quality_profile'] == 'business_task_knowledge'


def test_build_task_payload_carries_category_and_file():
    info = _payload()['task_info']
    assert info['category_name'] == 'TikTok Shop-美国ACCU'
    assert info['category_id'] == '21'
    assert info['files'][0]['store_method'] == 'minio'
    assert info['files'][0]['ext'] == 'md'
    assert info['files'][0]['address'] == 'p/o/content.md'


def test_build_task_payload_business_context_mentions_platform_and_site():
    info = _payload()['task_info']
    assert 'TikTok Shop' in info['business_context_text']
    assert '美国ACCU' in info['business_context_text']


# --------------------------------------------------------------------------- 清单筛选

def _manifest(tmp_path, docs):
    path = tmp_path / 'crawl_manifest.json'
    path.write_text(json.dumps({'docs': docs}, ensure_ascii=False), encoding='utf-8')
    return str(path)


def _make_doc_dir(tmp_path, name):
    doc_dir = tmp_path / name
    doc_dir.mkdir(parents=True)
    (doc_dir / 'content.md').write_text('正文', encoding='utf-8')
    (doc_dir / 'meta.json').write_text(json.dumps({'title': name}), encoding='utf-8')
    return str(doc_dir)


def test_load_crawled_docs_skips_non_ok_status(tmp_path):
    ok_dir = _make_doc_dir(tmp_path, 'ok_doc')
    path = _manifest(tmp_path, [
        {'platform': 'P', 'site': 'S1', 'status': 'ok', 'dir': ok_dir},
        {'platform': 'P', 'site': 'S2', 'status': 'need_login'},
        {'platform': 'P', 'site': 'S3', 'status': 'unsupported'},
    ])
    docs = builder.load_crawled_docs(path)
    assert [r['site'] for r, _ in docs] == ['S1']


def test_load_crawled_docs_accepts_skipped_existing(tmp_path):
    """skipped_existing 表示盘上已有内容，是可投递的，不能被当成失败漏掉。"""
    doc_dir = _make_doc_dir(tmp_path, 'cached_doc')
    path = _manifest(tmp_path, [
        {'platform': 'P', 'site': 'S1', 'status': 'skipped_existing', 'dir': doc_dir}])
    assert len(builder.load_crawled_docs(path)) == 1


def test_load_crawled_docs_skips_missing_content_file(tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()
    path = _manifest(tmp_path, [
        {'platform': 'P', 'site': 'S1', 'status': 'ok', 'dir': str(empty)}])
    with pytest.raises(ValueError):
        builder.load_crawled_docs(path)


# --- 子链接：site 是 URL slug 而不是站点名 -----------------------------------

def test_is_display_site_rejects_url_slug():
    """子链接的 site 是 URL 派生的 slug，塞进文档名/业务背景里就是噪音。"""
    assert not builder.is_display_site(
        'bytedance_sg_larkoffice_com_docx_PmmFdbhwOog32nx07K5lqamaguc')
    assert not builder.is_display_site(
        'seller_id_tokopedia_com_university_essay_knowledge_id_745338')
    assert not builder.is_display_site('通用')
    assert not builder.is_display_site('')


def test_is_display_site_keeps_real_site_names():
    for name in ('美国ACCU', '东南亚', '全托管', '欧盟(西德意法)', '墨西哥'):
        assert builder.is_display_site(name), name


def test_source_file_name_drops_slug_but_keeps_site_name():
    assert builder.build_source_file_name(
        'TikTok Shop-印尼', 'seller_id_tokopedia_com_university_essay_knowledge_id_745338',
        '品牌授权资质要求 - 飞书云文档') == '品牌授权资质要求'
    assert builder.build_source_file_name(
        'TikTok Shop', '美国ACCU', '入驻手册 - 飞书云文档') == '美国ACCU 入驻手册'


def test_business_context_appends_anchor_note():
    """锚文本说明了这篇子链接在父文档里是干什么的，比 slug 有信息量。"""
    text = builder.build_business_context_text(
        'TikTok Shop-印尼', 'seller_id_tokopedia_com_university_essay_x', '品牌授权说明',
        '子链接，父文档=TikTok Shop/印尼，锚文本=品牌授权资质要求')
    assert 'seller_id_tokopedia' not in text
    assert '锚文本=品牌授权资质要求' in text
    assert '《品牌授权说明》' in text


def test_need_translate_off_by_default_and_on_by_flag():
    """英文源文档要显式开翻译，别指望抽取模型顺手译。

    实测 Bol 英文材料在 need_translate=0 时，92% 靠模型自己译了、8% 保留英文标题
    （如 'What are the benefits of Logistics via bol...'），中文 query 检索不到。
    """
    assert _payload()['task_info']['need_translate'] == 0

    class _ArgsTranslate(_Args):
        need_translate = True

    record = {'platform': 'Bol', 'site': '荷兰',
              'source_url': 'https://x/docx/b', 'char_count': 1200}
    payload = builder.build_task_payload(
        record, {'title': 'Logistics via bol'},
        {'md_key': 'p/o/c.md', 'image_count': 0, 'missing_images': []},
        _ArgsTranslate(), 'Bol-荷兰', '22')
    assert payload['task_info']['need_translate'] == 1
