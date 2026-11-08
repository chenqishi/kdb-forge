from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登录态在线文档爬取器（飞书 docx/wiki、企微文档、腾讯文档）。

和 `web_batch_crawler.py` 的分工：
- `web_batch_crawler.py` 面向**公开站点的广度爬取**（selenium + chromedriver + BFS 展开链接）。
- 本脚本面向**清单驱动的在线文档**：数量少、需要登录态、正文是虚拟滚动渲染的富文本。

技术选型说明（不要随手改回 selenium）：
- 走 playwright 的 `connect_over_cdp`，连一个**已经起好的 Chrome 调试实例**。
  这样既复用该实例里的登录态，也绕开 chromedriver 与 Chrome 大版本必须匹配的问题。
- Chrome 136+ 起，`--remote-debugging-port` 在**默认 user-data-dir** 上会被忽略，
  所以调试实例必须显式带一个独立的 `--user-data-dir`。

正文提取的核心是**虚拟滚动**：飞书 docx 只渲染视口内的块，一次性取 innerText 会漏。
做法是每滚动一屏采集一次当前 DOM 里的块，用块 id 去重、用块相对滚动容器的绝对偏移排序，
连续若干轮没有新块且滚动到底才停。

用法::

    # 1) 起调试实例（独立 profile，首次需要在窗口里手工登录需要登录的站点）
    open -na "Google Chrome" --args \
        --user-data-dir="$HOME/.cache/chrome-doc-crawl" --remote-debugging-port=9222

    # 2) 探测（只打印结构与字数，不落盘）
    python3 knowledge_crawler_tool/web_crawl/login_doc_crawler.py \
        --manifest knowledge_crawler_tool/data/payoneer_olive_doc_urls.json --probe-only

    # 3) 全量爬取
    python3 knowledge_crawler_tool/web_crawl/login_doc_crawler.py \
        --manifest knowledge_crawler_tool/data/payoneer_olive_doc_urls.json --download-images
"""

import argparse
import base64
import collections
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime

PROJECT_ROOT = str(_PROJECT_ROOT)

LOGGER = logging.getLogger('login_doc_crawler')

DEFAULT_CDP_URL = 'http://127.0.0.1:9222'

# 每类文档宿主的滚动容器 / 块选择器。都是实测出来的，不要凭猜测新增。
DOC_PROFILES = {
    'lark': {
        'scroll_selector': '.bear-web-x-container',
        'block_selector': '[data-block-id]',
        'id_attr': 'data-block-id',
        'type_attr': 'data-block-type',
        'ready_selector': '[data-block-type="page"]',
    },
    # 企微文档和腾讯文档同一套引擎，正文同样画在 <canvas class="surface"> 上，DOM 抓不到。
    # 但它的 dop-api/opendoc 返回的是**明文 JSON**（不是 protobuf），比腾讯文档好解得多。
    # 需要登录态，所以走浏览器里的 fetch；图片靠滚动页面时截获响应。
    'wecom': {
        'scroll_selector': '#scrollable',
        'block_selector': None,
        'id_attr': None,
        'type_attr': None,
        'ready_selector': None,
        'extractor': 'wecom_api',
    },
    # 普通网页（卖家大学 / 帮助中心 / 公众号文章）：不是虚拟滚动的富文本应用，
    # 一次渲染完就能取全，但要先框定正文容器，否则会把导航栏、页脚、侧边目录一起抓进来。
    # 下面这些候选选择器都是实测出来的（见 docs/payoneer_olive_sublink_crawl.md）：
    #   TikTok 卖家大学（seller-us / tokopedia / seller-mx / eu 四个域名同模板）→ article.article-main
    #   seller.tiktokglobalshop.com → div[class*=articleDetailLayout]
    #   global-selling.mercadolibre.com → main / .page-content
    #   mp.weixin.qq.com → .rich_media_area_primary
    # 匹配不到就退回「页面上文本最长的那个容器」。
    'web': {
        'scroll_selector': None,
        'block_selector': None,
        'id_attr': None,
        'type_attr': None,
        'ready_selector': None,
        'extractor': 'web_article',
        'content_selectors': [
            'article.article-main', '.content-inner',
            '[class*=articleDetailLayout]', '[class*=contentWrapper]',
            '.rich_media_area_primary', '.page-content', 'main', 'article',
        ],
    },

    # 飞书表格（/sheets/）：和腾讯文档一样是 canvas 渲染，DOM 里 0 个 <table>，抓不到。
    # 出路是「框选全表复制」——飞书自己会把选区写成 TSV 放进剪贴板，读剪贴板即可拿到全表。
    # 实测「印尼行业资质对照表」这样能拿到 27.8 万字（三级类目 + 限制/定邀标记 + 所需资质）。
    'lark_sheet': {
        'scroll_selector': None,
        'block_selector': None,
        'id_attr': None,
        'type_attr': None,
        'ready_selector': None,
        'extractor': 'lark_sheet_clipboard',
    },

    # 在线 PDF 阅读器（doc.weixin.qq.com/pdf/、docs.qq.com/pdf/）：正文画在 canvas 上，
    # DOM 里只有「撤销/重做/缩略图」这类工具栏文字。但页面自己会分片请求 PDF 字节
    # （content-type: application/pdf），截获这些响应就能拼回原始文件，不用反解接口。
    # 拿到 PDF 后交给仓库已有的 parse_pdf_to_json（PyMuPDF）解析，不重复造轮子。
    'pdf': {
        'scroll_selector': None,
        'block_selector': None,
        'id_attr': None,
        'type_attr': None,
        'ready_selector': None,
        'extractor': 'pdf_capture',
    },

    # 腾讯文档正文是 canvas 渲染的，DOM 里只有无障碍占位文本，滚动采集拿不到任何内容。
    # 只能走页面自己 <link preload> 出来的 dop-api/opendoc，见 fetch_tencent_doc_via_api。
    'tencent': {
        'scroll_selector': None,
        'block_selector': None,
        'id_attr': None,
        'type_attr': None,
        'ready_selector': None,
        'extractor': 'tencent_api',
    },
}

TENCENT_DOC_ID_RE = re.compile(r'/doc/([A-Za-z0-9_-]+)')
TENCENT_OPENDOC_URL = (
    'https://docs.qq.com/dop-api/opendoc?u=&id={doc_id}&normal=1&outformat=1&noEscape=1'
    '&commandsFormat=1&doc_chunk_version=3&preview_token=&doc_chunk_flag=1'
)
# 正文是 protobuf 打包后再 base64 的，没有公开的解码库。
# 这里只从解码后的字节流里捞连续的可打印/中日韩 UTF-8 片段，够拿到全部文字（会丢层级和表格结构）。
_UTF8_RUN_RE = re.compile(
    rb'(?:[\x20-\x7e]|[\xe0-\xef][\x80-\xbf]{2}|[\xc2-\xdf][\x80-\xbf]|[\xf0-\xf4][\x80-\xbf]{3}){4,}'
)
# 腾讯文档在正文里塞的富文本控制串，不是给人看的内容
_TENCENT_CTRL_RE = re.compile(
    r'^(HYPERLINK\s|normalLink\b|\\td[a-z]+\b|[0-9a-f]{6,}$)'
)
# 这个文档是从 Word 导入的，blob 里正文之后紧跟着整张 Word 样式表 + 图片资源清单。
# 正文一定在最前面，所以扫到第一条样式表特征行就截断，后面的全是元数据。
_TENCENT_META_FONTS = (
    '微软雅黑', '宋体', '黑体', '等线', '仿宋', '楷体', '雅黑', '苹方', 'PingFang', 'SimSun',
    'Microsoft YaHei', 'Calibri', 'Times New Roman', 'Helvetica', 'Segoe UI',
    'Tahoma', 'Verdana', 'Wingdings', 'Courier New', 'Consolas',
)
_TENCENT_META_RE = re.compile(
    r'^(p\.\d{10,}|[0-9A-F]{6,}|autoZ|pictureZ|descript)|schemas\.(microsoft|openxmlformats)\.'
)
_TENCENT_IMG_RE = re.compile(
    r'https://docimg\d*\.docs\.qq\.com/image/[A-Za-z0-9_\-]+\.(?:png|jpe?g|gif|webp)[^\s*"\']*'
)


def _is_tencent_metadata_line(line):
    text = (line or '').strip()
    for font in _TENCENT_META_FONTS:
        if text.startswith(font) and len(text) - len(font) <= 4:
            return True
    return bool(_TENCENT_META_RE.match(text))

# 目录名里必须去掉的字符：路径分隔符和会让 shell/文件系统出问题的符号。
# 中文、空格、括号都保留，因为平台目录名要和线上类目名严格一致。
_UNSAFE_DIR_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')

# 飞书/腾讯文档正文里塞了大量零宽字符用于光标定位（标题里还会塞 U+2060~U+2064 这类不可见符号），
# 必须清掉，否则字数统计、目录名和检索都会被污染。
_ZERO_WIDTH = re.compile(r'[​-‏‪-‮⁠-⁤⁪-⁯﻿]')


def clean_text(text):
    """去掉零宽/不可见字符并收拢空白。"""
    return _ZERO_WIDTH.sub('', text or '').strip()

_MD_MARKS = re.compile(r'^(#{1,9}\s+|[-*]\s+|\d+\.\s+|>\s+|```.*$)')

# 表格单元格里的图片占位符，由 HARVEST_JS 的 tableToMd 写入，落盘时换成相对引用
_IMG_TOKEN_RE = re.compile(r'⟦IMG:(.+?)⟧')

# 采集一轮当前视口内的块。返回 [{key, top, type, text, md, images, leaf}]
HARVEST_JS = r"""
(cfg) => {
  const container = cfg.scrollSelector ? document.querySelector(cfg.scrollSelector) : null;
  const root = container || document.body;
  const cRect = root.getBoundingClientRect();
  const scrollTop = container ? container.scrollTop : window.scrollY;

  const clean = (s) => (s || '').replace(/[​‌‍﻿]/g, '');

  // 表格单元格里常常放的是操作截图（"第1步/第2步"三列各一张图）。
  // 只取 innerText 的话这些图两头都不出：单元格是空的，而表格的后代块又被标记成已消费。
  // 所以把单元格里的图片就地写成占位符，落盘时再换成本地文件名，位置就不会丢。
  const imgToken = (im) => {
    const src = im.currentSrc || im.src;
    if (!src || src.startsWith('data:')) return '';
    const w = im.naturalWidth || im.width || 0, h = im.naturalHeight || im.height || 0;
    if (w < 120 || h < 60) return '';
    return '⟦IMG:' + src + '⟧';
  };

  const tableToMd = (el) => {
    const rows = Array.from(el.querySelectorAll('tr'));
    if (!rows.length) return clean(el.innerText);
    const lines = [];
    rows.forEach((tr, i) => {
      const cells = Array.from(tr.querySelectorAll('td,th')).map(td => {
        let s = clean(td.innerText).replace(/\n+/g, ' ').replace(/\|/g, '\\|').trim();
        const toks = Array.from(td.querySelectorAll('img')).map(imgToken).filter(Boolean);
        if (toks.length) s = (s ? s + ' ' : '') + toks.join(' ');
        return s;
      });
      lines.push('| ' + cells.join(' | ') + ' |');
      if (i === 0) lines.push('| ' + cells.map(() => '---').join(' | ') + ' |');
    });
    return lines.join('\n');
  };

  // 正文里的超链接（官方入驻通道、政策页、子文档）是关键信息，只取 innerText 会全丢掉，
  // 所以把块内锚点回填成 markdown 链接。
  const withLinks = (el, md) => {
    if (!md) return md;
    const anchors = Array.from(el.querySelectorAll('a[href]'));
    for (const a of anchors) {
      const href = a.href || '';
      if (!/^https?:/.test(href)) continue;
      const label = clean(a.innerText).replace(/\n+/g, ' ').trim();
      if (!label || label.length < 2) continue;
      if (md.indexOf('](' + href + ')') >= 0) continue;
      if (label === href || md.indexOf(href) >= 0) continue;
      const idx = md.indexOf(label);
      if (idx < 0) continue;
      md = md.slice(0, idx) + '[' + label + '](' + href + ')' + md.slice(idx + label.length);
    }
    return md;
  };

  const blockMd = (el, type, text) => {
    const h = /^heading(\d)$/.exec(type || '');
    if (h) return '#'.repeat(Math.min(6, parseInt(h[1], 10))) + ' ' + text.replace(/\s*\n+\s*/g, ' ');
    if (type === 'table') return tableToMd(el);
    // 列表块的 innerText 会把渲染出来的项目符号也带上（"•\n正文"），要剥掉再套 markdown 标记
    const li = (s) => s.replace(/^\s*[•◦▪·‣⁃]\s*/, '').replace(/^\s*\d+[.、)]\s*/, '')
                       .replace(/^\s*\n+/, '').replace(/\n+/g, ' ').trim();
    if (type === 'bullet') return '- ' + li(text);
    if (type === 'ordered') return '1. ' + li(text);
    if (type === 'todo') return '- [ ] ' + li(text);
    if (type === 'code') return '```\n' + text + '\n```';
    if (type === 'quote' || type === 'quote_container' || type === 'callout') {
      return text.split('\n').map(l => '> ' + l).join('\n');
    }
    if (type === 'divider') return '---';
    return text;
  };

  const out = [];
  const consumed = new Set();
  const nodes = Array.from(root.querySelectorAll(cfg.blockSelector));

  // 先把 table 的后代标记为已消费，避免表格单元格又被当成独立块输出一遍
  nodes.forEach(el => {
    const type = cfg.typeAttr ? el.getAttribute(cfg.typeAttr) : null;
    if (type === 'table') {
      el.querySelectorAll(cfg.blockSelector).forEach(d => {
        const k = cfg.idAttr ? d.getAttribute(cfg.idAttr) : null;
        if (k) consumed.add(k);
      });
    }
  });

  nodes.forEach(el => {
    const key = cfg.idAttr ? el.getAttribute(cfg.idAttr) : null;
    if (!key || consumed.has(key)) return;
    const type = cfg.typeAttr ? el.getAttribute(cfg.typeAttr) : null;
    // 容器块（内部还有块）本身不产出文本，交给它的子块，否则内容会重复
    const isContainer = type !== 'table' && el.querySelector(cfg.blockSelector) !== null;
    const text = clean(el.innerText).replace(/\n{3,}/g, '\n\n').trim();
    // 只算「属于自己这一块」的图：否则容器块会把所有后代块的图再输出一遍，正文里全是重复图。
    // 例外是 table：它的后代块已经被标记成已消费，图片只能由表格块自己收，否则整表的图全丢。
    // 另外表情贴纸/头像这类小图是界面噪音，抓下来只会污染多模态阶段
    const images = Array.from(el.querySelectorAll('img'))
      .filter(i => type === 'table' || i.closest(cfg.blockSelector) === el)
      .filter(i => (i.naturalWidth || i.width || 0) >= 120 && (i.naturalHeight || i.height || 0) >= 60)
      .map(i => i.currentSrc || i.src)
      .filter(s => s && !s.startsWith('data:'));
    if (isContainer && !images.length) {
      return;
    }
    if (!text && !images.length) return;
    const r = el.getBoundingClientRect();
    out.push({
      key: key,
      top: Math.round(r.top - cRect.top + scrollTop),
      type: type || '',
      text: text,
      md: isContainer ? '' : withLinks(el, blockMd(el, type, text)),
      images: images,
    });
  });
  return {
    blocks: out,
    scrollTop: Math.round(scrollTop),
    scrollHeight: Math.round(container ? container.scrollHeight : document.documentElement.scrollHeight),
    clientHeight: Math.round(container ? container.clientHeight : window.innerHeight),
  };
}
"""

# 普通网页正文提取：按 DOM 顺序把标题/段落/列表/表格/图片转成块，供 blocks_to_markdown 组装。
WEB_ARTICLE_JS = r"""
(cfg) => {
  const clean = (s) => (s || '').replace(/[\u200b\u200c\u200d\ufeff]/g, '').trim();

  // 先按候选选择器找正文容器，都没命中就退回「文本最长的容器」
  let root = null;
  for (const sel of cfg.selectors) {
    const el = document.querySelector(sel);
    if (el && (el.innerText || '').trim().length > 200) { root = el; break; }
  }
  if (!root) {
    let best = null, bestLen = 0;
    document.querySelectorAll('article,main,section,div').forEach(el => {
      const t = (el.innerText || '').trim();
      // 取「自身文本够长且不含更长子容器」的那个，避免选到整个 body
      if (t.length > bestLen && t.length > 200 && el.children.length < 400) { best = el; bestLen = t.length; }
    });
    root = best || document.body;
  }

  const imgToken = (im) => {
    const src = im.currentSrc || im.src;
    if (!src || src.startsWith('data:')) return '';
    const w = im.naturalWidth || im.width || 0, h = im.naturalHeight || im.height || 0;
    if (w < 120 || h < 60) return '';
    return '\u27e6IMG:' + src + '\u27e7';
  };

  const tableToMd = (el) => {
    const rows = Array.from(el.querySelectorAll('tr'));
    if (!rows.length) return clean(el.innerText);
    const lines = [];
    rows.forEach((tr, i) => {
      const cells = Array.from(tr.querySelectorAll('td,th')).map(td => {
        let s = clean(td.innerText).replace(/\n+/g, ' ').replace(/\|/g, '\\|');
        const toks = Array.from(td.querySelectorAll('img')).map(imgToken).filter(Boolean);
        if (toks.length) s = (s ? s + ' ' : '') + toks.join(' ');
        return s;
      });
      lines.push('| ' + cells.join(' | ') + ' |');
      if (i === 0) lines.push('| ' + cells.map(() => '---').join(' | ') + ' |');
    });
    return lines.join('\n');
  };

  const SEL = 'h1,h2,h3,h4,h5,h6,p,li,pre,blockquote,table,img';
  const out = [];
  let idx = 0;
  const consumed = new Set();
  root.querySelectorAll('table').forEach(t => t.querySelectorAll(SEL).forEach(e => consumed.add(e)));

  root.querySelectorAll(SEL).forEach(el => {
    if (consumed.has(el)) return;
    const tag = el.tagName.toLowerCase();
    let md = '', images = [];
    if (tag === 'table') {
      md = tableToMd(el);
      images = Array.from(el.querySelectorAll('img')).map(i => i.currentSrc || i.src)
                    .filter(s => s && !s.startsWith('data:'));
    } else if (tag === 'img') {
      const tk = imgToken(el);
      if (!tk) return;
      images = [el.currentSrc || el.src];
    } else {
      const text = clean(el.innerText);
      if (!text) return;
      if (/^h[1-6]$/.test(tag)) md = '#'.repeat(parseInt(tag[1], 10)) + ' ' + text.replace(/\s*\n+\s*/g, ' ');
      else if (tag === 'li') md = '- ' + text.replace(/\n+/g, ' ');
      else if (tag === 'pre') md = '```\n' + text + '\n```';
      else if (tag === 'blockquote') md = text.split('\n').map(l => '> ' + l).join('\n');
      else md = text;
      // 段落里内嵌的图也要留住位置
      const toks = Array.from(el.querySelectorAll('img')).map(imgToken).filter(Boolean);
      if (toks.length) md = md + ' ' + toks.join(' ');
      images = Array.from(el.querySelectorAll('img')).map(i => i.currentSrc || i.src)
                    .filter(s => s && !s.startsWith('data:'));
    }
    if (!md && !images.length) return;
    out.push({key: 'w' + (idx++), top: idx, type: tag, text: clean(el.innerText), md: md, images: images});
  });
  return {blocks: out, rootSel: root.tagName + '.' + (root.className || '').toString().slice(0, 40)};
}
"""

# 在页面里把图片取成 dataURL，作为「截获浏览器图片响应」之外的兜底。
# 主要用于 blob: 这种没有网络请求可截的场景。
# 必须带 credentials，否则飞书的图床直链会返回 401（<img> 自己发的请求是带 cookie 的）。
FETCH_IMAGES_JS = r"""
async (srcs) => {
  const out = {};
  for (const s of srcs) {
    try {
      const r = await fetch(s, {credentials: 'include'});
      if (!r.ok) { out[s] = 'ERR:http_' + r.status; continue; }
      const b = await r.blob();
      out[s] = await new Promise((res, rej) => {
        const fr = new FileReader();
        fr.onload = () => res(fr.result);
        fr.onerror = () => rej(new Error('read_fail'));
        fr.readAsDataURL(b);
      });
    } catch (e) {
      out[s] = 'ERR:' + (e && e.message ? e.message : 'unknown');
    }
  }
  return out;
}
"""

_EXT_BY_MIME = {
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/svg+xml': '.svg',
    'image/bmp': '.bmp',
}


def setup_logging(verbose=False):
    """统一配置根 logger。

    直接用 basicConfig 会因为导入链上已经装过 handler 而变成 no-op，所以显式替换。
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)


def load_url_manifest(path):
    """读取文档清单，返回 (root, [item...])。

    item 必须含 platform / site / url / doc_type。缺字段直接报错，
    因为目录结构和提取器都由这几个字段决定，静默跳过只会让人以为爬全了。
    """
    with open(path, 'r', encoding='utf-8') as fin:
        raw = json.load(fin)
    if isinstance(raw, list):
        docs, root = raw, None
    else:
        docs, root = raw.get('docs') or [], raw.get('root')
    if not docs:
        raise ValueError('清单里没有 docs：%s' % path)
    items = []
    for idx, doc in enumerate(docs):
        missing = [k for k in ('platform', 'site', 'url', 'doc_type') if not doc.get(k)]
        if missing:
            raise ValueError('清单第 %d 条缺字段 %s：%s' % (idx + 1, ','.join(missing), doc))
        if doc['doc_type'] not in DOC_PROFILES:
            raise ValueError('清单第 %d 条 doc_type 未知：%s' % (idx + 1, doc['doc_type']))
        items.append(dict(doc))
    disambiguate_sites(items)
    return root, items


def disambiguate_sites(items):
    """`(platform, site)` 决定落盘目录，撞名的后一篇会**直接覆盖**前一篇。

    子链接的 `site` 常是从 URL 截出来的 slug，几条只有 query 尾巴不同的链接
    （`.../essay?identity=1&role=1&knowledge_id=<各不相同>`）会截成同一个 slug。
    实测 57 条网页里 6 组撞名、8 篇被静默覆盖：日志条条 `status=ok`，
    盘上却少了 8 篇，只有对账时才会发现。

    这里给撞名的补一段 URL 短哈希，保证一篇一目录。原地改 items。
    """
    seen = {}
    for item in items:
        key = (item['platform'], item['site'])
        seen.setdefault(key, []).append(item)
    for (platform, site), group in seen.items():
        if len(group) < 2:
            continue
        LOGGER.warning('目录名撞车：%s/%s 有 %d 条，按 URL 哈希区分', platform, site, len(group))
        for item in group:
            suffix = hashlib.md5(item['url'].encode('utf-8')).hexdigest()[:8]
            item['site'] = '%s_%s' % (site, suffix)
    return items


def safe_dir_name(name):
    """把一个平台名/站点名转成安全的目录名，保留中文、空格、括号。"""
    cleaned = _UNSAFE_DIR_CHARS.sub('_', (name or '').strip())
    cleaned = cleaned.strip('. ')
    cleaned = re.sub(r'^\.+', '', cleaned)
    return cleaned or '_'


def build_doc_dir(root, platform, site):
    """<root>/<平台>/<站点>/，并保证不会因为站点名里带 ../ 而逃出 root。"""
    doc_dir = os.path.join(root, safe_dir_name(platform), safe_dir_name(site))
    root_abs = os.path.abspath(root)
    doc_abs = os.path.abspath(doc_dir)
    if not (doc_abs == root_abs or doc_abs.startswith(root_abs + os.sep)):
        raise ValueError('目录逃出 root：%s' % doc_dir)
    return doc_dir


def merge_blocks(collected, new_blocks):
    """把一轮采集到的块并进累积结果。

    同一个块在多轮里会重复出现（滚动有重叠），按 key 去重；
    但块的 md/images 可能在后面几轮才加载完（图片懒加载），所以用"内容更全的那份"覆盖。
    返回本轮新增的块数。
    """
    added = 0
    for blk in new_blocks:
        key = blk['key']
        old = collected.get(key)
        if old is None:
            collected[key] = blk
            added += 1
            continue
        if len(blk.get('md') or '') > len(old.get('md') or ''):
            old['md'] = blk['md']
            old['text'] = blk['text']
        if len(blk.get('images') or []) > len(old.get('images') or []):
            old['images'] = blk['images']
        old['top'] = min(old['top'], blk['top'])
    return added


def ordered_blocks(collected):
    """按块在文档中的绝对位置排序，位置相同再按 key 稳定排序。"""
    return sorted(collected.values(), key=lambda b: (b['top'], str(b['key'])))


def scroll_and_harvest(page, profile, on_step=None, step_ratio=0.7,
                       settle_ms=700, max_rounds=400, stagnant_limit=4):
    """滚到底并逐屏采集块，返回 (blocks, stats)。

    停止条件是"连续 stagnant_limit 轮既没有新块、滚动位置也不再前进"，
    只看 scrollTop 到底会漏掉底部懒加载的内容。
    """
    cfg = {
        'scrollSelector': profile['scroll_selector'],
        'blockSelector': profile['block_selector'],
        'idAttr': profile['id_attr'],
        'typeAttr': profile['type_attr'],
    }
    collected = {}
    stagnant = 0
    rounds = 0
    last_top = -1
    scroll_height = 0
    while rounds < max_rounds:
        rounds += 1
        res = page.evaluate(HARVEST_JS, cfg)
        added = merge_blocks(collected, res['blocks'])
        scroll_height = res['scrollHeight']
        if on_step is not None:
            on_step(res['blocks'])
        at_bottom = res['scrollTop'] + res['clientHeight'] >= res['scrollHeight'] - 5
        if added == 0 and res['scrollTop'] == last_top:
            stagnant += 1
        elif added == 0 and at_bottom:
            stagnant += 1
        else:
            stagnant = 0
        if stagnant >= stagnant_limit:
            break
        last_top = res['scrollTop']
        step = max(200, int(res['clientHeight'] * step_ratio))
        page.evaluate(
            """(a) => { const c = a.sel ? document.querySelector(a.sel) : null;
                        if (c) { c.scrollTop += a.step; } else { window.scrollBy(0, a.step); } }""",
            {'sel': profile['scroll_selector'], 'step': step},
        )
        page.wait_for_timeout(settle_ms)
    stats = {'rounds': rounds, 'scroll_height': scroll_height, 'block_count': len(collected)}
    return ordered_blocks(collected), stats


def fetch_images(page, srcs):
    """在页面上下文里把图片取成 dataURL，返回 {src: dataurl_or_ERR}。"""
    if not srcs:
        return {}
    return page.evaluate(FETCH_IMAGES_JS, list(srcs))


def _image_file_name(src, mime):
    ext = _EXT_BY_MIME.get((mime or '').split(';')[0].strip(), '.bin')
    return hashlib.md5(src.encode('utf-8')).hexdigest()[:16] + ext


def decode_data_url(src, data_url):
    """把 `fetch_images` 返回的 dataURL 转成统一的 {'data','mime'} / {'error'} 结构。"""
    if not data_url or str(data_url).startswith('ERR:'):
        return {'error': data_url or 'empty'}
    try:
        header, payload = data_url.split(',', 1)
        mime = re.match(r'^data:([^;,]*)', header).group(1)
        raw = base64.b64decode(payload)
    except Exception as exc:                                       # noqa: BLE001
        return {'error': 'decode_fail:%s' % exc}
    if not raw:
        return {'error': 'empty_body'}
    return {'data': raw, 'mime': mime}


def save_images(image_results, out_dir):
    """把图片字节落盘，返回 (src -> 相对文件名) 和失败列表。

    image_results: {src: {'data': bytes, 'mime': str}} 或 {src: {'error': str}}
    """
    saved, failed = {}, []
    if not image_results:
        return saved, failed
    os.makedirs(out_dir, exist_ok=True)
    for src, item in image_results.items():
        raw = (item or {}).get('data')
        if not raw:
            failed.append({'src': src, 'reason': (item or {}).get('error') or 'empty'})
            continue
        name = _image_file_name(src, (item or {}).get('mime'))
        with open(os.path.join(out_dir, name), 'wb') as fout:
            fout.write(raw)
        saved[src] = name
    return saved, failed


# 飞书/企微渲染出来的界面文案，不是文档内容，整行完全等于这些才丢，避免误伤正文
_UI_NOISE_LINES = {
    '本文暂未被其它文档引用',
    '本文档由 飞书文档 创建',
    '点击查看更多',
    '展开全部',
    '收起',
}


def _image_ref(src, image_map):
    local = (image_map or {}).get(src)
    return '![](images/%s)' % local if local else '![](%s)' % src


def blocks_to_markdown(blocks, image_map=None):
    """把有序块拼成 markdown；图片按 image_map 换成 images/<本地文件名> 相对引用。

    表格单元格里的图片是以 `⟦IMG:src⟧` 占位符就地保留的（见 HARVEST_JS 的 tableToMd），
    这里换成相对引用；已经在表格里出现过的图不再单独追加一行，避免同一张图重复。
    """
    image_map = image_map or {}
    lines = []
    for blk in blocks:
        md = clean_text(blk.get('md') or '')
        inlined = set(_IMG_TOKEN_RE.findall(md))
        if inlined:
            md = _IMG_TOKEN_RE.sub(lambda m: _image_ref(m.group(1), image_map), md)
        if md and md not in _UI_NOISE_LINES:
            lines.append(md)
        for src in blk.get('images') or []:
            if src in inlined:
                continue
            ref = _image_ref(src, image_map)
            # 同一张图连着出现多次是渲染重复，不是文档里真的贴了两遍
            if lines and lines[-1] == ref:
                continue
            lines.append(ref)
    return '\n\n'.join(lines).strip() + '\n'


def markdown_to_text(markdown):
    """去掉 markdown 标记，产出给下游挖掘用的纯文本。"""
    out = []
    in_code = False
    for line in markdown.splitlines():
        if line.strip().startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            out.append(line)
            continue
        if re.match(r'^!\[\]\(', line.strip()):
            continue
        if line.strip() == '---':
            continue
        out.append(_MD_MARKS.sub('', line))
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).strip() + '\n'


def write_doc_outputs(doc_dir, meta, blocks, image_map=None, page_html=None):
    """落 content.md / content.txt / page.html / meta.json / blocks.json。"""
    os.makedirs(doc_dir, exist_ok=True)
    markdown = blocks_to_markdown(blocks, image_map)
    plain = markdown_to_text(markdown)
    with open(os.path.join(doc_dir, 'content.md'), 'w', encoding='utf-8') as fout:
        fout.write(markdown)
    with open(os.path.join(doc_dir, 'content.txt'), 'w', encoding='utf-8') as fout:
        fout.write(plain)
    with open(os.path.join(doc_dir, 'blocks.json'), 'w', encoding='utf-8') as fout:
        json.dump(blocks, fout, ensure_ascii=False, indent=1)
    if page_html:
        with open(os.path.join(doc_dir, 'page.html'), 'w', encoding='utf-8') as fout:
            fout.write(page_html)
    meta = dict(meta)
    meta['char_count'] = len(plain)
    meta['markdown_char_count'] = len(markdown)
    meta['block_count'] = len(blocks)
    meta['image_count'] = len(image_map or {})
    with open(os.path.join(doc_dir, 'meta.json'), 'w', encoding='utf-8') as fout:
        json.dump(meta, fout, ensure_ascii=False, indent=1)
    return meta


def decode_tencent_attributed_text(chunks):
    """把 opendoc 返回的 base64 正文块解成文本行。

    腾讯文档的 initialAttributedText.text 是 protobuf 打包再 base64 的，没有公开解码库，
    所以只从字节流里提取连续的 UTF-8 文本片段。够拿到全部文字，但层级/表格结构会丢。
    """
    lines = []
    for chunk in chunks or []:
        if not isinstance(chunk, str):
            continue
        try:
            raw = base64.b64decode(chunk)
        except Exception:                                          # noqa: BLE001
            continue
        for run in _UTF8_RUN_RE.findall(raw):
            text = clean_text(run.decode('utf-8', 'ignore'))
            if not text or _TENCENT_CTRL_RE.match(text):
                continue
            lines.append(text)
    # 相邻重复行是同一段落被切成多个块导致的，去掉
    deduped = []
    for line in lines:
        if deduped and deduped[-1] == line:
            continue
        deduped.append(line)
    # 图片直链散落在正文之后的资源区，先全量捞出来再截断
    image_urls = []
    for line in deduped:
        for hit in _TENCENT_IMG_RE.findall(line):
            if hit not in image_urls:
                image_urls.append(hit)
    body = []
    for line in deduped:
        if _is_tencent_metadata_line(line):
            break
        body.append(line)
    return body, image_urls


def fetch_tencent_doc_via_api(url, timeout=30, download_images=True):
    """用页面自己的 dop-api/opendoc 拿腾讯文档正文，返回 (title, blocks, image_results)。

    先 GET 一次文档页拿匿名 cookie，否则 opendoc 直接 401。
    """
    import requests

    match = TENCENT_DOC_ID_RE.search(url)
    if not match:
        raise ValueError('识别不出腾讯文档 id：%s' % url)
    doc_id = match.group(1)
    session = requests.Session()
    session.headers.update({
        'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36'),
        'Referer': url,
    })
    session.get(url, timeout=timeout)
    resp = session.get(TENCENT_OPENDOC_URL.format(doc_id=doc_id), timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    client_vars = payload.get('clientVars') or {}
    collab = client_vars.get('collab_client_vars') or {}
    attributed = collab.get('initialAttributedText') or {}
    lines, image_urls = decode_tencent_attributed_text(attributed.get('text') or [])
    title = clean_text(client_vars.get('padTitle') or client_vars.get('initialTitle')
                       or (payload.get('bodyData') or {}).get('initialTitle') or '')
    blocks = [{'key': 'tencent-%d' % i, 'top': i, 'type': 'text', 'text': line,
               'md': line, 'images': []}
              for i, line in enumerate(lines)]
    # 图片在 blob 里的位置和正文对不上，只能作为附录整体附在文末，位置信息确实丢了
    image_results = {}
    if download_images and image_urls:
        for idx, img_url in enumerate(image_urls):
            blocks.append({'key': 'tencent-img-%d' % idx, 'top': len(lines) + idx,
                           'type': 'image', 'text': '', 'md': '', 'images': [img_url]})
            try:
                img_resp = session.get(img_url, timeout=timeout)
                if img_resp.status_code == 200 and img_resp.content:
                    image_results[img_url] = {
                        'data': img_resp.content,
                        'mime': img_resp.headers.get('content-type', ''),
                    }
                else:
                    image_results[img_url] = {'error': 'http_%s' % img_resp.status_code}
            except Exception as exc:                               # noqa: BLE001
                image_results[img_url] = {'error': '%s' % exc}
    return title, blocks, image_results


# --------------------------------------------------------------------------- 企微文档

WECOM_DOC_ID_RE = re.compile(r'/doc/(w\d+_[A-Za-z0-9_-]+)')
WECOM_SCODE_RE = re.compile(r'[?&]scode=([A-Za-z0-9_-]+)')
WECOM_OPENDOC_URL = (
    'https://doc.weixin.qq.com/dop-api/opendoc?scode={scode}&&u=null&doc_chunk_flag=0'
    '&id={doc_id}&normal=1&noEscape=1&outformat=1&preview_token='
)
# 正文里的富文本控制符（实测）：
#   \r        段落分隔
#   \x13..\x14 标签 \x15   超链接 / 文档引用 / @提及
#   \x08      图片占位
#   \x0f、\x1e 之后是评论区，不是正文
_WECOM_LINK_RE = re.compile('\x13(.*?)\x14(.*?)\x15', re.S)
_WECOM_URL_RE = re.compile(r'https?://[^\s\\]+')
_WECOM_CTRL_RE = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f]')
_WECOM_BODY_END = ('\x0f', '\x1e')
# 企微文档的正文配图在 wdcdn.qpic.cn；wework.qpic.cn 是 IM 头像（@提及带出来的），不是文档内容
_WECOM_AVATAR_HOST = 'wework.qpic.cn'
_WECOM_MIN_IMAGE_BYTES = 5000


def parse_wecom_attributed_text(text_items):
    """把企微文档 opendoc 的 commands 结构解成正文行，返回 (lines, image_placeholder_count)。"""
    chunks = []
    for item in text_items or []:
        if not isinstance(item, dict):
            continue
        for command in item.get('commands') or []:
            for mutation in command.get('mutations') or []:
                if mutation.get('ty') == 'is' and mutation.get('s'):
                    chunks.append(mutation['s'])
    raw = ''.join(chunks)
    # 评论区跟在正文后面，不截掉会把「@某某 这里需要补充」这类协作留言当成知识
    for marker in _WECOM_BODY_END:
        idx = raw.find(marker)
        if idx >= 0:
            raw = raw[:idx]
            break
    placeholder_count = raw.count('\x08')

    def _to_link(match):
        directive, label = match.group(1), (match.group(2) or '').strip()
        url_match = _WECOM_URL_RE.search(directive or '')
        if url_match and label:
            return '[%s](%s)' % (label, url_match.group(0))
        return label or (url_match.group(0) if url_match else '')

    raw = _WECOM_LINK_RE.sub(_to_link, raw)
    raw = _WECOM_CTRL_RE.sub('', raw)
    lines = [clean_text(x) for x in raw.split('\r')]
    return [x for x in lines if x], placeholder_count


def fetch_wecom_doc_via_browser(page, url, timeout=45000):
    """在已登录的页面上下文里调 opendoc 拿企微文档正文，返回 (title, lines, placeholder_count)。

    必须走浏览器 fetch：这个接口要登录态，脚本侧另起会话拿不到。
    """
    doc_match = WECOM_DOC_ID_RE.search(url)
    if not doc_match:
        raise ValueError('识别不出企微文档 id：%s' % url)
    scode_match = WECOM_SCODE_RE.search(url)
    api_url = WECOM_OPENDOC_URL.format(doc_id=doc_match.group(1),
                                       scode=scode_match.group(1) if scode_match else '')
    body = page.evaluate(
        """async (u) => {
             const r = await fetch(u, {credentials: 'include'});
             if (!r.ok) throw new Error('opendoc http ' + r.status);
             return await r.text();
           }""",
        api_url)
    payload = json.loads(body)
    client_vars = payload.get('clientVars') or {}
    collab = client_vars.get('collab_client_vars') or {}
    attributed = collab.get('initialAttributedText') or {}
    lines, placeholder_count = parse_wecom_attributed_text(attributed.get('text') or [])
    title = clean_text(client_vars.get('padTitle') or client_vars.get('initialTitle') or '')
    return title, lines, placeholder_count


def scroll_to_load_images(page, scroll_selector, rounds=60, settle_ms=500):
    """纯滚动（不采集），用来触发 canvas 文档把图片资源请求出来，配合 page.on('response') 截获。

    canvas 文档的滚动容器是渲染完才出现的，进页面就滚会滚了个寂寞：
    容器不存在时会退化成 window 滚动，而 body 本身不滚，第一轮就被判成「到底了」。
    所以先等容器出现，并且要求连续两轮到底才停。
    """
    if scroll_selector:
        try:
            page.wait_for_selector(scroll_selector, timeout=30000)
            # 容器是页面外壳的一部分，会先于正文出现；正文渲染完之前 scrollHeight == clientHeight，
            # 这时候滚会被判成「一进来就到底」，必须等到真的有得滚
            page.wait_for_function(
                """(sel) => { const c = document.querySelector(sel);
                              return !!c && c.scrollHeight > c.clientHeight + 200; }""",
                arg=scroll_selector, timeout=30000)
        except Exception:                                          # noqa: BLE001
            LOGGER.warning('滚动容器 %s 一直没撑开，图片可能抓不全', scroll_selector)
    # 企微文档会恢复上次的阅读位置：不归零的话一进来就在底部，循环立刻判定到底，一张图都截不到
    page.evaluate("""(sel) => { const c = sel ? document.querySelector(sel) : null;
                                if (c) { c.scrollTop = 0; } else { window.scrollTo(0, 0); } }""",
                  scroll_selector)
    page.wait_for_timeout(settle_ms)
    bottom_hits = 0
    for _ in range(rounds):
        at_bottom = page.evaluate(
            """(sel) => {
                 const c = sel ? document.querySelector(sel) : null;
                 if (!c) { window.scrollBy(0, window.innerHeight * 0.8);
                           return window.scrollY + window.innerHeight >= document.body.scrollHeight - 5; }
                 c.scrollTop += c.clientHeight * 0.8;
                 return c.scrollTop + c.clientHeight >= c.scrollHeight - 5;
               }""",
            scroll_selector)
        page.wait_for_timeout(settle_ms)
        bottom_hits = bottom_hits + 1 if at_bottom else 0
        if bottom_hits >= 2:
            break


def capture_pdf_bytes(page, url, settle_ms=12000):
    """截获在线 PDF 阅读器加载的字节流，拼回完整文件。

    页面是分片请求的（同一个 padid、不同 token），每片都是 `application/pdf`。
    取字节最多的那一片作为完整文件——实测分片里最大的那个就是整份 PDF，
    其余是缩略图/局部预取。
    """
    chunks = []

    def _on_response(resp):
        try:
            if resp.status != 200:
                return
            ctype = (resp.headers or {}).get('content-type', '')
            if 'pdf' not in ctype.lower():
                return
            body = resp.body()
            if body and body[:4] == b'%PDF':
                chunks.append(body)
        except Exception:  # noqa: BLE001
            pass

    page.on('response', _on_response)
    page.goto(url, wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(settle_ms)
    if not chunks:
        page.wait_for_timeout(settle_ms)
    return max(chunks, key=len) if chunks else None


def pdf_to_blocks(pdf_path, image_dir):
    """用 PyMuPDF 把 PDF 拆成块（正文 + 内嵌图）。

    不走 `knowledge_clear_tool.wordtotext.parse_pdf_to_json`：那个模块顶层还 import
    `docx` / `docx2pdf` 等 Office 转换依赖，只为解析 PDF 把它整个拉进来代价太大
    （实测本机就卡在 `ImportError: cannot import name 'Document' from 'docx'`）。
    这里只用 fitz，输出结构和本爬取器的块一致。
    """
    import fitz

    os.makedirs(image_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    blocks, image_map, idx = [], {}, 0
    try:
        for pno in range(doc.page_count):
            page = doc.load_page(pno)
            text = clean_text(page.get_text('text'))
            for para in [x.strip() for x in text.split('\n\n')] if '\n\n' in text else [text]:
                para = para.strip()
                if not para:
                    continue
                blocks.append({'key': 'p%d_%d' % (pno + 1, idx), 'top': idx, 'type': 'text',
                               'text': para, 'md': para, 'images': []})
                idx += 1
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    info = doc.extract_image(xref)
                except Exception:  # noqa: BLE001
                    continue
                raw, ext = info.get('image'), info.get('ext') or 'png'
                # 页眉页脚里的小图标不是知识，滤掉
                if not raw or len(raw) < 8000:
                    continue
                name = '%s.%s' % (hashlib.md5(raw).hexdigest()[:16], ext)
                path = os.path.join(image_dir, name)
                if not os.path.exists(path):
                    with open(path, 'wb') as fout:
                        fout.write(raw)
                image_map[path] = name
                blocks.append({'key': 'p%d_%d' % (pno + 1, idx), 'top': idx, 'type': 'image',
                               'text': '', 'md': '', 'images': [path]})
                idx += 1
        return blocks, doc.page_count, image_map
    finally:
        doc.close()


class CopyForbidden(Exception):
    """文档所有者关掉了复制权限——技术上无解，只能去要权限。"""


def _detect_copy_forbidden(page):
    """按下 Cmd+C 后飞书会弹「由于文档权限设置...」，据此把权限问题和技术故障分开。"""
    try:
        toasts = page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'[class*=toast],[class*=Toast],[class*=message],[class*=Message],[role=alert]'))"
            ".map(e => (e.innerText || '').trim()).filter(Boolean)")
    except Exception:  # noqa: BLE001
        return None
    for t in toasts or []:
        if '权限' in t and ('复制' in t or '导出' in t or '下载' in t):
            return t.split('\n')[0][:120]
    return None


def copy_sheet_via_clipboard(page, context, settle_ms=9000, retries=3):
    """飞书表格：点进表格区域 → 全选 → 复制 → 读剪贴板，拿到 TSV。

    表格是 canvas 画的，DOM 里没有 <table>，只能借飞书自己的复制能力。

    **复制前必须先清空剪贴板**：复制失败时读到的是上一张表的残留，
    实测 4 个不同表格全都拿到同一份内容（320375 字一模一样）——
    这种错比抓不到更危险，内容看着有，实际张冠李戴。
    所以写一个哨兵值进去，读回来还是哨兵就判定失败。
    """
    try:
        context.grant_permissions(['clipboard-read', 'clipboard-write'])
    except Exception:  # noqa: BLE001
        pass
    modifier = 'Meta' if sys.platform == 'darwin' else 'Control'
    sentinel = '__CLIPBOARD_EMPTY_%d__' % int(time.time() * 1000)
    page.wait_for_timeout(settle_ms)
    for attempt in range(retries):
        try:
            page.evaluate('(s) => navigator.clipboard.writeText(s)', sentinel)
            page.wait_for_timeout(300)
            box = page.viewport_size or {'width': 1280, 'height': 800}
            page.mouse.click(int(box['width'] * 0.5), int(box['height'] * 0.5))
            page.wait_for_timeout(900)
            page.keyboard.press('%s+A' % modifier)
            page.wait_for_timeout(900)
            page.keyboard.press('%s+C' % modifier)
            page.wait_for_timeout(3000)
            text = page.evaluate('navigator.clipboard.readText()')
            if text and text.strip() and sentinel not in text:
                return text
            forbid = _detect_copy_forbidden(page)
            if forbid:
                LOGGER.warning('文档禁止复制：%s', forbid)
                raise CopyForbidden(forbid)
            LOGGER.warning('表格复制未生效(%d/%d)，剪贴板仍是哨兵值', attempt + 1, retries)
            page.wait_for_timeout(2000)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning('表格复制失败(%d/%d): %s', attempt + 1, retries, exc)
            page.wait_for_timeout(2000)
    return None


SHEET_BLOCK_MAX_CHARS = 40000


def tsv_to_blocks(tsv, max_chars=SHEET_BLOCK_MAX_CHARS):
    """TSV -> markdown 表格块。大表按行切成多块，**每块重复表头**。

    不能整表一个块：下游 `parse_txt_to_json` 按元素分页，一个巨大元素就是一页，
    QA 生成和段落生成会把整页送给 Dify，撞上
    `paragraph must be less than 128000 characters`（实测一张 32 万字的表两阶段全挂）。

    切块时表头必须跟着走——只有第一块带表头的话，后面几块的列就没有含义了。
    """
    rows = [r.split('\t') for r in (tsv or '').split('\n') if r.strip()]
    if not rows:
        return []
    width = max(len(r) for r in rows)

    def _line(row):
        cells = [clean_text(c).replace('|', '\\|') for c in row] + [''] * (width - len(row))
        return '| ' + ' | '.join(cells) + ' |'

    header = [_line(rows[0]), '| ' + ' | '.join(['---'] * width) + ' |']
    head_len = sum(len(x) + 1 for x in header)

    blocks, chunk, size = [], [], head_len
    for row in rows[1:]:
        line = _line(row)
        if chunk and size + len(line) + 1 > max_chars:
            blocks.append(header + chunk)
            chunk, size = [], head_len
        chunk.append(line)
        size += len(line) + 1
    if chunk or not blocks:
        blocks.append(header + chunk)

    return [{'key': 'sheet_%d' % i, 'top': i, 'type': 'table',
             'text': '\n'.join(lines), 'md': '\n'.join(lines), 'images': []}
            for i, lines in enumerate(blocks)]


def _finish_browser_doc(record, item, root, doc_dir_meta, title, blocks, stats,
                        image_results, page, probe_only, save_html, image_map_override=None):
    """浏览器路径的收尾：probe 直接返回统计，否则落盘并补齐 record。"""
    record.update({'title': title, 'scroll_height': stats['scroll_height'],
                   'rounds': stats['rounds']})
    if probe_only:
        markdown = blocks_to_markdown(blocks)
        record.update({'status': 'probed', 'block_count': len(blocks),
                       'char_count': len(markdown),
                       'head': markdown[:300], 'tail': markdown[-300:]})
        return record

    doc_dir = build_doc_dir(root, item['platform'], item['site'])
    if image_map_override is not None:
        # PDF 链路的图片已经由 parse_pdf_to_json 落到 images/ 了，不用再存一遍
        image_map, image_failed = image_map_override, []
    else:
        image_map, image_failed = save_images(image_results, os.path.join(doc_dir, 'images'))
    page_html = page.content() if save_html else None
    meta = {
        'platform': item['platform'],
        'site': item['site'],
        'doc_type': item['doc_type'],
        'source_url': item['url'],
        'title': title,
        'note': item.get('note', ''),
        'crawled_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'scroll_height': stats['scroll_height'],
        'harvest_rounds': stats['rounds'],
        'image_failed': image_failed,
        'html_snapshot_is_partial': True,
    }
    meta.update(doc_dir_meta or {})
    meta = write_doc_outputs(doc_dir, meta, blocks, image_map, page_html)
    record.update({'status': 'ok', 'dir': doc_dir, 'title': title,
                   'char_count': meta['char_count'], 'block_count': meta['block_count'],
                   'image_count': meta['image_count'],
                   'image_failed_count': len(image_failed)})
    return record


def connect_browser(playwright, cdp_url=DEFAULT_CDP_URL):
    """连上已经起好的 Chrome 调试实例。"""
    browser = playwright.chromium.connect_over_cdp(cdp_url)
    if not browser.contexts:
        raise RuntimeError('调试实例里没有 browser context：%s' % cdp_url)
    return browser


def is_login_page(page):
    """判断当前页是不是被打回了登录页。"""
    url = page.url or ''
    if 'accounts.feishu.cn' in url or '/accounts/page/login' in url:
        return True
    try:
        text = page.evaluate("() => (document.body.innerText || '').slice(0, 300)")
    except Exception:                                              # noqa: BLE001
        return False
    # 「没有权限访问」和登录页是两回事，但对爬取来说结果一样：拿不到正文，
    # 而且页面还能正常渲染出一堆界面文案，不识别就会被当成爬成功。
    markers = ('企业身份登录', '扫码登录', '请使用 飞书移动端', '登录后查看',
               '没有权限访问', '无权限访问', '无权限', '申请阅读权限', '申请访问')
    return any(m in text for m in markers)


def crawl_one(context, item, root, download_images=True, probe_only=False,
              nav_timeout=60000, settle_ms=700, save_html=True):
    """爬一篇文档，返回一条 manifest 记录。"""
    profile = DOC_PROFILES[item['doc_type']]
    record = {
        'platform': item['platform'],
        'site': item['site'],
        'doc_type': item['doc_type'],
        'source_url': item['url'],
        'status': 'pending',
    }

    if profile.get('extractor') == 'tencent_api':
        try:
            title, blocks, image_results = fetch_tencent_doc_via_api(
                item['url'], download_images=download_images)
            record['title'] = title
            if probe_only:
                markdown = blocks_to_markdown(blocks)
                record.update({'status': 'probed', 'block_count': len(blocks),
                               'char_count': len(markdown),
                               'head': markdown[:300], 'tail': markdown[-300:]})
                return record
            doc_dir = build_doc_dir(root, item['platform'], item['site'])
            image_map, image_failed = save_images(image_results, os.path.join(doc_dir, 'images'))
            meta = {
                'platform': item['platform'], 'site': item['site'],
                'doc_type': item['doc_type'], 'source_url': item['url'],
                'title': title, 'note': item.get('note', ''),
                'crawled_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'extractor': 'tencent_api',
                'image_failed': image_failed,
                'structure_note': '腾讯文档正文是 canvas 渲染，只能从 opendoc 的 protobuf 里提取文字：'
                                  '标题层级和表格结构会拍平；图片在 blob 里和正文位置对不上，'
                                  '统一附在文末，不代表它在原文中的位置',
            }
            meta = write_doc_outputs(doc_dir, meta, blocks, image_map)
            record.update({'status': 'ok', 'dir': doc_dir,
                           'char_count': meta['char_count'],
                           'block_count': meta['block_count'],
                           'image_count': meta['image_count'],
                           'image_failed_count': len(image_failed)})
            return record
        except Exception as exc:                                   # noqa: BLE001
            LOGGER.exception('%s/%s 腾讯文档抓取失败', item['platform'], item['site'])
            record['status'] = 'failed'
            record['error'] = '%s: %s' % (type(exc).__name__, exc)
            return record

    if not profile.get('block_selector') and not profile.get('extractor'):
        # 不能抛异常：一篇没配好选择器会把整批爬取带崩，其余文档白跑
        record['status'] = 'unsupported'
        record['error'] = ('doc_type=%s 的选择器还没探测出来，先用 --probe-dom 定选择器'
                           % item['doc_type'])
        LOGGER.warning('%s/%s 跳过：%s', item['platform'], item['site'], record['error'])
        return record
    page = context.new_page()
    # 图片直链需要 <img> 请求自带的 cookie/referer，从脚本里再发一次 fetch 往往 401。
    # 所以直接截获浏览器自己加载图片时的响应体，最省事也最不会被鉴权卡住。
    captured_images = {}

    def _on_response(resp):
        try:
            if resp.status != 200:
                return
            ctype = (resp.headers or {}).get('content-type', '')
            if not ctype.startswith('image/'):
                return
            captured_images[resp.url] = {'data': resp.body(), 'mime': ctype}
        except Exception:                                          # noqa: BLE001
            pass

    if download_images:
        page.on('response', _on_response)
    try:
        page.goto(item['url'], wait_until='domcontentloaded', timeout=nav_timeout)
        page.wait_for_timeout(3000)
        if is_login_page(page):
            record['status'] = 'need_login'
            record['error'] = '页面被打回登录/无权限：%s' % page.url[:160]
            return record
        if profile.get('ready_selector'):
            try:
                page.wait_for_selector(profile['ready_selector'], timeout=30000)
            except Exception:                                      # noqa: BLE001
                LOGGER.warning('%s/%s 等待 ready_selector 超时，继续尝试采集',
                               item['platform'], item['site'])
        title = clean_text(page.title())

        image_results = {}
        extra_meta = {}

        if profile.get('extractor') == 'lark_sheet_clipboard':
            tsv = copy_sheet_via_clipboard(page, context)
            if not tsv:
                record['status'] = 'failed'
                record['error'] = '表格复制为空（可能没选中表格区域或无权限）'
                return record
            title = clean_text(page.title()) or item['site']
            blocks = tsv_to_blocks(tsv)
            stats = {'rounds': 0, 'scroll_height': 0, 'block_count': len(blocks)}
            LOGGER.info('%s/%s 表格 %d 字，%d 行',
                        item['platform'], item['site'], len(tsv), len(blocks))
            return _finish_browser_doc(record, item, root,
                                       doc_dir_meta={'extractor': 'lark_sheet_clipboard',
                                                     'tsv_chars': len(tsv)},
                                       title=title, blocks=blocks, stats=stats,
                                       image_results={}, page=page,
                                       probe_only=probe_only, save_html=False)

        if profile.get('extractor') == 'pdf_capture':
            pdf_bytes = capture_pdf_bytes(page, item['url'])
            if not pdf_bytes:
                record['status'] = 'failed'
                record['error'] = '没有截获到 PDF 字节流（可能需要登录或页面结构变了）'
                return record
            doc_dir = build_doc_dir(root, item['platform'], item['site'])
            os.makedirs(doc_dir, exist_ok=True)
            pdf_path = os.path.join(doc_dir, 'source.pdf')
            with open(pdf_path, 'wb') as fout:
                fout.write(pdf_bytes)
            title = clean_text(page.title()) or item['site']
            blocks, npages, pdf_image_map = pdf_to_blocks(pdf_path, os.path.join(doc_dir, 'images'))
            stats = {'rounds': 0, 'scroll_height': 0, 'block_count': len(blocks)}
            LOGGER.info('%s/%s PDF %d KB，%d 页，%d 块',
                        item['platform'], item['site'], len(pdf_bytes) // 1024, npages, len(blocks))
            return _finish_browser_doc(record, item, root,
                                       doc_dir_meta={'extractor': 'pdf_capture',
                                                     'pdf_bytes': len(pdf_bytes),
                                                     'pdf_pages': npages,
                                                     'source_pdf': 'source.pdf'},
                                       title=title, blocks=blocks, stats=stats,
                                       image_results={}, page=page,
                                       probe_only=probe_only, save_html=False,
                                       image_map_override=pdf_image_map)

        if profile.get('extractor') == 'web_article':
            # 普通网页不是虚拟滚动应用，渲染完一次取全即可；但要先滚一遍触发懒加载图片
            scroll_to_load_images(page, None, rounds=20, settle_ms=400)
            res = page.evaluate(WEB_ARTICLE_JS, {'selectors': profile.get('content_selectors') or []})
            blocks = res['blocks']
            LOGGER.info('%s/%s 正文容器=%s，块数=%d',
                        item['platform'], item['site'], res.get('rootSel'), len(blocks))
            stats = {'rounds': 0, 'scroll_height': 0, 'block_count': len(blocks)}
            if download_images:
                wanted = list(dict.fromkeys(src for b in blocks for src in b.get('images') or []))
                for src in wanted:
                    if src in captured_images:
                        image_results[src] = captured_images[src]
                missing = [x for x in wanted if x not in image_results]
                for src, data_url in fetch_images(page, missing).items():
                    image_results[src] = decode_data_url(src, data_url)
                image_results = {x: image_results[x] for x in wanted if x in image_results}
            return _finish_browser_doc(record, item, root,
                                       doc_dir_meta={'extractor': 'web_article',
                                                     'content_root': res.get('rootSel')},
                                       title=title, blocks=blocks, stats=stats,
                                       image_results=image_results, page=page,
                                       probe_only=probe_only, save_html=save_html)

        if profile.get('extractor') == 'wecom_api':
            api_title, lines, placeholder_count = fetch_wecom_doc_via_browser(page, item['url'])
            title = api_title or title
            blocks = [{'key': 'wecom-%d' % i, 'top': i, 'type': 'text',
                       'text': line, 'md': line, 'images': []}
                      for i, line in enumerate(lines)]
            stats = {'rounds': 0, 'scroll_height': 0, 'block_count': len(blocks)}
            if download_images:
                # canvas 文档滚过去才会请求图片资源，滚一遍把 _on_response 喂饱
                scroll_to_load_images(page, profile.get('scroll_selector'))
                doc_images = {url: data for url, data in captured_images.items()
                              if _WECOM_AVATAR_HOST not in url
                              and len((data or {}).get('data') or b'') >= _WECOM_MIN_IMAGE_BYTES}
                for idx, img_url in enumerate(doc_images):
                    blocks.append({'key': 'wecom-img-%d' % idx, 'top': len(lines) + idx,
                                   'type': 'image', 'text': '', 'md': '', 'images': [img_url]})
                image_results = doc_images
            extra_meta = {
                'extractor': 'wecom_api',
                'image_placeholder_count': placeholder_count,
                'structure_note': '企微文档正文是 canvas 渲染，只能从 opendoc 的 commands 里提取文字：'
                                  '标题层级和表格结构会拍平；正文里有 %d 处图片占位，但占位和抓到的'
                                  '图片对不上号，图片统一附在文末，不代表它在原文中的位置；'
                                  '文末评论区已截掉' % placeholder_count,
            }
            record['image_placeholder_count'] = placeholder_count
            return _finish_browser_doc(record, item, root, doc_dir_meta=extra_meta, title=title,
                                       blocks=blocks, stats=stats, image_results=image_results,
                                       page=page, probe_only=probe_only, save_html=save_html)

        def _on_step(blocks):
            if not download_images:
                return
            # blob: URL 一旦滚出视口就可能被 revoke，必须在当前这一屏立刻取；
            # 普通直链等滚完再统一处理，避免拖慢滚动节奏。
            pending = [src for blk in blocks for src in blk.get('images') or []
                       if src.startswith('blob:') and src not in image_results]
            for src, data_url in fetch_images(page, pending).items():
                image_results[src] = decode_data_url(src, data_url)

        blocks, stats = scroll_and_harvest(page, profile, on_step=_on_step, settle_ms=settle_ms)
        # 飞书的 document.title 是渲染完才写进去的，进页面就取会拿到占位的 "Docs"
        late_title = clean_text(page.title())
        if late_title and late_title.lower() not in ('docs', 'loading'):
            title = late_title

        if download_images:
            wanted = [src for blk in blocks for src in blk.get('images') or []]
            wanted = list(dict.fromkeys(wanted))
            for src in wanted:
                if src not in image_results and src in captured_images:
                    image_results[src] = captured_images[src]
            missing = [s for s in wanted if s not in image_results]
            for src, data_url in fetch_images(page, missing).items():
                image_results[src] = decode_data_url(src, data_url)
            image_results = {s: image_results[s] for s in wanted if s in image_results}
        return _finish_browser_doc(record, item, root, doc_dir_meta={}, title=title,
                                   blocks=blocks, stats=stats, image_results=image_results,
                                   page=page, probe_only=probe_only, save_html=save_html)
    except Exception as exc:                                       # noqa: BLE001
        LOGGER.exception('%s/%s 爬取失败', item['platform'], item['site'])
        record['status'] = 'failed'
        record['error'] = '%s: %s' % (type(exc).__name__, exc)
        return record
    finally:
        try:
            page.close()
        except Exception:                                          # noqa: BLE001
            pass


def _browser_alive(browser):
    """调试实例还连得上吗。长批次里它会被关掉（内存压力或人手动关），
    不检测的话后续每一篇都会抛 TargetClosedError，整批白跑。"""
    try:
        return bool(browser.contexts) and browser.is_connected()
    except Exception:  # noqa: BLE001
        return False


def run_crawl(manifest_path, root=None, cdp_url=DEFAULT_CDP_URL, only=None,
              download_images=True, probe_only=False, skip_existing=False, settle_ms=700):
    """按清单跑一批文档，单篇失败不影响其余，最后写 crawl_manifest.json。"""
    from playwright.sync_api import sync_playwright

    manifest_root, items = load_url_manifest(manifest_path)
    root = root or manifest_root
    if not root:
        raise ValueError('没有指定 root，清单里也没有 root 字段')
    if only:
        wanted = {x.strip() for x in only.split(',') if x.strip()}
        items = [i for i in items
                 if '%s/%s' % (i['platform'], i['site']) in wanted or i['site'] in wanted]
        if not items:
            raise ValueError('--only 没有匹配到任何文档：%s' % only)

    records = []
    with sync_playwright() as playwright:
        browser = connect_browser(playwright, cdp_url)
        context = browser.contexts[0]
        for item in items:
            # 调试实例中途被关是常态（实测跑飞书文档的长批次里发生过两次）。
            # 断了就重连，别让剩下的全部陪葬——已完成的产物靠 --skip-existing 保住。
            if not _browser_alive(browser):
                LOGGER.warning('调试实例已断开，尝试重连 %s', cdp_url)
                reconnected = False
                for attempt in range(3):
                    time.sleep(3)
                    try:
                        browser = connect_browser(playwright, cdp_url)
                        context = browser.contexts[0]
                        reconnected = True
                        LOGGER.info('重连成功，继续')
                        break
                    except Exception as exc:  # noqa: BLE001
                        LOGGER.warning('重连失败(%d/3): %s', attempt + 1, exc)
                if not reconnected:
                    LOGGER.error('调试实例连不上，剩余 %d 篇未处理；重启实例后加 --skip-existing 续跑',
                                 len(items) - len(records))
                    break
            tag = '%s/%s' % (item['platform'], item['site'])
            if skip_existing and not probe_only:
                doc_dir = build_doc_dir(root, item['platform'], item['site'])
                if os.path.exists(os.path.join(doc_dir, 'content.md')):
                    LOGGER.info('跳过已存在：%s', tag)
                    record = {'platform': item['platform'], 'site': item['site'],
                              'doc_type': item['doc_type'], 'source_url': item['url'],
                              'status': 'skipped_existing', 'dir': doc_dir}
                    # 把上次的统计补进来，否则 crawl_manifest 里这些条目只有一个状态，没法验收
                    try:
                        with open(os.path.join(doc_dir, 'meta.json'), 'r', encoding='utf-8') as fin:
                            prev = json.load(fin)
                        for key in ('title', 'char_count', 'block_count', 'image_count', 'crawled_at'):
                            if key in prev:
                                record[key] = prev[key]
                    except Exception:                              # noqa: BLE001
                        LOGGER.warning('%s 的 meta.json 读不到，manifest 里只记状态', tag)
                    records.append(record)
                    continue
            LOGGER.info('开始爬取：%s -> %s', tag, item['url'])
            started = time.time()
            record = crawl_one(context, item, root, download_images=download_images,
                               probe_only=probe_only, settle_ms=settle_ms)
            record['elapsed_sec'] = round(time.time() - started, 1)
            LOGGER.info('完成：%s status=%s chars=%s images=%s %.1fs', tag, record['status'],
                        record.get('char_count'), record.get('image_count'), record['elapsed_sec'])
            records.append(record)

    if not probe_only:
        os.makedirs(root, exist_ok=True)
        out_path = os.path.join(root, 'crawl_manifest.json')
        write_crawl_manifest(out_path, records, manifest_path)
    return records


def write_crawl_manifest(out_path, records, manifest_path):
    """把本轮结果**合并**进已有清单，不是覆盖。

    同一个 root 会被多份清单先后爬（比如子链接分成「网页」和「文档」两批），
    直接覆盖会把上一批的 57 条抹掉，只剩本批的 29 条——盘上文件都在，
    下游按清单投递却只看到一小半，而且没有任何报错。踩过一次。

    合并键是 `(platform, site)`，本轮结果覆盖同一篇的旧记录。
    """
    old = []
    if os.path.exists(out_path):
        try:
            with open(out_path, 'r', encoding='utf-8') as fin:
                old = (json.load(fin) or {}).get('docs') or []
        except Exception as exc:                                       # noqa: BLE001
            LOGGER.warning('旧清单读不出来，本轮从空开始：%s', exc)
    merged = collections.OrderedDict(
        ((d.get('platform'), d.get('site')), d) for d in old)
    for rec in records:
        merged[(rec.get('platform'), rec.get('site'))] = rec
    sources = []
    for d in merged.values():
        src = d.get('_source_manifest') or manifest_path
        d['_source_manifest'] = src
        if src not in sources:
            sources.append(src)
    payload = {'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
               'source_manifest': sources if len(sources) > 1 else manifest_path,
               'docs': list(merged.values())}
    with open(out_path, 'w', encoding='utf-8') as fout:
        json.dump(payload, fout, ensure_ascii=False, indent=1)
    LOGGER.info('写出 %s（本轮 %d 条，合计 %d 条）',
                out_path, len(records), len(merged))
    return payload


def probe_dom(cdp_url, url, nav_timeout=60000):
    """打开一个 URL，dump 滚动容器候选和块结构，用来给新宿主定选择器。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = connect_browser(playwright, cdp_url)
        context = browser.contexts[0]
        page = context.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=nav_timeout)
            page.wait_for_timeout(5000)
            info = page.evaluate(r"""() => {
              const scrollables = [];
              document.querySelectorAll('*').forEach(el => {
                if (el.scrollHeight > el.clientHeight + 200 && el.clientHeight > 200) {
                  scrollables.push({tag: el.tagName, cls: (el.className||'').toString().slice(0,120),
                                    id: el.id || '', sh: el.scrollHeight, ch: el.clientHeight});
                }
              });
              const attrCount = {};
              document.querySelectorAll('*').forEach(el => {
                for (const a of el.attributes) {
                  if (/^data-/.test(a.name)) attrCount[a.name] = (attrCount[a.name]||0)+1;
                }
              });
              return {
                url: location.href, title: document.title,
                bodyTextHead: (document.body.innerText||'').slice(0,400),
                bodyTextLen: (document.body.innerText||'').length,
                scrollables: scrollables.slice(0, 12),
                dataAttrs: Object.entries(attrCount).sort((a,b)=>b[1]-a[1]).slice(0, 25),
                imgCount: document.querySelectorAll('img').length,
              };
            }""")
            return info
        finally:
            try:
                page.close()
            except Exception:                                      # noqa: BLE001
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description='登录态在线文档爬取器')
    parser.add_argument('--manifest', help='文档清单 JSON')
    parser.add_argument('--root', help='输出根目录，默认取清单里的 root')
    parser.add_argument('--cdp-url', default=DEFAULT_CDP_URL, help='Chrome 调试实例地址')
    parser.add_argument('--only', help='只跑指定文档，逗号分隔，形如 "TikTok Shop/英国" 或 "英国"')
    parser.add_argument('--download-images', action='store_true', help='下载正文图片')
    parser.add_argument('--probe-only', action='store_true', help='只采集不落盘，打印字数与首尾片段')
    parser.add_argument('--probe-dom', help='对单个 URL dump DOM 结构，用于给新宿主定选择器')
    parser.add_argument('--skip-existing', action='store_true', help='已有 content.md 的目录跳过')
    parser.add_argument('--settle-ms', type=int, default=700, help='每次滚动后的等待毫秒')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    if args.probe_dom:
        info = probe_dom(args.cdp_url, args.probe_dom)
        print(json.dumps(info, ensure_ascii=False, indent=1))
        return 0

    if not args.manifest:
        parser.error('需要 --manifest 或 --probe-dom')

    records = run_crawl(args.manifest, root=args.root, cdp_url=args.cdp_url, only=args.only,
                        download_images=args.download_images, probe_only=args.probe_only,
                        skip_existing=args.skip_existing, settle_ms=args.settle_ms)
    print(json.dumps(records, ensure_ascii=False, indent=1))
    bad = [r for r in records if r['status'] not in ('ok', 'probed', 'skipped_existing')]
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
