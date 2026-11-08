from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本地爬下来的在线文档投递成 `document_qa_segment_mining` 任务（带业务上下文增强）。

衔接的是 `knowledge_crawler_tool/web_crawl/login_doc_crawler.py` 的产物：
`data/<client>/<平台>/<站点>/{content.md, images/, meta.json}`。

为什么走 MinIO 而不是直接喂本地路径：
`document_qa_segment_mining` 的阶段1固定用 `MinioDownloader` 拉文件，没有本地文件通道；
而且任务跑在 `main` 上，本机的文件它看不到。MinIO 是这条链路设计好的输入口，不用改流程代码。

为什么每篇文档一个任务：
`category_id` / `category_name` 是**任务级**字段（`document_qa_segment_mining.py:60-62`），
一个任务只能挂一个类目。而这批文档要按站点分别挂到 `TikTok Shop-<站点>` 下，所以一篇一个任务。

图片处理：
`parse_txt_to_json`（`knowledge_clear_tool/wordtotext.py:436`）认 markdown 图片语法，
http 图片会被下载到本地再进多模态 OCR。所以上传前要把 `images/xxx.png` 这种**相对引用
改写成 MinIO 公网 URL**，否则解析阶段找不到文件，图片里的信息（后台路径、字段名）就全丢了。

用法::

    # 1) 只上传 + 生成任务载荷，不投递（默认）
    python3 data_control_tools/build_doc_mining_tasks.py \
        --manifest data/payoneer_olive/crawl_manifest.json \
        --client payoneer_olive --index-name payoneer_olive \
        --work-dir output/payoneer_olive_doc_mining_20260807

    # 2) 投递单篇试跑
    python3 data_control_tools/build_doc_mining_tasks.py ... --only "美国ACCU" --submit

    # 3) 全量投递
    python3 data_control_tools/build_doc_mining_tasks.py ... --submit
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time

PROJECT_ROOT = str(_PROJECT_ROOT)

LOGGER = logging.getLogger('build_doc_mining_tasks')

DEFAULT_SERVICE_URL = 'http://120.77.147.247:6000'
DEFAULT_MINIO_CONFIG = os.path.join(PROJECT_ROOT, 'config', 'minio_config.json')
DEFAULT_BUCKET = 'boot-admin'
# md 走 S3 API 由任务侧拉取，不需要公开读；但正文里的图片是被 HTTP 下载的，必须走这个公网网关
PUBLIC_GATEWAY = 'https://file.marsmind.cc'

CATEGORY_TREE_URL = ('https://admin.marsmind.cc/api/rufit-ai/intranet/knowledge/'
                     'qaCategory/tree?client={client}')

_MD_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\((images/[^)]+)\)')
_SLUG_RE = re.compile(r'[^0-9a-zA-Z]+')

# 抽取目标：这批文档是平台官方攻略，噪音主要是社群招募话术、协作留言、目录导航
DEFAULT_KNOWLEDGE_OBJECTIVE = (
    '只抽取跨境电商平台官方的入驻与运营规则类知识：入驻资质与主体要求、注册与认证流程、'
    '所需材料清单、店铺与类目规则、禁限售、费用与结算、物流与履约时效、后台操作步骤、'
    '常见问题处理办法。'
    '拒绝：社群招募与活动话术（加群、领礼包、限时名额）、目录/导航式罗列、纯链接堆砌、'
    '文档协作留言（“待补充”“已更新”“@某某请确认”）、与具体某个卖家或工单绑定的个案信息。'
)


def setup_logging(verbose=False):
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)


def load_crawled_docs(manifest_path):
    """从 crawl_manifest.json 挑出真正落盘成功的文档，返回 [(record, meta)]。"""
    with open(manifest_path, 'r', encoding='utf-8') as fin:
        manifest = json.load(fin)
    root = os.path.dirname(os.path.abspath(manifest_path))
    docs = []
    for record in manifest.get('docs') or []:
        # skipped_existing 也是「盘上有内容」，need_login / unsupported / failed 才是真没有
        if record.get('status') not in ('ok', 'skipped_existing'):
            LOGGER.warning('跳过 %s/%s：status=%s',
                           record.get('platform'), record.get('site'), record.get('status'))
            continue
        doc_dir = record.get('dir')
        if doc_dir and not os.path.isabs(doc_dir):
            doc_dir = os.path.join(PROJECT_ROOT, doc_dir)
        if not doc_dir or not os.path.exists(os.path.join(doc_dir, 'content.md')):
            LOGGER.warning('跳过 %s/%s：content.md 不存在（%s）',
                           record.get('platform'), record.get('site'), doc_dir)
            continue
        with open(os.path.join(doc_dir, 'meta.json'), 'r', encoding='utf-8') as fin:
            meta = json.load(fin)
        meta['_dir'] = doc_dir
        docs.append((record, meta))
    if not docs:
        raise ValueError('manifest 里没有可用文档：%s' % manifest_path)
    return docs


def slugify(text, fallback='doc'):
    """生成 ASCII 安全的对象键片段。

    中文会被整段剥掉（`英国`/`东南亚`/`印尼` 都会变成空），所以空串时必须退回**内容相关的哈希**，
    不能退回一个固定字符串——否则这些站点的对象键会撞在一起互相覆盖。
    """
    slug = _SLUG_RE.sub('_', (text or '')).strip('_').lower()
    if slug:
        return slug
    if not text:
        return fallback
    return '%s_%s' % (fallback, hashlib.md5(text.encode('utf-8')).hexdigest()[:8])


def flatten_category_tree(nodes, prefix=''):
    """把类目树压成 {完整路径: category_id}，路径用 `-` 连接（和类目系统的层级分隔符一致）。"""
    mapping = {}
    for node in nodes or []:
        name = node.get('categoryName')
        if not name:
            continue
        path = '%s-%s' % (prefix, name) if prefix else name
        mapping[path] = str(node.get('categoryId'))
        mapping.update(flatten_category_tree(node.get('children'), path))
    return mapping


def load_category_map(client, timeout=20):
    """拉线上类目树，返回 {完整路径: category_id}。"""
    import requests

    resp = requests.get(CATEGORY_TREE_URL.format(client=client), timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get('code') != '00000':
        raise RuntimeError('拉类目树失败：%s' % payload.get('msg'))
    return flatten_category_tree(payload.get('data'))


def resolve_category(platform, site, category_map):
    """站点有二级类目就挂到二级，否则挂平台一级类目。找不到直接报错，不静默落到默认分组。"""
    for candidate in ('%s-%s' % (platform, site), platform):
        if candidate in category_map:
            return candidate, category_map[candidate]
    raise KeyError('类目里找不到 %s / %s，先建类目再投递' % (platform, site))


def rewrite_image_refs(markdown, image_url_map):
    """把 `![](images/x.png)` 换成公网 URL；映射里没有的原样保留并记一笔。"""
    missing = []

    def _sub(match):
        alt, rel = match.group(1), match.group(2)
        name = os.path.basename(rel)
        url = image_url_map.get(name)
        if not url:
            missing.append(name)
            return match.group(0)
        return '![%s](%s)' % (alt, url)

    return _MD_IMAGE_RE.sub(_sub, markdown), missing


def upload_doc_assets(minio, doc_dir, key_prefix, bucket, upload_dir, upload_images=True):
    """上传图片 + 改写后的 markdown，返回 {md_key, md_name, image_count, missing_images}。"""
    with open(os.path.join(doc_dir, 'content.md'), 'r', encoding='utf-8') as fin:
        markdown = fin.read()

    image_url_map = {}
    images_dir = os.path.join(doc_dir, 'images')
    if upload_images and os.path.isdir(images_dir):
        for name in sorted(os.listdir(images_dir)):
            local = os.path.join(images_dir, name)
            if not os.path.isfile(local):
                continue
            key = '%s/images/%s' % (key_prefix, name)
            if not minio.upload_file(local, key, bucket_name=bucket):
                raise RuntimeError('图片上传失败：%s' % local)
            image_url_map[name] = '%s/%s/%s' % (PUBLIC_GATEWAY, bucket, key)

    rewritten, missing = rewrite_image_refs(markdown, image_url_map)
    if missing:
        LOGGER.warning('%s 有 %d 张图没对上本地文件，正文里保留原引用', doc_dir, len(missing))

    os.makedirs(upload_dir, exist_ok=True)
    local_md = os.path.join(upload_dir, '%s.md' % os.path.basename(key_prefix))
    with open(local_md, 'w', encoding='utf-8') as fout:
        fout.write(rewritten)

    md_key = '%s/content.md' % key_prefix
    if not minio.upload_file(local_md, md_key, bucket_name=bucket):
        raise RuntimeError('markdown 上传失败：%s' % local_md)
    return {'md_key': md_key, 'local_md': local_md,
            'image_count': len(image_url_map), 'missing_images': missing}


_URL_SLUG_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{15,}$')


def is_display_site(site):
    """`site` 有时是人看的站点名（`美国ACCU`），有时是 URL 派生的 slug
    （`bytedance_sg_larkoffice_com_docx_Pmm...`）。后者塞进文档名和业务背景里就是噪音，
    还会被当成"站点名"喂给 LLM。所以只有像人话的才拿来展示。"""
    site = (site or '').strip()
    if not site or site == '通用':
        return False
    # 站点名是中文短词（`美国ACCU`/`东南亚`）；slug 是长串 ASCII + 下划线，没有中文也没有空格
    return not _URL_SLUG_RE.match(site)


def build_business_context_text(platform, site, title, note=None):
    """给 LLM 的业务背景。写清楚"这是什么文档、读者是谁"，让它抽的是规则而不是活动话术。"""
    scope = '%s %s 站点' % (platform, site) if is_display_site(site) else platform
    extra = ''
    if note:
        extra = '%s。' % note.strip().rstrip('。')
    return (
        '本文是 Payoneer 橄榄枝计划（跨境卖家入驻绿色通道）为中国跨境卖家整理/转载的'
        '%s 官方入驻与运营攻略，标题《%s》。'
        '读者是正准备入驻或已入驻该平台的中国跨境卖家及其对接的招商/客户经理。'
        '文中的后台截图、材料清单、费用与时效说明是核心知识；'
        '文中穿插的加群邀请、限时活动、权益礼包属于运营话术，不是知识。%s'
        % (scope, title or '', extra)
    )


_TITLE_SUFFIX_RE = re.compile(r'\s*[-—]\s*(飞书云文档|企业微信文档|腾讯文档)\s*$')


def build_source_file_name(platform, site, title):
    """`files[].name` 会落到 `ext_info.from_file_name`，后续软删/对账都按它匹配。

    所以要：去掉宿主平台的尾巴（" - 飞书云文档"），并带上站点让同平台多篇文档不会混。
    """
    clean = _TITLE_SUFFIX_RE.sub('', (title or '').strip())
    if not clean:
        clean = '%s %s' % (platform, site)
    if is_display_site(site) and site not in clean:
        clean = '%s %s' % (site, clean)
    return clean[:120]


def build_task_payload(record, meta, upload_info, args, category_name, category_id):
    """拼 document_qa_segment_mining 的 task_info。"""
    platform, site = record['platform'], record['site']
    title = meta.get('title') or '%s %s' % (platform, site)
    note = meta.get('note')
    return {
        'task_type': 'document_qa_segment_mining',
        'task_info': {
            'client': args.client,
            'index_name': args.index_name,
            'user': args.user,
            'files': [{
                'name': build_source_file_name(platform, site, title),
                'ext': 'md',
                'store_method': 'minio',
                'bucket_name': args.bucket,
                'address': upload_info['md_key'],
            }],
            'category_name': category_name,
            'category_id': category_id,
            # 英文源文档要开翻译，否则抽出来的 QA 标题会中英混杂：
            # 实测 Bol 英文材料在 need_translate=0 时，92% 靠抽取模型自己顺手译了、
            # 8% 保留英文标题（如 'What are the benefits of Logistics via bol...'），
            # 中文 query 检索不到。语言不该指望模型顺带处理，要显式声明。
            'need_translate': 1 if args.need_translate else 0,
            # ==== 上下文增强（用户要的「带检索和历史对话优化」的那条流程）====
            'enable_context_enrichment': True,
            'enable_chat_query_context': True,   # 从 data_chat_history 提炼该客户真实高频意图
            'enable_web_context': False,         # 网络检索保持关闭，避免把网上内容当文档事实
            'context_cache_ttl_days': args.context_cache_ttl_days,
            'quality_profile': 'business_task_knowledge',
            'knowledge_objective': args.knowledge_objective,
            'business_context_text': build_business_context_text(platform, site, title, note),
            'review_only': bool(args.review_only),
        },
        '_meta': {
            'platform': platform, 'site': site, 'title': title,
            'source_url': record.get('source_url'),
            'char_count': record.get('char_count'),
            'image_count': upload_info['image_count'],
            'md_key': upload_info['md_key'],
        },
    }


def submit_task(service_url, payload, timeout=60):
    """投递到任务服务，返回 (task_id, 原始响应)。"""
    import requests

    body = {'task_type': payload['task_type'], 'task_info': payload['task_info']}
    resp = requests.post('%s/start_task' % service_url.rstrip('/'), json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    task_id = (data.get('data') or {}).get('task_id') if isinstance(data.get('data'), dict) else None
    return task_id, data


def run(args):
    from kdb.shared.storage.minio import MinioTools

    docs = load_crawled_docs(args.manifest)
    if args.only:
        wanted = {x.strip() for x in args.only.split(',') if x.strip()}
        docs = [(r, m) for r, m in docs
                if r['site'] in wanted or '%s/%s' % (r['platform'], r['site']) in wanted]
        if not docs:
            raise ValueError('--only 没匹配到任何文档：%s' % args.only)

    category_map = load_category_map(args.client)
    minio = MinioTools(config=args.minio_config)
    os.makedirs(args.work_dir, exist_ok=True)
    upload_dir = os.path.join(args.work_dir, 'upload')

    payloads = []
    for record, meta in docs:
        platform, site = record['platform'], record['site']
        tag = '%s/%s' % (platform, site)
        category_name, category_id = resolve_category(platform, site, category_map)
        key_prefix = '%s/%s_%s' % (args.key_prefix, slugify(platform, 'platform'),
                                   slugify(site, 'site'))
        LOGGER.info('上传 %s -> %s（类目 %s / %s）', tag, key_prefix, category_name, category_id)
        upload_info = upload_doc_assets(minio, meta['_dir'], key_prefix, args.bucket,
                                        upload_dir, upload_images=not args.no_images)
        payload = build_task_payload(record, meta, upload_info, args, category_name, category_id)
        payloads.append(payload)
        LOGGER.info('  已上传：md=%s 图片=%d', upload_info['md_key'], upload_info['image_count'])

    tasks_path = os.path.join(args.work_dir, 'tasks.json')
    with open(tasks_path, 'w', encoding='utf-8') as fout:
        json.dump(payloads, fout, ensure_ascii=False, indent=1)
    LOGGER.info('任务载荷已写出：%s（%d 篇）', tasks_path, len(payloads))

    if not args.submit:
        LOGGER.info('未加 --submit，只做了上传和载荷生成，没有投递任务')
        return payloads

    submitted = []
    for payload in payloads:
        tag = '%s/%s' % (payload['_meta']['platform'], payload['_meta']['site'])
        try:
            task_id, raw = submit_task(args.service_url, payload)
            payload['_meta']['task_id'] = task_id
            payload['_meta']['submit_response'] = raw
            LOGGER.info('投递成功 %s -> task_id=%s', tag, task_id)
        except Exception as exc:                                   # noqa: BLE001
            payload['_meta']['submit_error'] = '%s: %s' % (type(exc).__name__, exc)
            LOGGER.error('投递失败 %s：%s', tag, exc)
        submitted.append(payload)
        time.sleep(args.submit_interval)

    with open(tasks_path, 'w', encoding='utf-8') as fout:
        json.dump(submitted, fout, ensure_ascii=False, indent=1)
    return submitted


def main(argv=None):
    parser = argparse.ArgumentParser(description='把爬下来的在线文档投递成文档挖掘任务')
    parser.add_argument('--manifest', required=True, help='login_doc_crawler 产出的 crawl_manifest.json')
    parser.add_argument('--client', required=True)
    parser.add_argument('--index-name', required=True)
    parser.add_argument('--user', default='')
    parser.add_argument('--work-dir', required=True)
    parser.add_argument('--key-prefix', default='payoneer_olive/doc_crawl',
                        help='MinIO 对象键前缀')
    parser.add_argument('--bucket', default=DEFAULT_BUCKET)
    parser.add_argument('--minio-config', default=DEFAULT_MINIO_CONFIG)
    parser.add_argument('--service-url', default=DEFAULT_SERVICE_URL)
    parser.add_argument('--only', help='只处理指定文档，逗号分隔，站点名或 "平台/站点"')
    parser.add_argument('--knowledge-objective', dest='knowledge_objective',
                        default=DEFAULT_KNOWLEDGE_OBJECTIVE)
    parser.add_argument('--context-cache-ttl-days', type=int, default=30)
    parser.add_argument('--need-translate', action='store_true',
                        help='源文档是外文时开启，把正文翻成中文再抽 QA')
    parser.add_argument('--no-images', action='store_true', help='不上传图片（正文保留原相对引用）')
    parser.add_argument('--review-only', action='store_true', help='任务只产审核文件，不写 ES')
    parser.add_argument('--submit', action='store_true', help='真正投递任务，默认只上传+生成载荷')
    parser.add_argument('--submit-interval', type=float, default=2.0)
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    payloads = run(args)
    failed = [p for p in payloads if p['_meta'].get('submit_error')]
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
