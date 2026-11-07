from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
自动学习 QA 的二次质量审核 —— 结合群聊上下文和同事名单，判断这条知识能不能留在 high。

和 2026-08-05 那轮 `relabel_qa_quality_by_llm.py` 的区别：那一轮**只看 Q/A**，
这一轮把 `ext_info.from_chat_history`（当时的群聊上下文）和应用配置里的
**同事名单（peer/teacher/management）**一起喂给模型，专门解决一类漏网的坏知识：

    Q: Bol-你能告诉我过去一年我们所有店铺的GMV和单店铺销售额吗？
    A: 额 过去一年我们所有店铺GMV大概是100W欧元左右。然后单店铺销售额最高大概是11W欧元左右。

答案是**卖家自己报的经营数据**，不是同事给的知识。只看 Q/A 很难判，
但看上下文就很清楚：这句话的说话人是卖家，不在同事名单里。

三个判定维度：
1. 是否跟业务相关（橄榄枝计划 = 帮卖家入驻/运营海外电商平台）
2. 是否通用（换个卖家换个店铺还成立，不是卖家的私人问题/私有数据）
3. 答案来源是不是同事/平台官方经理（**答案来自客户 → 不可信**）

范围：`from_type=chat_auto` + `data_type=qa` + `quality_level=high` + `audit_result=-1`（未审核过）。

用法：

    # 本机抽样 dry-run（硬盘小，别在本机拉全量）
    /usr/bin/python3 data_control_tools/audit_chat_auto_qa_by_llm.py \\
        --index payoneer_olive --client payoneer_olive \\
        --limit 50 --random-seed 20260827 --concurrency 4 \\
        --work-dir output/audit_chat_auto_sample_20260827

    # 线上机器全量 dry-run（先确认那台机器有 config/llm_config.json）
    ... --work-dir output/audit_chat_auto_20260827 --concurrency 8

    # 写回（复用同一 work-dir 的 decisions.jsonl，不重复烧 token）
    ... --execute

    # 回滚
    ... --rollback output/audit_chat_auto_20260827/rollback.jsonl --execute
"""

import argparse
import json
import logging
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = str(_PROJECT_ROOT)

from kdb.mining.quality.chat_qa_extract import load_llm_config  # noqa: E402
from kdb.mining.quality.chat_qa_extract import llm_client as cqe_llm_client  # noqa: E402
from kdb.mining.quality.chat_qa_extract.config import get_model  # noqa: E402
from kdb.shared.text import common_utils  # noqa: E402
from kdb.shared.clients.app_role_config import (extract_colleague_names,  # noqa: E402
                                     fetch_role_config)
from kdb.shared.clients.es_http_client import DEFAULT_BULK_BATCH, EsHttpClient  # noqa: E402

DEFAULT_ES_CONFIG = os.path.join(PROJECT_ROOT, 'config', 'config_es_engine.json')
DEFAULT_APP_ID = '2071478687539675137'

# 降级标签 → 档位。沿用 quality_tools/qa_quality_tools.py 的口径，
# 另加本轮新增的「答案来自客户」（同样是 low：来源不可信的内容不能进检索）。
LOW_TAGS = {'不相关', '无实质答案', '不通用', '答案来自客户'}
MID_TAGS = {'不清晰', '无法判断', '需要修改'}

# 说话人行：`昵称 : 内容` / `昵称: 内容`。昵称里可能带 @部门、括号后缀、空格，
# 但不会出现句子标点——不加这个限制，消息正文里换行后带冒号的一行
# （`通过Payoneer派安盈绿色通道快速入驻享受专属福利:`）会被当成说话人。
_SPEAKER_RE = re.compile(r'^([^\n。！？；，、"\'《》]{1,40}?)\s*[:：]\s', re.M)
_NORM_RE = re.compile(r'[^0-9a-z一-鿿]+')

# 答案与发言行的相似度门槛：低于此值认为没定位到答案出处
ANSWER_MATCH_THRESHOLD = 0.6

_write_lock = threading.Lock()


def normalize_name(text: str) -> str:
    return _NORM_RE.sub('', (text or '').lower())


def build_target_query(from_type: str = 'chat_auto', data_type: str = 'qa',
                       quality_level: str = 'high',
                       audit_results: Sequence[int] = (-1,),
                       random_seed: int = 0) -> Dict[str, Any]:
    """
    圈定待审 QA。

    **按 `from_type` 而不是 `from_type_norm`**：线上 `from_type_norm` 里没有 `chat_auto`，
    自动学习那批是 `auto_learning`(8060) + 历史遗留中文 `自动学习`(1127)，
    按 norm 过滤要么查不到、要么漏掉一千多条。
    """
    filters: List[Dict[str, Any]] = [
        {'term': {'del_flag': 0}},
        {'term': {'from_type': from_type}},
        {'term': {'data_type': data_type}},
        {'term': {'quality_level': quality_level}},
        {'terms': {'audit_result': list(audit_results)}},
    ]
    query: Dict[str, Any] = {'bool': {'filter': filters}}
    if random_seed:
        # 随机抽样：ES 的 random_score 需要指定 field，用 _seq_no 保证同 seed 可复现
        query = {'function_score': {
            'query': query,
            'random_score': {'seed': random_seed, 'field': '_seq_no'},
        }}
    return query


def download_docs(es: EsHttpClient, index: str, query: Dict[str, Any], output_file: str,
                  limit: int = 0, random_sample: bool = False) -> List[Dict[str, Any]]:
    """拉待审 QA；文件已存在则复用（断点续跑不重复拉）"""
    if os.path.exists(output_file):
        docs = _read_jsonl(output_file)
        logging.info('复用已下载文件 %s，共 %d 条', output_file, len(docs))
        return docs

    fields = ['title', 'content', 'quality_level', 'audit_result',
              'primary_category.category_path', 'ext_info.from_chat_history',
              'ext_info.from_file_name']
    rows: List[Tuple[str, Dict[str, Any]]] = []
    if random_sample:
        # random_score 打乱后取前 N，一次查询拿完（抽样量都不大，不需要分页）
        body = {'query': query, 'size': limit or 100, '_source': fields}
        for hit in es.search(index, body)['hits']['hits']:
            rows.append((hit['_id'], hit.get('_source') or {}))
    else:
        for did, src in es.iter_search_after(index, query, fields,
                                             limit=limit or None):
            rows.append((did, src))

    docs = []
    for did, src in rows:
        ext = src.get('ext_info') or {}
        docs.append({
            '_id': did,
            'title': src.get('title') or '',
            'content': src.get('content') or '',
            'old_level': src.get('quality_level') or '',
            'audit_result': src.get('audit_result'),
            'category': (src.get('primary_category') or {}).get('category_path') or '',
            'chat_history': ext.get('from_chat_history') or '',
            'chat_room': ext.get('from_file_name') or '',
        })
    _write_jsonl(output_file, docs)
    logging.info('下载完成 %d 条 → %s', len(docs), output_file)
    return docs


def annotate_chat_history(chat_history: str, answer: str,
                          colleague_names: Sequence[str]) -> Dict[str, Any]:
    """
    识别群聊里的说话人，标出同事，并猜答案出自谁。

    昵称匹配用「归一化后子串包含」：群昵称普遍是
    `Stacy Yao@橄榄枝计划 出差中回复慢` 这种带后缀的，精确相等匹配不上。
    """
    norm_peers = {normalize_name(n) for n in colleague_names if n and len(n) >= 2}
    norm_peers.discard('')

    lines: List[Tuple[str, str]] = []  # (说话人, 这句话)
    matches = list(_SPEAKER_RE.finditer(chat_history or ''))
    for idx, m in enumerate(matches):
        name = m.group(1).strip()
        if not name or '<' in name or '>' in name:
            continue
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(chat_history)
        lines.append((name, chat_history[m.end():end].strip()))

    stats: Dict[str, Dict[str, Any]] = {}
    for name, _ in lines:
        item = stats.setdefault(name, {'name': name, 'lines': 0,
                                       'is_colleague': _is_colleague(name, norm_peers)})
        item['lines'] += 1
    speakers = sorted(stats.values(), key=lambda x: -x['lines'])

    answer_speaker, best_score = '', 0.0
    norm_answer = (answer or '').strip()
    if norm_answer:
        for name, text in lines:
            if not text:
                continue
            score = common_utils.context_dice(norm_answer, text[:len(norm_answer) * 2 + 40])
            if score > best_score:
                answer_speaker, best_score = name, score
    if best_score < ANSWER_MATCH_THRESHOLD:
        answer_speaker = ''

    return {
        'speakers': speakers,
        'colleagues_in_chat': [s['name'] for s in speakers if s['is_colleague']],
        'answer_speaker': answer_speaker,
        'answer_speaker_is_colleague': (
            _is_colleague(answer_speaker, norm_peers) if answer_speaker else None),
        'match_score': round(best_score, 3),
    }


def _is_colleague(name: str, norm_peers: set) -> bool:
    norm = normalize_name(name)
    if not norm:
        return False
    return any(p in norm for p in norm_peers)


SYSTEM_PROMPT = (
    '你是跨境电商知识库的质量审核员。你的判断决定一条自动抽取的问答能否留在知识库里。'
    '只输出一个 JSON 对象，不要任何解释性文字，不要 markdown 代码块。'
)


def build_judge_prompt(doc: Dict[str, Any], annotation: Dict[str, Any],
                       max_history_chars: int = 4000) -> str:
    """单条判定的 prompt。上下文从尾部截断——答案通常出现在对话结尾。"""
    history = doc.get('chat_history') or ''
    if len(history) > max_history_chars:
        history = '……（前文已截断）\n' + history[-max_history_chars:]

    colleagues = annotation.get('colleagues_in_chat') or []
    speaker = annotation.get('answer_speaker') or ''
    if speaker:
        is_col = annotation.get('answer_speaker_is_colleague')
        speaker_hint = '程序定位到答案出自「%s」，该昵称%s在同事名单里（文本相似度 %.2f，可能定位错，仅供参考）' % (
            speaker, '' if is_col else '**不**', annotation.get('match_score') or 0)
    else:
        speaker_hint = '程序没能定位答案出自谁，请自己从聊天记录判断'

    return '''# 业务背景
Payoneer「橄榄枝计划」帮中国跨境卖家入驻和运营海外电商平台（Chewy、Bol、Trendyol、
Cdiscount、ManoMano、OTTO、Walmart、Allegro、Mercado Libre、eBay 等）。
下面这条问答是从客户服务群聊里自动抽取的，现在标记为「高质量」，请你复核它是否够格。

# 待审问答
问题：%s
答案：%s

# 群聊上下文
本段对话中识别到的 Payoneer 同事：%s
%s

<聊天记录>
%s
</聊天记录>

# 判定维度（三条都要给结论）
1. business_related：问题是否属于橄榄枝计划业务——平台入驻资质/材料/审核时效、
   平台规则、收款与费用、运营与物流、后台操作步骤等。
   闲聊、内部事务流水、与跨境电商无关的话题 → false。
2. generic：换一个卖家、换一个店铺是否依然成立。下面任一类都判 false：
   - **问的是卖家自己的情况**：`RDC-是否有海外仓？海外仓在哪里？`（答案「是，波兰、法国」是这个卖家的情况）、
     `Chewy-公司是有多位股东嘛`、`RDC-在RDC打算销售什么品类？`、
     `Bol-你能告诉我过去一年我们所有店铺的GMV和单店铺销售额吗？`（答案是卖家自报的经营数据）
   - 陈述/汇报/状态告知（`我已经提交了入驻申请`）、情绪抱怨、只是一个名词短语
   - 进度催办、时间追问（`目前的审核进度是什么`、`这周会有消息吗`）
   - 索要联系方式/会议号/私发链接
   - 含个案标识：工单号 `GC#23176`、公司名/卖家简称、人名、邮箱、店铺链接、具体金额、税号、单号，
     以及群名前缀里带出来的客户身份（`TY X Payoneel（精创）-佛山-2个店铺，沙特站点，…`
     里的「精创」「佛山」「2个店铺」都是这一个卖家的情况）
   - 主体指代不清（`这个到时能改吧？`），单看这条不知道在问什么
   - **口语化追问/确认**：`…是吧？`、`…对吧？`、`还是说…？`、`…这样吗？`——
     这是对话里的一句接话，不是一个别人会拿来搜的问题
   - **要看懂必须知道上一句在说什么**（问题里的「这个/那份/前面说的」指向上文）
   - 内部办事流水/转派口吻（`表单我可以驳回 稍等一下`、`您直接邮件回复下 Vivian`）
   注意：问题开头的平台名前缀（`Bol-`、`chewy-`、`allegro-`）是有用的限定信息，**不算**个案标识。
3. substantive：答案本身有没有实质内容。**这是业务侧最主要的拒绝理由
   （Chewy 已审 1394 条被拒的里面 91.7%% 是「无实质答案」），判的时候先查这一条。**
   下面任一类都判 false：
   - 空确认：`可以的` / `对的` / `是的` / `不会` / `可以呀` / `没有数量要求` / `对 ```
   - 只重复或改写了问题，没增加信息：`建议不要随意改吗？` → `但是建议还是不要随意改吧`
   - 当下动作/进度回复：`我们这边也在催促Chewy`、`嗯，这个我在群里跟卖家沟通了`
   - 自己也不确定 / 含糊措辞：`你要找一下界面了 我记得是有的`、
     `应该是…吧`、`大概…`、`可能…`、`建议你再跟对方确认下`——
     知识库要的是定论，不是猜测
   - 只说了一半、不构成结论：`这个是COI保险的模版`（没说怎么填）、
     `花旗银行比较慢`（问的是能不能用别的银行）
   - 回避问题：`因为您这个问题目前主观性比较强哈，Chewy 不会正面这个问题的`
   - 客服受理模板：`我们已经收到了您提交的表格，会尽快审核和推进`
   - 反问要材料：`您这边可以提供销量多一些的产品链接吗`

4. answer_source：答案是谁说的
   - colleague：Payoneer 同事（橄榄枝计划小助手/招商/运营）
   - official：电商平台官方的人（如「allegro招商经理小南」「沃尔玛官方经理Catherine」），
     他们不在同事名单里，但回答同样权威
   - customer：卖家/客户自己说的（自报经营数据、自述公司情况、卖家之间互相回答）→ 不可信
   - unknown：无法判断
   判断方法：在聊天记录里找到这句答案是谁发的。**问句在问卖家自身情况时，
   回答它的几乎一定是卖家本人 → customer**。同事的口吻是在讲平台规则、给操作指引；
   卖家的口吻是在讲「我们公司/我们店铺/我这边」的情况。

5. is_rule：这条脱离当时那次对话，还能不能算一条**规则**。
   业务方实际审核时最看重这一条（对 Chewy 1184 条逐条审的结果统计：
   判为「平台通用规则」的通过率明显高于判为「操作细节」的）。
   - 是规则：平台的资质门槛、材料要求、费用与回款算法、时效、模式差异、
     系统字段的固定填法（`EDI 那一栏没有就填 NA`）——换个卖家照样成立
   - 不是规则：当下这一次的操作指引（`你现在去 DSCO 把那个 SKU 的库存改一下`）、
     针对这个卖家这一单的处置意见
   操作步骤类的内容**不是一律不要**，但它必须是标准步骤，而不是这一次的临场指挥。

# 结论
verdict = "keep" 仅当**全部**成立：business_related=true 且 generic=true 且
substantive=true 且 is_rule=true 且 answer_source 属于 colleague/official。
否则 verdict = "downgrade"。

空确认的**唯一例外**（门槛很高，默认不适用，先想为什么不适用）：
问题本身是一个完整的政策性是非问句，**且问题里不含任何个案标识、任何指代词**，
这时「可以/不可以」本身就是一条可复用的结论，才允许 substantive=true。
- 适用：`chewy-可以用中国大陆的主体入驻吗？` → `可以`
- **不适用**：`TY X Payoneel（精创）-佛山-2个店铺，沙特站点，可以用同一个海外仓地址吧` → `可以的老板`
  （问题带卖家简称、城市、店铺数量，generic 已经是 false）
- **不适用**：`chewy-那后期是否可以补充提供？` → `可以的`（问题里「后期」「补充提供」
  指的是这一单当下的某份材料，脱离上下文不知道在问什么）
- **不适用**：`chewy-这个国内平台可以写吗` → `可以的`（「这个」没说明是哪个）

拿不准时一律判 downgrade——留一条个案或一句空确认进检索，比漏一条知识更有害。

tags 从下面选（可多选，keep 时留空数组）：
"不通用"、"不相关"、"无实质答案"、"不清晰"、"答案来自客户"

# 输出（只输出这个 JSON）
{"business_related": true, "generic": true, "substantive": true, "is_rule": true,
 "answer_source": "colleague", "verdict": "keep", "tags": [], "reason": "50字以内说明"}''' % (
        doc.get('title') or '', doc.get('content') or '',
        '、'.join(colleagues) if colleagues else '（未识别到）',
        speaker_hint, history)


def _parse_llm_json(text: str) -> Optional[Dict[str, Any]]:
    """模型偶尔会包 ```json 或前后带说明，取第一个完整的 JSON 对象"""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?|```$', '', cleaned, flags=re.M).strip()
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(cleaned[start:end + 1])
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def decide_level(old_level: str, result: Dict[str, Any]) -> Tuple[str, str]:
    """
    判定结果 → 新档位。返回 (new_level, skip_reason)。

    判不出来就不动（skip_reason 非空），绝不默认降级——
    模型失败把一批 high 静默降到 low 是最坏的结果。
    """
    if not result:
        return old_level, 'empty_llm_result'
    verdict = str(result.get('verdict') or '').lower()
    if verdict not in ('keep', 'downgrade'):
        return old_level, 'bad_verdict'

    tags = [str(t).strip('#') for t in (result.get('tags') or []) if str(t).strip()]
    source = str(result.get('answer_source') or '').lower()

    if verdict == 'keep':
        return 'high', ''
    # 三个硬维度任何一个不过 → low
    if (source == 'customer' or result.get('business_related') is False
            or result.get('generic') is False or result.get('substantive') is False
            or LOW_TAGS.intersection(tags)):
        return 'low', ''
    # 不是规则、只是当次对话的操作指引：降 mid（内容本身没错，只是不该进检索）
    if result.get('is_rule') is False:
        return 'mid', ''
    if MID_TAGS.intersection(tags):
        return 'mid', ''
    # 说要降级但没给出降级理由，保守降到 mid（mid 同样不进默认检索）
    return 'mid', ''


def judge_one(doc: Dict[str, Any], colleague_names: Sequence[str],
              model: str) -> Dict[str, Any]:
    annotation = annotate_chat_history(doc.get('chat_history') or '',
                                       doc.get('content') or '', colleague_names)
    prompt = build_judge_prompt(doc, annotation)
    content, detail = cqe_llm_client.request_llm(
        model_name=model, query=prompt, system_message=SYSTEM_PROMPT,
        max_tokens=800, temperature=0.1)
    result = _parse_llm_json(content)
    new_level, skip_reason = decide_level(doc.get('old_level') or 'high', result or {})
    if result is None and content:
        skip_reason = skip_reason or 'unparsable_llm_result'
    return {
        '_id': doc['_id'],
        'title': doc.get('title'),
        'content': doc.get('content'),
        'category': doc.get('category'),
        'chat_room': doc.get('chat_room'),
        'old_level': doc.get('old_level'),
        'new_level': new_level,
        'changed': new_level != (doc.get('old_level') or ''),
        'verdict': (result or {}).get('verdict'),
        'business_related': (result or {}).get('business_related'),
        'generic': (result or {}).get('generic'),
        'substantive': (result or {}).get('substantive'),
        'is_rule': (result or {}).get('is_rule'),
        'answer_source': (result or {}).get('answer_source'),
        'tags': (result or {}).get('tags') or [],
        'reason': (result or {}).get('reason'),
        'answer_speaker': annotation.get('answer_speaker'),
        'answer_speaker_is_colleague': annotation.get('answer_speaker_is_colleague'),
        'match_score': annotation.get('match_score'),
        'colleagues_in_chat': annotation.get('colleagues_in_chat'),
        'skip_reason': skip_reason,
        'llm_detail': detail[:200] if skip_reason else '',
    }


def judge_all(docs: List[Dict[str, Any]], colleague_names: Sequence[str],
              decision_file: str, model: str = '', concurrency: int = 4) -> List[Dict[str, Any]]:
    """并发判定，逐条落盘，已判过的 _id 跳过（续跑不重复烧 token）"""
    load_llm_config()
    if not cqe_llm_client.is_configured():
        raise RuntimeError('LLM 凭证缺失：请配置 config/llm_config.json（模板见 .example）')
    model = model or get_model('quality')
    logging.info('审核模型: %s，并发 %d', model, concurrency)

    done = {r['_id']: r for r in _read_jsonl(decision_file)} if os.path.exists(decision_file) else {}
    todo = [d for d in docs if d['_id'] not in done]
    logging.info('待判 %d 条（已有结果 %d 条）', len(todo), len(done))

    results: List[Dict[str, Any]] = list(done.values())

    def _run(doc: Dict[str, Any]) -> None:
        try:
            row = judge_one(doc, colleague_names, model)
        except Exception as exc:  # noqa: BLE001 单条失败不能拖垮整轮
            logging.warning('判定失败 _id=%s: %s', doc.get('_id'), exc)
            row = {'_id': doc['_id'], 'title': doc.get('title'),
                   'old_level': doc.get('old_level'), 'new_level': doc.get('old_level'),
                   'changed': False, 'skip_reason': 'exception:%s' % type(exc).__name__}
        with _write_lock:
            results.append(row)
            with open(decision_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
            if len(results) % 20 == 0:
                logging.info('进度 %d/%d', len(results), len(docs))

    if todo:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(_run, todo))
    return results


def build_report(decisions: List[Dict[str, Any]], sample_size: int = 10) -> Dict[str, Any]:
    transitions: Dict[str, int] = {}
    reasons: Dict[str, int] = {}
    sources: Dict[str, int] = {}
    skips: Dict[str, int] = {}
    for d in decisions:
        transitions['%s->%s' % (d.get('old_level'), d.get('new_level'))] = \
            transitions.get('%s->%s' % (d.get('old_level'), d.get('new_level')), 0) + 1
        for t in d.get('tags') or []:
            reasons[t] = reasons.get(t, 0) + 1
        src = d.get('answer_source') or 'n/a'
        sources[src] = sources.get(src, 0) + 1
        if d.get('skip_reason'):
            skips[d['skip_reason']] = skips.get(d['skip_reason'], 0) + 1
    changed = [d for d in decisions if d.get('changed')]
    kept = [d for d in decisions if not d.get('changed') and not d.get('skip_reason')]
    return {
        'total': len(decisions),
        'changed': len(changed),
        'transitions': transitions,
        'tags': reasons,
        'answer_source': sources,
        'skipped': skips,
        'downgrade_samples': [{'title': d.get('title'), 'answer': (d.get('content') or '')[:80],
                               'to': d.get('new_level'), 'source': d.get('answer_source'),
                               'speaker': d.get('answer_speaker'),
                               'tags': d.get('tags'), 'reason': d.get('reason')}
                              for d in changed[:sample_size]],
        'keep_samples': [{'title': d.get('title'), 'answer': (d.get('content') or '')[:80],
                          'source': d.get('answer_source'), 'reason': d.get('reason')}
                         for d in kept[:sample_size]],
    }


def bulk_update_doc(es: EsHttpClient, index: str,
                    updates: List[Tuple[str, Dict[str, Any]]],
                    batch_size: int = DEFAULT_BULK_BATCH) -> Dict[str, Any]:
    """
    _bulk 局部更新。自带一份而不用 `EsHttpClient.bulk_update_doc`：
    那个方法目前只在本地工作区里，生产机器上的 commons/es_http_client.py 还没有它
    （线上跑会 AttributeError）。`bulk_update_field` 只能写单字段，不够用。
    """
    updated, failures = 0, []
    start = 0
    while start < len(updates):
        batch = updates[start:start + batch_size]
        lines = []
        for doc_id, partial in batch:
            lines.append(json.dumps({'update': {'_index': index, '_id': doc_id}}, ensure_ascii=False))
            lines.append(json.dumps({'doc': partial}, ensure_ascii=False))
        status, payload = es._request('POST', '/_bulk', raw_body='\n'.join(lines) + '\n')
        if status == 413 and batch_size > 10:
            batch_size = max(10, batch_size // 2)
            logging.warning('bulk 触发 413，batch_size 降为 %d 重试', batch_size)
            continue
        if status != 200:
            raise RuntimeError('ES bulk 失败 status=%s payload=%s' % (status, payload))
        # Serverless 返回 200 不代表成功，错误藏在 items 里
        for item in payload.get('items', []):
            res = item.get('update', {})
            if res.get('error'):
                failures.append({'_id': res.get('_id'), 'error': res['error']})
            else:
                updated += 1
        start += len(batch)
        logging.info('bulk 进度 %d/%d，成功 %d，失败 %d',
                     start, len(updates), updated, len(failures))
    return {'updated': updated, 'failed': failures}


def apply_updates(es: EsHttpClient, index: str, decisions: List[Dict[str, Any]],
                  rollback_file: str, batch_size: int = DEFAULT_BULK_BATCH) -> Dict[str, Any]:
    """只写 quality_level，且只写真正变化的；写前先落 rollback"""
    changed = [d for d in decisions if d.get('changed') and not d.get('skip_reason')]
    if not changed:
        logging.info('没有需要写回的文档')
        return {'updated': 0, 'failed': []}
    _write_jsonl(rollback_file, [{'_id': d['_id'], 'quality_level': d['old_level']}
                                 for d in changed])
    logging.info('回滚文件已写入 %s（%d 条）', rollback_file, len(changed))
    updates = [(d['_id'], {'quality_level': d['new_level']}) for d in changed]
    return bulk_update_doc(es, index, updates, batch_size=batch_size)


def run_rollback(es: EsHttpClient, index: str, rollback_file: str,
                 batch_size: int = DEFAULT_BULK_BATCH) -> Dict[str, Any]:
    rows = _read_jsonl(rollback_file)
    updates = [(r['_id'], {'quality_level': r['quality_level']}) for r in rows]
    logging.info('回滚 %d 条 → %s', len(updates), index)
    return bulk_update_doc(es, index, updates, batch_size=batch_size)


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='自动学习 QA 二次质量审核（带群聊上下文 + 同事名单）')
    p.add_argument('--es-config', default=DEFAULT_ES_CONFIG)
    p.add_argument('--index', required=True, help='ES 索引名，如 payoneer_olive')
    p.add_argument('--client', required=True, help='client，如 payoneer_olive')
    p.add_argument('--app-id', default=DEFAULT_APP_ID, help='取同事名单用的 appId')
    p.add_argument('--from-type', default='chat_auto')
    p.add_argument('--quality-level', default='high')
    p.add_argument('--audit-result', type=int, action='append', default=[],
                   help='可重复，默认只审未审核过的 -1')
    p.add_argument('--limit', type=int, default=0, help='0 = 不限；本机跑务必设小')
    p.add_argument('--random-seed', type=int, default=0, help='非 0 时随机抽样')
    p.add_argument('--concurrency', type=int, default=4)
    p.add_argument('--model', default='', help='默认取 llm_config models.quality')
    p.add_argument('--work-dir', default='')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--rollback', default='')
    p.add_argument('--bulk-batch', type=int, default=DEFAULT_BULK_BATCH)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    args = build_arg_parser().parse_args(argv)
    es = EsHttpClient.from_config(args.es_config)

    if args.rollback:
        if not args.execute:
            print('--rollback 需要配合 --execute')
            return 1
        print(json.dumps(run_rollback(es, args.index, args.rollback, args.bulk_batch),
                         ensure_ascii=False, indent=2))
        return 0

    work_dir = args.work_dir or os.path.join(
        PROJECT_ROOT, 'output', 'audit_chat_auto_%s' % args.index)
    os.makedirs(work_dir, exist_ok=True)

    colleagues_file = os.path.join(work_dir, 'colleagues.json')
    if os.path.exists(colleagues_file):
        colleague_names = json.load(open(colleagues_file, 'r', encoding='utf-8'))
        logging.info('复用同事名单 %s（%d 人）', colleagues_file, len(colleague_names))
    else:
        colleague_names = extract_colleague_names(
            fetch_role_config(args.app_id, args.client))
        if not colleague_names:
            raise SystemExit('同事名单为空，判定会失效，先查 appId/client 是否正确')
        json.dump(colleague_names, open(colleagues_file, 'w', encoding='utf-8'),
                  ensure_ascii=False)
        logging.info('同事名单 %d 人 → %s', len(colleague_names), colleagues_file)

    query = build_target_query(from_type=args.from_type, quality_level=args.quality_level,
                               audit_results=args.audit_result or (-1,),
                               random_seed=args.random_seed)
    docs = download_docs(es, args.index, query, os.path.join(work_dir, 'docs.jsonl'),
                         limit=args.limit, random_sample=bool(args.random_seed))
    if not docs:
        print('没有圈到待审 QA')
        return 0

    decisions = judge_all(docs, colleague_names,
                          os.path.join(work_dir, 'decisions.jsonl'),
                          model=args.model, concurrency=args.concurrency)
    report = build_report(decisions)
    report['index'] = args.index
    report['work_dir'] = work_dir
    report['colleague_count'] = len(colleague_names)

    if args.execute:
        report['result'] = apply_updates(es, args.index, decisions,
                                         os.path.join(work_dir, 'rollback.jsonl'),
                                         args.bulk_batch)
        report['mode'] = 'execute'
    else:
        report['mode'] = 'dry-run（加 --execute 才写）'

    json.dump(report, open(os.path.join(work_dir, 'report.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
