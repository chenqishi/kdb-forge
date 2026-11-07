from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('chatknowledge/gen_knowledge_from_chat.py')
from commons import common_utils
from commons.common_utils import load_attr_map_dict as load_3file_dict
from config_tools.config import GLOBAL_CONFIG as config
import json
import logging
import sys
import os
import re
import hashlib
import mimetypes
import requests
import time
import traceback
import contextlib
from datetime import datetime

LEADER_SOURCE_ROLE = 'leader/可作为答案来源'
COLLEAGUE_SOURCE_ROLE = '同事/可作为答案来源'
QUESTION_SOURCE_ROLE = '客户/只能作为问题来源'
UNKNOWN_SOURCE_ROLE = '未识别/不能作为答案来源'
ANSWER_SOURCE_ROLES = {LEADER_SOURCE_ROLE, COLLEAGUE_SOURCE_ROLE}
IDENTITY_PRIORITY = {
    LEADER_SOURCE_ROLE: 100,
    COLLEAGUE_SOURCE_ROLE: 90,
    QUESTION_SOURCE_ROLE: 10,
    UNKNOWN_SOURCE_ROLE: 0,
}

# `AI` 必须是独立的 ASCII 关键词；不能误伤 Aimee、Daisy 等真人姓名。
AI_SPEAKER_KEYWORD_RE = re.compile(r'(?i)(?<![A-Za-z])ai(?![A-Za-z])')

NOISE_ACK_TEXT = {
    '好', '好的', '收到', '已收到', '嗯', '嗯嗯', 'ok', 'OK', 'Ok', '谢谢',
    '感谢', '辛苦了', '麻烦了', '可以', '可以的', '是的', '对', '对的', '不是', '1',
    '应该是', '应该可以', '看着应该是了', '没问题',
    'yes', 'no', 'yep', 'nope', 'sure', 'thanks', 'thank you', 'thx',
    'noted', 'noted a moment', 'one moment', 'wait a moment', 'sorry', 'oh sorry',
}

DIRECT_LLM_JSON_SYSTEM_INSTRUCTION = """
你是跨境电商聊天记录 QA 知识抽取引擎。你的工作目标是：只从“当前待评估答案”中沉淀未来可复用的业务知识，输出忠于原文、可审核、可进入知识库的结构化 QA；不能复述整段聊天，不能替客户编答案。

输入格式固定：
- 用户消息只包含 metadata 和动态对话窗口，不包含规则说明或图片地址 JSON。
- 【上方50句上下文】只用于还原客户问题、业务阶段、指代对象和必要背景。
- 【当前待评估答案】是本次唯一允许作为答案来源的 leader/同事原文。
- 每行格式为：时间｜角色姓名/用途：原文内容。用途可能是：问题来源、答案来源、当前待评估答案、上下文参考。
- 正文中的“（图片1）”“（图片2）”只是图片占位。图片真实 URL/路径由程序映射，不在用户消息中提供，也不需要你输出。

拼接和来源约束：
- 只能把【当前待评估答案】以及同一 answer turn 内连续的 leader/同事原文作为答案来源。
- 【上方50句上下文】里的客户消息只能帮助形成 q，不能进入 a。
- 【上方50句上下文】里的其他 leader/同事历史回答只能帮助理解对话背景，不能被拼进当前 a。
- 如果当前待评估答案里有引用回复包装、被引用原文、长分隔线、群管理尾巴，只能取其中真正由当前同事发出的业务口径。

QA 抽取类型：
- 可抽：平台规则、入驻/注册/审核/刊登/结算/物流/汇款流程、资料要求、字段填写要求、排障方法、限制条件、业务判断口径、可复用操作步骤。
- 当前待评估答案明确说明支持/不支持某国家、地区、币种、银行、签证类型、主体类型时，即使答案很短，也属于可复用规则；如果平台可从 user prompt 标题或上下文确定，q 必须写出平台名，不要写 this platform/该平台。
- 当前待评估答案是简短规则时不要因为短而直接返回空。只要最近相关上下文能确定对象，且答案本身明确表达支持/不支持、可以/不可以、需要/不需要、可绑定/不可绑定、可注册/不可注册、可转账/不可转账、是否需要同主体等业务口径，就应抽取；例如“supported HSBC overseas”“只要主体一致的支付商账号即可绑定”“we don't support study visa”这类短规则可以抽，q 负责补全原文中的对象和场景。
- 可抽安全/合规解释：如果当前待评估答案完整说明平台安全性、合法性、监管牌照、合规检查、资金冻结风险或资金保障逻辑，且上下文是在询问平台是否安全/可靠/合法，也应抽取为可复用知识。
- 不抽：短确认、寒暄、等待、道歉、无业务口径、纯转发、教程/链接合集、广告营销、活动报名、福利宣传、入群欢迎、群规则、群公告、问卷提醒、索要手机号/邮箱/截图、帮忙催办/申诉/处理、内部协作、离题闲聊。
- 不抽临时系统问题：例如 KYC/后台/系统升级中、当前有 bug、我们已在修复、正在修复、改天/下周/VPN/换浏览器/隔天再试。这些是临时状态或协作建议，不是可复用业务知识。
- 不抽后台客服协作：例如把订单号、账单 id、费用账单 id 发给后台客服判断/处理/咨询，只能说明个案排查路径，不能泛化成知识。
- 不抽具体个案状态：某账号/店铺/订单/申请/工单/物流单当前状态、某客户是否通过、某个问题是否已经反馈，除非当前待评估答案明确给出可复用规则。
- 上下文不足、指代不清、平台/场景不明、当前待评估答案无法独立支撑答案时，必须输出 {"items": []}。

q 的生成标准：
- q 的背景增强是一种忠于原文的整理方法，不是字段模板。你要把当时这个具体问题说完整：从最近相关原文中补全客户问题和当前待评估答案依赖的指代、场景、对象、限制和前置条件。
- 只有当原文中实际出现且与当前待评估答案直接相关时，才补入服务平台、业务对象、主体类型、业务阶段、注册/提现/收款用途、用户动作、资料/字段/页面/按钮、异常现象、已尝试动作等背景；未出现或不相关的信息不要为了完整而补。
- 如果 metadata 给出服务平台，同时对话原文也出现目标渠道/店铺/业务对象，且两者都与当前答案相关，q 应同时保留两者；如果原文没有对应依据，不要凭经验补出服务平台、主体类型或用途。
- 如果当前待评估答案是在回答上文同一主题的追问，q 只承接最近同主题问题里已经明确出现的稳定背景；不要只根据当前答案里的单个字段生成窄问题，也不要把无关历史问题合并进来。
- 上下文里的个案银行名、账号名、客户操作对象等只用于理解当时问题；如果当前待评估答案没有提到，不要写入 q，例如不要把 “e.g., China Citic” 这类个案银行名带进可复用问题。
- q 中的平台、渠道、店铺类型、业务对象名称必须能在 user prompt 的 metadata 或对话原文中找到依据；不要凭行业经验补出未出现的对象名称，例如输入只写“跨境店”时不能改成“TikTok 跨境店”。
- 当前待评估答案只说明“可以注册/可注册/ok to register”时，q 只能询问注册资格或开户注册，不能推断为支持汇款、转账、提现或收款；只有当前答案也明确提到 transfer/remit/汇款/转账/提现/币种/目的地，q 才能写这些能力。
- 如果当前待评估答案的关键动作对象是 it/this/that/这个/该，q 必须从最近上下文中补出具体对象，例如“收入证明表格/模板”；不能只写“文件/资料”这类泛称。如果无法确认这个指代对象，直接输出 {"items": []}。
- q 不能补充未出现的信息，不能把无关上下文或其他历史答案拼进问题。
- q 必须脱敏，不出现真实人名、客户名、公司名、店铺名、群名、账号、订单号、申请号、手机号、邮箱、微信号、个人链接等可定位个体的信息。
- 脱敏只针对可定位个体的标识；国家、地区、国籍、币种、签证类型、银行类型等业务实体必须保留，例如 Ghana/Ghanaian 不能写成 `[用户ID]`。

a 的生成标准：
- a 不是标准化改写，不要为了“更像知识库答案”而重写原句；必须尽量保留当前待评估答案原文的词序、语气、称谓和表达。
- a 只允许做最小清理：去掉开头 @ 人、`哦哦/嗯嗯/好的` 这类明显口头开场词、个人信息、引用包装和无关尾巴；其余主体表达不改写。不要把“您在注册的时候需要...”改写成“注册时需要...”，不要把“您就正常用...”改写成“用...”。
- a 中如果夹带“邀您入群/方便咨询/对接官方经理/感谢理解支持”等群运营尾巴，应删除尾巴，只保留当前待评估答案里的业务口径；如果删除后没有业务口径，输出 {"items": []}。
- 英文开场寒暄、歉意或确认词也属于明显口头开场词，例如 `Hi sorry I missed the early messages:`、`Yeah`、`Yes`、`Ok`、`Okay`，a 中应删除这类前缀，只保留其后的业务原句。
- a 默认保持当前待评估答案的原文语言和核心措辞，不要把英文答案翻译成中文，也不要把中文答案翻译成英文；除非只是删除称呼、脱敏或清理引用包装。
- 当前待评估答案很短但仍是明确规则时，a 保持短答案，不要把上下文里的其他答案补进来。
- 当前待评估答案含多句时，可以合并成同一个答案，但每个要点都必须来自该 answer turn。
- 如果答案含链接，除非链接本身是通用官方入口，否则 a 中应脱敏为“[链接]”；图片 URL/路径型答案除外。
- 如果当前待评估答案只说明个案处理或状态，不能泛化成知识。

图片处理：
- 图片不是乱码；图片占位和图片地址必须理解为图片消息。
- 你不能看到图片内容，也不能编造图片中的文字或视觉信息。
- 如果当前待评估答案是图文混合，a 只使用同 turn 文本口径；图片追溯由程序在后处理阶段挂载。
- 如果当前待评估答案是纯图片且上下文足够明确问题，可以抽取 q，但 a 必须只写“图片答案”；程序会把 a 替换成对应图片 URL/路径。
- 纯图片答案不能把上方上下文里的历史文字答案复制或改写成 a，也不能把你推测的图片内容写成 a；如果你不能确定 q，输出 {"items": []}。
- 不要输出 supplement，不要输出图片 URL、backend_path、address，不要尝试自己维护图片和占位符的映射。
- 如果无法确认图片属于当前待评估答案或图片无法作为独立答案，输出 {"items": []}。

质量和分类：
- quality_level=high：问题清晰，答案完整可执行，复用价值高。
- quality_level=mid：有复用价值，但范围较窄、答案略依赖上下文或需少量人工确认。
- quality_level=low：碎片化、不完整、偏个案；通常 is_qualified=false。
- is_qualified=true：脱敏后仍通用、信息完整、可被其他场景复用。
- is_qualified=false：偏个案、上下文不足、低价值、需要人工大量补全、状态查询、临时系统 bug 或临时协作。若没有保留价值，直接输出 {"items": []}。
- reuse_scope=universal 表示全行业通用；industry_specific 表示行业/平台/业务线内可复用；client_specific 表示只适用于单一 client 或个案，通常不应进入知识库。

输出必须是严格 JSON object，不能输出 Markdown、解释文字或代码块。格式：
{
  "items": [
    {
      "q": "补足业务背景且脱敏后的可搜索问题",
      "a": "只来自当前待评估答案且脱敏泛化后的答案",
      "source": "当前待评估答案说话人姓名",
      "platform": "平台名，不确定填 unknown",
      "quality_level": "high|mid|low",
      "is_qualified": true,
      "quality_reason": "质量判断原因",
      "tags": ["业务、场景、实体和检索关键词统一放在这里"],
      "reuse_scope": "universal|industry_specific|client_specific",
      "confidence": 0.0,
      "source_quote": "当前待评估答案里的关键原文"
    }
  ]
}
"""

DIRECT_LLM_PROMPT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))),
    'chat_qa_extract',
    'prompts',
)


def _normalize_name(name):
    return re.sub(r'\s+', '', str(name or '').strip().lower())


def _normalize_identity_key(value):
    return re.sub(r'\s+', '', str(value or '').strip().lower())


def has_ai_speaker_keyword(name):
    """姓名中存在独立 AI 标识时，不允许作为人工答案来源。"""
    return bool(AI_SPEAKER_KEYWORD_RE.search(str(name or '')))


def _split_name_list(text):
    names = []
    for item in re.split(r'[\n,，、;；]+', text or ''):
        item = item.strip().strip('。').strip()
        if item:
            names.append(item)
    return names


def extract_answer_source_names(system_prompt):
    """
    从平台system prompt中抽取“同事/可作为答案来源”的姓名列表。
    """
    if not system_prompt:
        return set()

    answer_names = set()
    colleague_blocks = re.findall(r'#\s*你的同事如下.*?"""(.*?)"""', system_prompt, re.S)
    for block in colleague_blocks:
        answer_names.update(_split_name_list(block))

    role_blocks = re.findall(r'下面这些人是你的同事.*?：\s*\n(.*?)(?:\n\s*\n|除以上同事|如果输入消息)', system_prompt, re.S)
    for block in role_blocks:
        answer_names.update(_split_name_list(block))

    sentence_patterns = [
        r'([^。\n#]+?)这\d*个人是你的同事',
        r'([^。\n#]+?)是你的同事[，,]\s*他们的发言会包含答案',
        r'你的同事们的回答[，,]\s*例如(.+?)等[，,]\s*他们的回答都是正确的答案',
        r'只有(.+?)的回答可以作为答案',
    ]
    for pattern in sentence_patterns:
        for match in re.findall(pattern, system_prompt, re.S):
            answer_names.update(_split_name_list(match))

    return set(name for name in answer_names if name and not has_ai_speaker_keyword(name))

def _is_name_match(send_user, candidate_names):
    send_user_norm = _normalize_name(send_user)
    if not send_user_norm:
        return False
    for name in candidate_names or []:
        name_norm = _normalize_name(name)
        if not name_norm:
            continue
        if send_user_norm == name_norm or name_norm in send_user_norm or send_user_norm in name_norm:
            return True
    return False


def _to_int(value, default=None):
    try:
        if value is None or value == '':
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _new_identity_lookup():
    return {'by_id': {}, 'by_name': {}}


def _add_identity(lookup, key_type, key, role, reason, display_name=None):
    norm_key = _normalize_identity_key(key)
    if not norm_key:
        return
    item = {
        'role': role,
        'reason': reason,
        'display_name': display_name or str(key or '').strip(),
        'priority': IDENTITY_PRIORITY.get(role, 0),
    }
    exists = lookup[key_type].get(norm_key)
    if not exists or item['priority'] > exists.get('priority', 0):
        lookup[key_type][norm_key] = item


def _role_from_wecom_contact(row):
    relationship = _to_int(row.get('we_com_contact_relationship'))
    relation_type = _to_int(row.get('we_com_contact_relation_type'))
    if relationship == 2:
        return COLLEAGUE_SOURCE_ROLE, '企业微信通讯录标记为同事'
    if relation_type == 1 and relationship != 3:
        return COLLEAGUE_SOURCE_ROLE, '企业微信通讯录标记为内部联系人'
    if relationship == 3:
        return UNKNOWN_SOURCE_ROLE, '企业微信通讯录标记为静默'
    return QUESTION_SOURCE_ROLE, '企业微信通讯录默认外部联系人'


def _role_from_wechat_address(row):
    relationship = _to_int(row.get('relationship'))
    if relationship == 2:
        return COLLEAGUE_SOURCE_ROLE, '微信通讯录标记为同事'
    if relationship == 3:
        return UNKNOWN_SOURCE_ROLE, '微信通讯录标记为静默'
    return QUESTION_SOURCE_ROLE, '微信通讯录默认联系人'


def _add_contact_identity_row(lookup, row, role, reason, id_fields, name_fields):
    display_name = ''
    for name_field in name_fields:
        if row.get(name_field):
            display_name = str(row.get(name_field)).strip()
            break

    for id_field in id_fields:
        _add_identity(lookup, 'by_id', row.get(id_field), role, reason, display_name)

    # 姓名兜底只用于可作为答案来源的人，避免客户重名时被错误命中。
    if role in ANSWER_SOURCE_ROLES:
        for name_field in name_fields:
            _add_identity(lookup, 'by_name', row.get(name_field), role, reason, display_name)


def load_contact_identity_lookup(mysql_config_file='config/mysql_conn_config.json'):
    """
    从通讯录表加载发言人身份。ID 精确匹配优先，姓名只作为同事/leader兜底。
    """
    lookup = _new_identity_lookup()
    if not mysql_config_file or not os.path.exists(mysql_config_file):
        logging.warning('mysql_config_file not found, skip contact identity lookup: %s', mysql_config_file)
        return lookup

    try:
        from commons.mysql_connector import MySQLConnector

        conn = MySQLConnector(mysql_config_file).get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                we_com_contact_user_id,
                we_com_contact_nick_name,
                we_com_contact_real_name,
                we_com_contact_relationship,
                we_com_contact_relation_type
            FROM rf_wkt_we_com_contact
            WHERE (del_flag IS NULL OR del_flag = 0)
              AND (is_enabled IS NULL OR is_enabled = 1)
        """)
        for row in cursor.fetchall():
            role, reason = _role_from_wecom_contact(row)
            _add_contact_identity_row(
                lookup,
                row,
                role,
                reason,
                id_fields=['we_com_contact_user_id'],
                name_fields=['we_com_contact_real_name', 'we_com_contact_nick_name']
            )

        cursor.execute("""
            SELECT
                address_wc_id,
                address_wechat_number,
                address_nick_name,
                relationship
            FROM rf_wkt_wechat_address
            WHERE (del_flag IS NULL OR del_flag = 0)
              AND (is_enabled IS NULL OR is_enabled = 1)
        """)
        for row in cursor.fetchall():
            role, reason = _role_from_wechat_address(row)
            _add_contact_identity_row(
                lookup,
                row,
                role,
                reason,
                id_fields=['address_wc_id', 'address_wechat_number'],
                name_fields=['address_nick_name']
            )

        cursor.close()
        conn.close()
        logging.info(
            'loaded contact identity lookup: by_id=%s by_name=%s',
            len(lookup['by_id']),
            len(lookup['by_name'])
        )
    except Exception:
        logging.error('load contact identity lookup failed:\n%s', traceback.format_exc())
    return lookup


def lookup_contact_identity(message_info, identity_lookup=None):
    if not identity_lookup:
        return None
    for key in [
        message_info.get('actual_user_id'),
        message_info.get('from_user_id'),
        message_info.get('send_user_id'),
    ]:
        item = identity_lookup.get('by_id', {}).get(_normalize_identity_key(key))
        if item:
            return item
    for key in [
        message_info.get('actual_user_nickname'),
        message_info.get('from_user_nickname'),
        message_info.get('send_user'),
    ]:
        item = identity_lookup.get('by_name', {}).get(_normalize_identity_key(key))
        if item:
            return item
    return None


def infer_speaker_identity(send_user, white_name_list=None, answer_source_names=None, platform=None,
                           contact_identity=None):
    """
    根据通讯录、白名单、平台同事名单和少量平台前缀推断说话人身份。
    """
    # 通讯录中显式设为“静默/不可作为答案源”是负向权威配置，
    # 用于标记 AI 助理、机器人或其它不应学习的账号。它必须能否决
    # system prompt 中的过期同事名单。
    if contact_identity and contact_identity.get('role') == UNKNOWN_SOURCE_ROLE:
        return UNKNOWN_SOURCE_ROLE, contact_identity.get('reason', '通讯录明确禁止作为答案源')

    # 发言人名称中的独立 AI 标识是硬 veto，优先于白名单、
    # 平台同事名单和通讯录的非静默身份。这只影响知识学习。
    if has_ai_speaker_keyword(send_user):
        return UNKNOWN_SOURCE_ROLE, '发言人名称包含AI标识'

    # 业务侧显式答案来源配置优先于通讯录的默认外部联系人身份。
    if _is_name_match(send_user, white_name_list):
        return LEADER_SOURCE_ROLE, '命中群白名单'
    if _is_name_match(send_user, answer_source_names):
        return COLLEAGUE_SOURCE_ROLE, '命中平台同事名单'
    if contact_identity:
        return contact_identity.get('role', QUESTION_SOURCE_ROLE), contact_identity.get('reason', '命中通讯录身份')

    send_user_norm = _normalize_name(send_user)
    platform_norm = _normalize_name(platform)
    if platform_norm == 'payoneer' and any(key in send_user_norm for key in ['payoneer', '派安盈', '橄榄枝']):
        return COLLEAGUE_SOURCE_ROLE, '命中Payoneer平台身份前缀'
    if platform_norm == 'santouliubi' and '三头六臂' in send_user_norm:
        return COLLEAGUE_SOURCE_ROLE, '命中三头六臂平台身份前缀'

    return QUESTION_SOURCE_ROLE, '未命中leader/同事身份'


def format_message_time(message_time):
    message_time = str(message_time or '').strip()
    return re.sub(r'^(\d{4}-\d{2}-\d{2})(\d{2}:\d{2}:\d{2})$', r'\1 \2', message_time)


def parse_message_time_ts(message_time):
    message_time = format_message_time(message_time)
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d%H:%M:%S']:
        try:
            return datetime.strptime(message_time, fmt).timestamp()
        except ValueError:
            continue
    return None


def strip_reply_quote_artifact(content):
    content = str(content or '').strip()
    if not content:
        return content
    if not re.search(r'(?:-\s*){6,}|-{6,}|------', content):
        return content
    if not re.search(r'[「“"].+[」”"]|：\s*/|:\s*/|/\s*-{3,}\s*/|^\s*「|\[图片\]', content, flags=re.S):
        return content
    separator_matches = list(re.finditer(r'(?:-\s*){6,}|-{6,}|------', content))
    for separator in reversed(separator_matches):
        tail = content[separator.end():]
        tail = re.sub(r'^[\s/：:，,。;；"“”]+', '', tail).strip()
        if tail:
            return tail
    return content


def strip_group_management_tail(content):
    content = str(content or '').strip()
    if not content:
        return content
    cleaned = re.sub(
        r'(?:另外|另请|同时|以及)?请.{0,40}(?:修改群内?备注|修改群被?姓名备注|填写.{0,12}问卷|基础信息问卷|群基础信息问卷).*$',
        '',
        content
    ).strip()
    cleaned = re.sub(
        r'(?:否则|不然).{0,20}(?:清出社群|清理|清人|踢出群聊).*$',
        '',
        cleaned
    ).strip()
    return cleaned or content


def strip_referral_promo_tail(content):
    content = str(content or '').strip()
    if not content:
        return content
    cleaned = content
    cleaned = re.sub(
        r'\s*,?\s*but if you have friends who hold work visa, please feel free to share our event.*$',
        '',
        cleaned,
        flags=re.I | re.S
    ).strip()
    cleaned = re.sub(
        r'\s*(?:Also,\s*)?if you have friends who hold work visa, please feel free to share our event.*$',
        '',
        cleaned,
        flags=re.I | re.S
    ).strip()
    cleaned = re.sub(
        r'\s*please check this link for more (?:prizes|details).*$',
        '',
        cleaned,
        flags=re.I | re.S
    ).strip()
    cleaned = re.sub(
        r'\s*\(?Find\s+your\s+link/code:.*$',
        '',
        cleaned,
        flags=re.I | re.S
    ).strip()
    cleaned = re.sub(
        r'\s*https?://remit\.skyee360\.com/client/account/invitation\S*.*$',
        '',
        cleaned,
        flags=re.I | re.S
    ).strip()
    cleaned = re.sub(
        r'\s*(?:both of you will get|you will get)\s*\d+\s*bonus.*$',
        '',
        cleaned,
        flags=re.I | re.S
    ).strip()
    return cleaned or content


def fix_common_chat_typos(content):
    content = str(content or '').strip()
    if not content:
        return content
    content = re.sub(r'(KYC的流程所有卖家都要)经理的', r'\1经历的', content)
    return content


def clean_chat_artifacts(content):
    content = strip_reply_quote_artifact(content)
    content = strip_group_management_tail(content)
    content = strip_referral_promo_tail(content)
    content = fix_common_chat_typos(content)
    return content.strip()


def sanitize_chat_content(content):
    content = str(content or '').replace('\u200b', '').replace('\ufeff', '')
    content = ''.join(ch for ch in content if ch in '\n\r\t' or ord(ch) >= 32)
    content = re.sub(r'[ \t\r\f\v]+', ' ', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = clean_chat_artifacts(content)
    return content.strip()


def normalize_message_ctype(ctype):
    return str(ctype or '').strip().upper()


def is_text_message_type(ctype):
    return normalize_message_ctype(ctype) in {'TEXT', 'TXT', ''}


def is_image_message_type(ctype):
    return normalize_message_ctype(ctype) in {
        'IMAGE', 'IMG', 'PIC', 'PICTURE', 'PHOTO', 'EMOTICON_IMAGE'
    }


def is_image_mixed_message_type(ctype):
    return normalize_message_ctype(ctype) in {
        'IMAGE_TEXT_MIX',
        'IMAGE_TEXT',
        'MIX_IMAGE_TEXT',
        'MIXED_IMAGE_TEXT',
        'MULTI_TYPE_MIX',
        'MULTI_TYPE',
        'MIXED_MESSAGE',
    }


def looks_like_image_address(text):
    text = str(text or '').strip()
    if not text:
        return False
    if re.search(r'\.(?:png|jpe?g|gif|webp|bmp|heic|heif)(?:[?#].*)?$', text, flags=re.I):
        return True
    if re.search(r'https?://|s3://|oss://|cos://|minio://|/|\\', text, flags=re.I) and re.search(
        r'image|img|pic|photo|wechat|wx|\.dat$',
        text,
        flags=re.I
    ):
        return True
    return False


CHAT_IMAGE_REMOTE_ROOT = os.environ.get('CHAT_IMAGE_REMOTE_ROOT', '/root/dify/dify-on-wechat').rstrip('/')
CHAT_IMAGE_BACKEND_URL_PREFIX = os.environ.get('CHAT_IMAGE_BACKEND_URL_PREFIX', '').rstrip('/')
CHAT_IMAGE_MULTIMODAL_CONFIG_PATH = os.environ.get(
    'CHAT_IMAGE_MULTIMODAL_CONFIG_PATH',
    'config/config_document_qasegment.json'
)
CHAT_IMAGE_MINIO_UPLOAD_ENABLED = os.environ.get('CHAT_IMAGE_MINIO_UPLOAD_ENABLED', '1') != '0'
CHAT_IMAGE_MINIO_UPLOAD_PREFIX = os.environ.get('CHAT_IMAGE_MINIO_UPLOAD_PREFIX', '').strip('/')
_CHAT_IMAGE_MINIO_RUNTIME = None
_CHAT_IMAGE_PUBLIC_URL_CACHE = {}


def is_http_url(text):
    return bool(re.match(r'https?://', str(text or '').strip(), flags=re.I))


def load_json_config_if_exists(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        logging.warning('load json config failed: %s\n%s', path, traceback.format_exc())
        return {}


def get_chat_image_minio_runtime():
    global _CHAT_IMAGE_MINIO_RUNTIME
    if _CHAT_IMAGE_MINIO_RUNTIME is not None:
        return _CHAT_IMAGE_MINIO_RUNTIME
    _CHAT_IMAGE_MINIO_RUNTIME = {}
    if not CHAT_IMAGE_MINIO_UPLOAD_ENABLED:
        return _CHAT_IMAGE_MINIO_RUNTIME

    multimodal_config = load_json_config_if_exists(CHAT_IMAGE_MULTIMODAL_CONFIG_PATH)
    minio_config_path = (
        multimodal_config.get('minio_config_path')
        or multimodal_config.get('minio_config')
        or config.get('minio_config_path')
        or 'config/minio_config.json'
    )
    minio_config = load_json_config_if_exists(minio_config_path)
    if not minio_config:
        return _CHAT_IMAGE_MINIO_RUNTIME

    bucket = (
        os.environ.get('CHAT_IMAGE_MINIO_BUCKET')
        or multimodal_config.get('bucket_name')
        or minio_config.get('bucket_name')
        or minio_config.get('bucket')
        or 'boot-admin'
    )
    upload_prefix = CHAT_IMAGE_MINIO_UPLOAD_PREFIX
    if not upload_prefix:
        base_prefix = str(multimodal_config.get('upload_prefix') or 'knowledge/multimodal').strip('/')
        upload_prefix = f"{base_prefix}/chat_qa_images".strip('/')
    prefix_fileservice_url = str(multimodal_config.get('prefix_fileservice_url') or '').rstrip('/')

    try:
        from data_control_tools.minio_tools import MinioTools
        with open(os.devnull, 'w') as devnull, contextlib.redirect_stdout(devnull):
            minio_client = MinioTools(minio_config)
    except Exception:
        logging.warning('init MinIO client failed for chat image public url\n%s', traceback.format_exc())
        return _CHAT_IMAGE_MINIO_RUNTIME

    _CHAT_IMAGE_MINIO_RUNTIME = {
        'client': minio_client,
        'bucket': bucket,
        'upload_prefix': upload_prefix,
        'prefix_fileservice_url': prefix_fileservice_url,
    }
    return _CHAT_IMAGE_MINIO_RUNTIME


def get_backend_file_path_from_image_info(image_info):
    backend_file_path = str(image_info.get('backend_file_path') or '').strip()
    if backend_file_path:
        return backend_file_path
    backend_path = str(image_info.get('backend_path') or image_info.get('address') or '').strip()
    if not backend_path or is_http_url(backend_path) or re.match(r'^(?:s3|oss|cos|minio)://', backend_path, flags=re.I):
        return ''
    if backend_path.startswith('/'):
        return backend_path
    return f"{CHAT_IMAGE_REMOTE_ROOT}/{backend_path.lstrip('/')}"


def build_chat_image_object_key(local_file_path, image_info, runtime):
    rel_value = str(image_info.get('backend_path') or image_info.get('address') or local_file_path or '').strip()
    if local_file_path.startswith(CHAT_IMAGE_REMOTE_ROOT + '/'):
        rel_value = local_file_path[len(CHAT_IMAGE_REMOTE_ROOT) + 1:]
    ext = os.path.splitext(local_file_path)[1] or os.path.splitext(rel_value)[1] or '.jpg'
    digest = hashlib.sha1(rel_value.encode('utf-8')).hexdigest()
    upload_prefix = str(runtime.get('upload_prefix') or 'chat_qa_images').strip('/')
    return f"{upload_prefix}/{digest[:2]}/{digest}{ext}".lstrip('/')


def build_chat_image_public_url(runtime, object_key):
    bucket = str(runtime.get('bucket') or '').strip('/')
    prefix_fileservice_url = str(runtime.get('prefix_fileservice_url') or '').rstrip('/')
    object_key = str(object_key or '').lstrip('/')
    if prefix_fileservice_url and bucket:
        return f"{prefix_fileservice_url}/{bucket}/{object_key}"
    if prefix_fileservice_url:
        return f"{prefix_fileservice_url}/{object_key}"
    minio_client = runtime.get('client')
    if minio_client:
        return minio_client.generate_public_url(object_key, bucket_name=bucket or None, permanent=False)
    return ''


def enrich_image_info_with_public_url(image_info):
    if not isinstance(image_info, dict):
        return image_info
    if is_http_url(image_info.get('backend_url')):
        return image_info

    local_file_path = get_backend_file_path_from_image_info(image_info)
    if not local_file_path or not os.path.exists(local_file_path):
        return image_info
    if local_file_path in _CHAT_IMAGE_PUBLIC_URL_CACHE:
        image_info.update(_CHAT_IMAGE_PUBLIC_URL_CACHE[local_file_path])
        return image_info

    runtime = get_chat_image_minio_runtime()
    minio_client = runtime.get('client') if isinstance(runtime, dict) else None
    if not minio_client:
        return image_info

    object_key = build_chat_image_object_key(local_file_path, image_info, runtime)
    bucket = runtime.get('bucket')
    try:
        content_type = mimetypes.guess_type(local_file_path)[0]
        success = minio_client.upload_file(
            local_file_path,
            object_key,
            bucket_name=bucket,
            content_type=content_type
        )
        if not success:
            return image_info
        public_url = build_chat_image_public_url(runtime, object_key)
        public_info = {
            'backend_url': public_url,
            'public_url': public_url,
            'minio_bucket': bucket,
            'minio_object_key': object_key,
            'minio_path': f"{bucket}/{object_key}" if bucket else object_key,
        }
        public_info = {key: value for key, value in public_info.items() if value}
        _CHAT_IMAGE_PUBLIC_URL_CACHE[local_file_path] = public_info
        image_info.update(public_info)
    except Exception:
        logging.warning('upload chat image to MinIO failed: %s\n%s', local_file_path, traceback.format_exc())
    return image_info


def normalize_backend_image_info(image_info):
    if not isinstance(image_info, dict):
        return image_info
    image_info = dict(image_info)
    backend_url = str(image_info.get('backend_url') or '').strip()
    if not backend_url and 'backend_url' in image_info:
        image_info.pop('backend_url', None)
    if backend_url and not (is_http_url(backend_url) or re.match(r'^(?:s3|oss|cos|minio)://', backend_url, flags=re.I)):
        image_info.pop('backend_url', None)
        if not image_info.get('backend_path'):
            image_info['backend_path'] = backend_url
        if not image_info.get('address'):
            image_info['address'] = backend_url
    address = str(image_info.get('address') or '').strip()
    if not address:
        backend_path = str(image_info.get('backend_path') or '').strip()
        if backend_path:
            address = backend_path
            image_info['address'] = backend_path
        else:
            backend_file_path = str(image_info.get('backend_file_path') or '').strip()
            if backend_file_path:
                address = backend_file_path
                image_info['address'] = backend_file_path
            else:
                return image_info

    if address.startswith(CHAT_IMAGE_REMOTE_ROOT + '/'):
        image_info.setdefault('backend_file_path', address)
        rel_path = address[len(CHAT_IMAGE_REMOTE_ROOT) + 1:]
        image_info.setdefault('backend_path', rel_path)
        return enrich_image_info_with_public_url(image_info)

    if is_http_url(address):
        image_info.setdefault('backend_url', address)
        return image_info

    if re.match(r'^(?:s3|oss|cos|minio)://', address, flags=re.I):
        image_info.setdefault('backend_url', address)
        return image_info

    image_info.setdefault('backend_path', address)
    if address.startswith('/'):
        image_info.setdefault('backend_file_path', address)
    else:
        image_info.setdefault('backend_file_path', f"{CHAT_IMAGE_REMOTE_ROOT}/{address.lstrip('/')}")
        if CHAT_IMAGE_BACKEND_URL_PREFIX:
            image_info.setdefault('backend_url', f"{CHAT_IMAGE_BACKEND_URL_PREFIX}/{address.lstrip('/')}")
    return enrich_image_info_with_public_url(image_info)


def is_image_placeholder_or_address(content):
    content = sanitize_chat_content(content)
    if not content:
        return False
    if re.search(r'<img\b|!\[[^\]]*\]\([^)]+\)', content, flags=re.I):
        return True
    if re.fullmatch(r'[\[【(（]?\s*(图片|image|img|photo|picture)\s*\d*\s*[\]】)）]?', content, flags=re.I):
        return True
    if looks_like_image_address(content):
        return True
    return False


def is_image_only_placeholder_content(content):
    content = sanitize_chat_content(content)
    if not content:
        return False
    return bool(re.fullmatch(r'(?:[\[【(（]?\s*(?:图片|image|img|photo|picture)\s*\d*\s*[\]】)）]?\s*)+', content, flags=re.I))


def is_generic_image_answer_text(content):
    content = sanitize_chat_content(content)
    if not content:
        return False
    if looks_like_image_reference_answer(content) or is_image_only_placeholder_content(content):
        return True
    answer_norm = normalize_qa_text(content)
    return answer_norm in {
        '图片答案', '图片', '见图片', '看图片', '参考图片',
        'imageanswer', 'seeimage', 'seetheimage', 'referimage', 'refertoimage'
    }


def collect_image_addresses(value, max_depth=3):
    addresses = []

    def _add_address(text):
        text = str(text or '').strip()
        if text and text not in addresses and looks_like_image_address(text):
            addresses.append(text)

    def _walk(obj, depth):
        if depth < 0 or obj is None:
            return
        if isinstance(obj, str):
            _add_address(obj)
            for url in re.findall(r'(?:https?|s3|oss|cos|minio)://[^\s<>"\'`，,]+', obj, flags=re.I):
                _add_address(url)
            return
        if isinstance(obj, (int, float, bool)):
            return
        if isinstance(obj, dict):
            for key, item in obj.items():
                key_norm = normalize_qa_text(key)
                if key_norm in {
                    'content', 'conent', 'url', 'path', 'filepath', 'filename', 'fileurl',
                    'imageurl', 'imagepath', 'cdnurl', 'publicurl', 'externurl', 'localpath',
                    'mediaurl', 's3path', 'thumburl', 'image'
                }:
                    _walk(item, depth - 1)
                elif depth > 0:
                    _walk(item, depth - 1)
            return
        if isinstance(obj, (list, tuple, set)):
            for item in obj:
                _walk(item, depth - 1)

    _walk(value, max_depth)
    return addresses


def build_image_message_content_and_supplement(message_info, send_content, ctype, image_label):
    addresses = []
    for value in [
        send_content,
        message_info.get('content'),
        message_info.get('conent'),
        message_info.get('url'),
        message_info.get('path'),
        message_info.get('file_path'),
        message_info.get('file_url'),
        message_info.get('image_url'),
        message_info.get('image_path'),
        message_info.get('local_path'),
        message_info.get('public_url'),
        message_info.get('original_info'),
    ]:
        for address in collect_image_addresses(value):
            if address not in addresses:
                addresses.append(address)

    image_info = {
        'label': image_label,
        'type': 'image',
        'ctype': ctype,
    }
    if addresses:
        image_info['address'] = addresses[0]
        if len(addresses) > 1:
            image_info['addresses'] = addresses
    if message_info.get('is_image_download') is not None:
        image_info['is_image_download'] = bool(message_info.get('is_image_download'))

    image_info = normalize_backend_image_info(image_info)
    return f"（{image_label}）", {'images': [image_info]}


def parse_mixed_message_items(send_content):
    if isinstance(send_content, list):
        return send_content
    if isinstance(send_content, dict):
        return send_content.get('items') or send_content.get('content') or []
    text = str(send_content or '').strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get('items') or data.get('content') or []
    return []


def build_mixed_image_text_content_and_supplement(message_info, send_content, ctype, start_image_index):
    items = parse_mixed_message_items(send_content)
    if not items:
        image_label = f"图片{start_image_index}"
        content, supplement = build_image_message_content_and_supplement(
            message_info,
            send_content,
            ctype,
            image_label
        )
        return content, supplement, 1

    content_parts = []
    image_infos = []
    image_index = start_image_index
    for item in items:
        if not isinstance(item, dict):
            text = sanitize_chat_content(item)
            if text:
                content_parts.append(text)
            continue
        item_type = normalize_message_ctype(item.get('type'))
        item_content = item.get('content') or item.get('url') or item.get('path') or item.get('file_path') or ''
        if item_type in {'TEXT', 'TXT'}:
            text = sanitize_chat_content(item_content)
            if text:
                content_parts.append(text)
            continue
        if item_type in {'IMAGE', 'IMG', 'PIC', 'PICTURE', 'PHOTO'} or collect_image_addresses(item):
            image_label = f"图片{image_index}"
            image_index += 1
            content_parts.append(f"（{image_label}）")
            addresses = []
            for value in [item, item_content]:
                for address in collect_image_addresses(value):
                    if address not in addresses:
                        addresses.append(address)
            image_info = {
                'label': image_label,
                'type': 'image',
                'ctype': ctype,
            }
            if addresses:
                image_info['address'] = addresses[0]
                if len(addresses) > 1:
                    image_info['addresses'] = addresses
            image_info = normalize_backend_image_info(image_info)
            image_infos.append(image_info)

    content = ' '.join(part for part in content_parts if part).strip()
    supplement = {'images': image_infos} if image_infos else {}
    used_count = max(0, image_index - start_image_index)
    if not content and image_infos:
        content = ' '.join(f"（{image['label']}）" for image in image_infos)
    return content, supplement, used_count


def format_supplement_image_placeholders(supplement):
    if not isinstance(supplement, dict):
        return ''
    labels = []
    for index, image in enumerate(supplement.get('images') or [], 1):
        label = ''
        if isinstance(image, dict):
            label = str(image.get('label') or '').strip()
        labels.append(label or f"图片{index}")
    return ' '.join(f"（{label}）" for label in labels)


def is_group_system_noise(content):
    content = sanitize_chat_content(content)
    if not content:
        return True
    compact = normalize_qa_text(content)
    if compact in {'群聊信息已更新', '群公告已更新', '群名称已更新'}:
        return True
    if re.fullmatch(r'[\[【(（]?\s*(群聊信息|群公告|群名称|群二维码|群信息)\s*已更新\s*[\]】)）]?', content):
        return True
    if re.search(r'(通过扫描|邀请).{0,30}(加入群聊|加入了群聊)', content):
        return True
    if re.search(r'(欢迎加入|欢迎.*入群|入群卖家|群昵称|群公告|群规则|定期清退|清理不在问卷池|不要随意拉人进群)', content):
        if re.search(r'(群|卖家|问卷|公告|运营资料|昵称|清退|拉人)', content):
            return True
    if re.search(r'(此群专注|此群是|本群是|群内请|群里请|请所有入群)', content):
        return True
    if re.search(r'修改群内?备注|修改群被?姓名备注|基础信息问卷|填写.{0,12}问卷|提交问卷|再提问|不要拉人|拉人入群|后续.*邀请|定期清人|改个备注|了解.{0,8}业务|代运营/孵化', content):
        return True
    return False


def is_promo_noise_chat_content(content):
    content = sanitize_chat_content(content)
    if not content:
        return False
    if re.search(r'[?？]|吗|嘛|么|是否|怎么|为什么|能不能|有没有|什么情况|不显示|找不到|打不开', content):
        return False

    strong_patterns = [
        r'扫码.{0,12}报名',
        r'扫描.{0,12}二维码',
        r'报名链接',
        r'用.{0,12}链接.{0,12}优惠',
        r'提供的链接.{0,12}优惠',
        r'点击.{0,12}(报名|领取|加入)',
        r'名额有限',
        r'席位有限',
        r'限时福利',
        r'新人福利',
        r'服务商礼包',
        r'免费领取',
        r'闭门私董会',
        r'招商大会',
        r'大卖.{0,8}私董会',
        r'直播.{0,12}报名',
        r'直播课堂',
        r'正在开播',
        r'卖家成长训练营',
        r'热卖选品指南',
        r'消费趋势数据',
        r'选品风向标',
        r'爆单选品运营指南',
        r'课程.{0,12}报名',
        r'峰会.{0,12}报名',
        r'trial bonus',
    ]
    if any(re.search(pattern, content, flags=re.I) for pattern in strong_patterns):
        return True

    promo_keywords = [
        '报名', '福利', '优惠', '折扣', '礼包', '私董会', '大会', '峰会',
        '直播', '课程', '席位', '名额', '扫码', '二维码', '海报', '活动详情',
        '注册链接', '立即加入', '限时', '免费领取',
    ]
    hit_count = sum(1 for keyword in promo_keywords if keyword in content)
    has_link_or_qr = bool(re.search(r'https?://|www\.|二维码|扫码|海报', content, flags=re.I))
    return hit_count >= 3 and has_link_or_qr


CHAT_URL_PATTERN = r'https?://[^\s，。；、）)】\]\}<>"“”]+|www\.[^\s，。；、）)】\]\}<>"“”]+'


def replace_chat_urls(text, replacement=''):
    return re.sub(CHAT_URL_PATTERN, replacement, str(text or ''), flags=re.I)


def is_resource_link_only_noise(content):
    content = sanitize_chat_content(content)
    if not content:
        return False
    deictic_patterns = [
        r'^\s*for your reference\s*$',
        r'^\s*check this\s*$',
        r'^\s*check this to (?:set up|register|create|open).{0,80}(?:acc|account|register|transfer)?.*$',
        r'^\s*sign in by this link and tap\s*\[[^\]]+\]\s*$',
        r'^\s*when you make transfer,?\s*you will need this\.?\s*$',
        r"^\s*and here[’'\"]?s a detailed guide.*take a look.*$",
        r'^.*注册流程.{0,12}参考这里面.*$',
        r'^.*参考这里面.{0,12}(?:详细|每一步).*$',
        r'^\s*来注册\s*$',
        r'^\s*click this,?\s*provide passport.*trial bonus.*$',
    ]
    if any(re.search(pattern, content, flags=re.I) for pattern in deictic_patterns):
        return True
    if not re.search(r'https?://|www\.|docs\.qq\.com|kks\.ink', content, flags=re.I):
        return False
    without_url = replace_chat_urls(content)
    without_mention = re.sub(r'@[^ \n\r\t\u2005]+', '', without_url)
    norm = normalize_qa_text(without_mention)
    if not norm:
        return True
    if len(norm) <= 12 and re.search(r'教程|合集|链接|资料|文档|官网|学习|参考|这里|查看|指南|入驻链接', without_mention):
        return True
    if re.search(r'(请|可以)?.{0,4}(在|去|到)?.{0,8}(官网|文档|链接|教程|资料).{0,8}(学习|查看|参考|查询)', without_mention):
        return True
    return False


def is_case_coordination_noise(content):
    content = sanitize_chat_content(content)
    if not content:
        return False
    if re.search(
        r'帮你申诉|帮你催|我帮你|已反馈|给你处理|我来处理|我看看|我再看看|耐心等待|过段时间再尝试|你的朋友如果注册|后续我们也会邀请|反馈下你的问题|定点帮你看|帮你看下你的店铺|提交申诉|开个case.{0,8}申诉|明天再尝试登录|不是官方的技术原因|服务商资源|添加我微信|加我微信|推荐招商经理|其他卖家都可以.{0,12}再尝试|再尝试下|无法登录的bug|选择客服助手即可|客服助手即可|自己找一下|@我邮箱号码|邮箱号码|订单号发给后台客服|把订单号发给后台客服|发给后台客服咨询|账单\\s*id.{0,12}后台客服|费用.{0,20}账单\\s*id.{0,20}后台客服|后台客服.{0,12}判断是什么支出|光看这个我看不出来|换浏览器.{0,20}VPN.{0,30}(?:隔天|明天|今天|再试|多尝试)|如果今天无法连接.{0,20}隔天',
        content
    ):
        return True
    if re.search(
        r"send me .*?(phone|email)|register phone number|register email|speed up the process|pay agent|agent .*get code|ask an agent|agent\s*/\s*HR|tax beurea|get the register code|then i can[’'\"]?t do it now|how can we help|i don[’'\"]?t seem to have",
        content,
        flags=re.I
    ):
        return True
    if re.search(r'mars\s*mind|账号要养|分配了个账号|小助手.{0,12}启用|用文字.{0,8}咨询小助手|有问题请@.*客服助手|@[^ \n\r\t\u2005]{0,80}(?:客服助手|小助手)|具体截图看看|截图看看|升级知识库|审核功能.{0,20}(?:上线|会上)|当前有过的对话.{0,12}学习|机器网络.{0,12}修复|机器人在群里面|观察到对应的对话|不需要联系技术支持|网络问题.{0,12}刷新|近期.{0,8}bug|bug.{0,12}(?:正在修复|修复中|期间)|目前.{0,8}bug期间|系统.{0,12}升级.{0,20}bug|系统.{0,20}bug.{0,20}(?:改天|再尝试|VPN|修复)|我们已在修复|正在修复|紧急修复|近期恢复正常|改天再尝试|下个星期再尝试|下周再尝试', content, flags=re.I):
        return True
    if re.search(r'\b(noted|one moment|wait a moment|oh[, ]+sorry|sorry[, ]+i misunderstood)\b', content, flags=re.I):
        return True
    return False


def is_obvious_offtopic_noise(content):
    content = sanitize_chat_content(content)
    if not content:
        return False
    domain_signal = re.search(
        r'美客多|mercado|meli|wayfair|payoneer|skyremit|skyee|KYC|RFC|SKU|FBM|FULL|店铺|账号|入驻|注册|审核|上传|物流|收款|绑定|广告|发货|揽收|订单|类目|刊登|上架|商品|资料|护照|签证|税|银行|流水|平台|后台',
        content,
        flags=re.I
    )
    if domain_signal:
        return False
    if re.search(r'手抓饼|芝士|烤箱|离焦镜|三年级|录播|作业|热镀锌|群里姐妹|项目部|提前入园|弄个提前|供货还是运输', content):
        return True
    if len(normalize_qa_text(content)) <= 12 and re.search(r'太晚了|哈哈|捂脸|抱拳|辛苦|感谢|谢谢|收到', content):
        return True
    return False


def is_ack_with_emoji_noise(content):
    content = sanitize_chat_content(content)
    no_emoji_text = re.sub(r'[\[【(（][^\]】)）]{1,12}[\]】)）]', '', content).strip()
    no_emoji_norm = normalize_qa_text(no_emoji_text)
    ack_text = {normalize_qa_text(text) for text in NOISE_ACK_TEXT}
    return no_emoji_norm in ack_text


def is_noise_chat_content(content):
    content = sanitize_chat_content(content)
    if not content:
        return True
    lower_content = content.lower().strip()
    if lower_content.startswith(('<sysmsg', '<msg', '<?xml')) or '<![cdata[' in lower_content:
        return True
    if is_image_placeholder_or_address(content):
        return False
    if is_group_system_noise(content):
        return True
    if is_promo_noise_chat_content(content):
        return True
    if is_resource_link_only_noise(content):
        return True
    if is_case_coordination_noise(content):
        return True
    if is_obvious_offtopic_noise(content):
        return True
    if is_ack_with_emoji_noise(content):
        return True
    if content.count('�') / max(1, len(content)) > 0.03:
        return True

    if content.lstrip().startswith('@'):
        after_first_mention = re.sub(r'@[^ \n\r\t\u2005]+', '', content, count=1).strip()
        has_question_signal = re.search(r'[?？吗呢]|怎么|有没有|什么|是否|可以|能不能|能否|麻烦|帮忙', content)
        has_answer_signal = re.search(
            r'是|不是|需要|无需|可以|不能|建议|填写|提供|提交|属于|指|适合|必须|先|然后|如果|即可',
            after_first_mention
        )
        if len(after_first_mention) <= 20 and not has_question_signal and not has_answer_signal:
            return True

    no_url = replace_chat_urls(content)
    no_mention = re.sub(r'@[^ \n\r\t\u2005]+', '', no_url)
    meaningful = re.sub(r'[\W_]+', '', no_mention, flags=re.U)
    ack_text = {re.sub(r'[\W_]+', '', text.lower()) for text in NOISE_ACK_TEXT}
    if not meaningful:
        return True
    if meaningful.lower() in ack_text:
        return True
    if len(meaningful) <= 1:
        return True
    if len(content) >= 80 and not re.search(r'[\u4e00-\u9fff]', content):
        long_tokens = re.findall(r'[A-Za-z0-9+/=_-]{80,}', content)
        if long_tokens:
            return True
    return False


def should_keep_image_payload_when_text_is_noise(content):
    """
    图文混合消息里，文本可能只是引用包装、@ 尾巴或不可读编码。
    这类文本应丢掉但保留图片；广告/群公告/个案协作等业务噪声仍整条丢弃。
    """
    content = sanitize_chat_content(content)
    if not content:
        return True
    if is_group_system_noise(content):
        return False
    if is_promo_noise_chat_content(content):
        return False
    if is_resource_link_only_noise(content):
        return False
    if is_case_coordination_noise(content):
        return False
    if is_obvious_offtopic_noise(content):
        return False
    if is_ack_with_emoji_noise(content):
        return False
    if content.count('�') / max(1, len(content)) > 0.03:
        return True
    no_url = replace_chat_urls(content)
    no_mention = re.sub(r'@[^ \n\r\t\u2005]+', '', no_url)
    meaningful = re.sub(r'[\W_]+', '', no_mention, flags=re.U)
    return not meaningful or len(meaningful) <= 1


def normalize_qa_text(text):
    return re.sub(r'[\W_]+', '', str(text or '').lower())


def is_null_answer(answer):
    answer_norm = normalize_qa_text(answer)
    return answer_norm in {'', 'null', 'none', '无', '没有', 'allnull'}


def is_weak_answer(answer):
    answer_norm = normalize_qa_text(answer)
    if answer_norm in {
        '对', '对的', '是', '是的', '嗯', '嗯嗯', '可以', '可以的',
        '看着应该是了', '应该是', '应该可以', '没问题', '收到', '好的',
        'yes', 'no', 'yep', 'nope', 'sure', 'thanks', 'thankyou', 'thx',
        'noted', 'notedamoment', 'onemoment', 'waitamoment', 'sorry', 'ohsorry',
        'alright',
    }:
        return True
    if is_request_for_customer_info(answer) or is_question_like_text(answer):
        return True
    if len(answer_norm) <= 2:
        return True
    return False


def is_weak_generated_answer(answer):
    answer_norm = normalize_qa_text(answer)
    if answer_norm in {
        '对', '对的', '是', '是的', '嗯', '嗯嗯', '可以', '可以的',
        '看着应该是了', '应该是', '应该可以', '没问题', '收到', '好的',
        'yes', 'no', 'yep', 'nope', 'sure', 'thanks', 'thankyou', 'thx',
        'noted', 'notedamoment', 'onemoment', 'waitamoment', 'sorry', 'ohsorry',
        'alright',
    }:
        return True
    if len(answer_norm) <= 2:
        return True
    if is_question_like_text(answer):
        return True
    return False


def is_request_for_customer_info(content):
    content = sanitize_chat_content(content)
    if not content:
        return False
    if re.search(r'(--》|->|=>)', content):
        return False
    if re.search(r'(send|provide|share).{0,30}(phone|email|mail|mobile|account|screenshot)', content, flags=re.I):
        return True
    return bool(re.search(
        r'(可以|能否|能不能|麻烦|请|请问|辛苦).*?(说一下|发一下|回复|提供|确认|截图|给我|告知|上传|填一下|看一下|同步一下)',
        content
    ))


def is_question_like_text(content):
    content = sanitize_chat_content(content)
    if not content:
        return False
    if re.search(r'(--》|->|=>)', content):
        return False
    answer_signal = re.search(r'需要|不需要|无需|填写|提供|提交|先.*然后|如果.*就|必须|不能|不要|只要|即可', content)
    if answer_signal:
        return False
    if re.search(r'^\s*(which|what|how|do you|did you|are you|can you|could you|may i|would you)\b', content, flags=re.I):
        return True
    return bool(re.search(r'[?？]\s*$', content) or re.search(r'(吗|嘛|么|呢|是否|是不是|能不能|需不需要|有没有|什么情况|多少|几多|是吧)\s*$', content))


def is_candidate_answer_like_content(content):
    content = sanitize_chat_content(content)
    if not content:
        return False
    if is_request_for_customer_info(content) or is_question_like_text(content):
        return False
    question_signal = re.search(
        r'[?？]|吗|嘛|么|呢|是否|是不是|能不能|需不需要|有没有|什么|哪个|哪里|为什么|怎么|多少|几多|是吧',
        content
    )
    answer_signal = re.search(
        r'--》|->|=>|：|:|需要|不需要|无需|可以|建议|填写|提供|提交|先|然后|如果|会要求|请|必须|不能|不要|只要|即可',
        content
    )
    if question_signal and not answer_signal:
        return False
    return True


def text_overlap_ratio(text_a, text_b):
    text_a = normalize_qa_text(text_a)
    text_b = normalize_qa_text(text_b)
    if not text_a or not text_b:
        return 0.0
    if text_a in text_b or text_b in text_a:
        return 1.0
    chars_a = set(text_a)
    chars_b = set(text_b)
    return len(chars_a & chars_b) / max(1, min(len(chars_a), len(chars_b)))


def is_similar_qa(existing_qa, new_qa):
    q_overlap = text_overlap_ratio(existing_qa.get('q', ''), new_qa.get('q', ''))
    a_overlap = text_overlap_ratio(existing_qa.get('a', ''), new_qa.get('a', ''))
    if q_overlap >= 0.86:
        return True
    if a_overlap >= 0.95 and q_overlap >= 0.55:
        return True
    return False


def clean_qa_info(qa_info):
    qa_info = dict(qa_info)
    qa_info['q'] = str(qa_info.get('q', '')).strip()
    answer = str(qa_info.get('a', '')).strip()
    answer = re.sub(r'\n来源:\s*null\s*$', '', answer, flags=re.I).strip()
    qa_info['a'] = answer
    source = str(qa_info.get('source', '')).strip()
    if normalize_qa_text(source) == 'null':
        source = ''
    qa_info['source'] = source
    return qa_info


def clean_and_dedupe_qa_list(qa_list):
    result = []
    for qa_info in qa_list:
        qa_info = clean_qa_info(qa_info)
        if not qa_info.get('q'):
            continue
        if is_null_answer(qa_info.get('a', '')):
            continue
        if is_weak_generated_answer(qa_info.get('a', '')):
            continue
        duplicate_index = None
        for index, existing_qa in enumerate(result):
            if is_similar_qa(existing_qa, qa_info):
                duplicate_index = index
                break
        if duplicate_index is None:
            result.append(qa_info)
            continue

        existing_qa = result[duplicate_index]
        existing_is_null = is_null_answer(existing_qa.get('a', ''))
        new_is_null = is_null_answer(qa_info.get('a', ''))
        if existing_is_null and not new_is_null:
            result[duplicate_index] = qa_info
        elif existing_is_null == new_is_null and text_overlap_ratio(existing_qa.get('a', ''), qa_info.get('a', '')) >= 0.95:
            if len(qa_info.get('q', '')) < len(existing_qa.get('q', '')):
                result[duplicate_index] = qa_info
    return result


def normalize_quality_level(value, default='mid'):
    quality_norm = normalize_qa_text(value)
    if quality_norm in {'high', 'h', 'good', '高', '高质量', '优质', '高中低高'}:
        return 'high'
    if quality_norm in {'mid', 'medium', 'middle', 'm', '中', '中等', '中质量', '高中低中'}:
        return 'mid'
    if quality_norm in {'low', 'l', 'bad', '低', '低质量', '较低', '高中低低'}:
        return 'low'
    return default


def normalize_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    value_norm = normalize_qa_text(value)
    if value_norm in {'true', 'yes', 'y', '1', '是', '可以', '合格', 'qualified', '可进入', '进入', '可复用', '可评估'}:
        return True
    if value_norm in {'false', 'no', 'n', '0', '否', '不可以', '不合格', 'unqualified', '不进入', '不可复用', '不评估'}:
        return False
    return default


def normalize_reuse_scope(value, default='industry_specific'):
    scope_norm = normalize_qa_text(value)
    if not scope_norm:
        return default
    mapping = {
        'universal': 'universal',
        'general': 'universal',
        'allindustrycommon': 'universal',
        'crossindustry': 'universal',
        '全行业通用': 'universal',
        '跨行业通用': 'universal',
        '通用': 'universal',
        'industryspecific': 'industry_specific',
        'platformspecific': 'industry_specific',
        '行业专属': 'industry_specific',
        '行业级别': 'industry_specific',
        '专属行业级别': 'industry_specific',
        '平台内通用': 'industry_specific',
        '平台专属': 'industry_specific',
        'clientspecific': 'client_specific',
        'singleclient': 'client_specific',
        'singleclientonly': 'client_specific',
        'customerspecific': 'client_specific',
        'singlecustomer': 'client_specific',
        'singlecustomeronly': 'client_specific',
        'casespecific': 'client_specific',
        '单一client使用': 'client_specific',
        '单client使用': 'client_specific',
        'client专属': 'client_specific',
        '单一客户使用': 'client_specific',
        '单客户使用': 'client_specific',
        '客户专属': 'client_specific',
        '个案': 'client_specific',
        '个案专属': 'client_specific',
    }
    return mapping.get(scope_norm, default)


def infer_is_qualified(item, quality_level, reuse_scope):
    if reuse_scope == 'client_specific':
        return False
    return normalize_bool(item.get('is_qualified'), default=False)


def normalize_supplement(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {'items': value}
    if isinstance(value, str) and value.strip():
        try:
            data = json.loads(value)
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                return {'items': data}
        except Exception:
            return {'note': value.strip()}
    return {}


def normalize_string_list(value, max_items=12):
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = value.values()
    elif isinstance(value, (tuple, set)):
        items = list(value)
    else:
        items = re.split(r'[\n,，、;；|/]+', str(value))
    result = []
    for item in items:
        item = str(item or '').strip()
        if not item or item in result:
            continue
        result.append(item)
        if len(result) >= max_items:
            break
    return result


def merge_qa_tags(item, max_items=12):
    result = []
    for field in ('tags', 'tag', 'business_tags', 'scenario_tags', 'entity_tags', 'entities', 'es_tags'):
        for tag in normalize_string_list(item.get(field), max_items=max_items):
            if tag not in result:
                result.append(tag)
                if len(result) >= max_items:
                    return result
    return result


def normalize_confidence(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    if score > 1:
        score = score / 100.0
    return max(0.0, min(1.0, score))


def generalize_reusable_qa_text(text):
    """
    q/a 面向检索复用，不能暴露能定位到个人、店铺、账号或订单的标识。
    原始追溯信息仍保留在 source/source_quote/metadata 中。
    """
    text = str(text or '').strip()
    if not text:
        return text
    text = replace_chat_urls(text, '[链接]')
    text = re.sub(
        r'^\s*(?:hi|hello)?[\s,，]*sorry\s+i\s+missed\s+(?:the\s+)?(?:early|earlier)?\s*messages?\s*[:：,，-]*\s*',
        '',
        text,
        flags=re.I
    )
    text = re.sub(
        r'^\s*(?:yeah|yes|ok|okay|oh\s*,?\s*yes)[\s,，.。!！]+(?=\S)',
        '',
        text,
        flags=re.I
    )
    text = re.sub(r'后续提现是否也必须提到对公账户', '后续提现是否也必须提现到对公账户', text)
    text = re.sub(r'提现是否也必须提到对公账户', '提现是否也必须提现到对公账户', text)
    text = re.sub(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', '[邮箱]', text)
    text = re.sub(r'\b1[3-9]\d{9}\b', '[手机号]', text)
    text = re.sub(r'\b(?:wxid|ww|corp)[_-]?[A-Za-z0-9_-]{5,}\b', '[用户ID]', text, flags=re.I)
    text = re.sub(r'\bgh[_-][A-Za-z0-9_-]{5,}\b', '[用户ID]', text, flags=re.I)
    text = re.sub(r'\b[A-Za-z]{1,8}[-_]\d{5,}[-_A-Za-z0-9]*\b', '[业务ID]', text)
    text = re.sub(r'\b[A-Z0-9][A-Z0-9_-]{9,}\b', '[业务ID]', text)
    text = re.sub(r'(?<!\d)\d{6,}(?!\d)', '[数字ID]', text)
    text = re.sub(r'(账号|账户|店铺|订单|申请|工单|物流单|运单|case|Case|CASE)[：: ]*[A-Za-z0-9_-]{4,}', r'\1[已脱敏]', text)
    text = re.sub(r'(客户|卖家|用户|联系人|对接人|负责人|店主|运营|经理|同事)[：: ]+[A-Za-z][A-Za-z ._-]{1,30}', r'\1', text)
    text = re.sub(
        r'(?:此|该)?邮件是邀您入群[，,、\s]*(?:方便您)?(?:咨询和)?对接官方经理[。.!！]?',
        '',
        text
    )
    text = re.sub(r'(?:此|该)?邮件.{0,12}邀您入群.{0,24}(?:官方经理|招商经理|经理)[。.!！]?', '', text)

    person_label_exclude = {
        '资料', '账号', '账户', '店铺', '订单', '申请', '工单', '状态', '问题', '信息',
        '后台', '页面', '产品', '类目', '链接', '邮箱', '手机', '电话', '地址',
        '处理', '提交', '检查', '确认', '需要', '可以', '是否', '如何', '怎么',
        '失败', '通过', '审核', '开通', '绑定', '登录', '进入', '操作', '补充',
        '修改', '删除', '创建', '都要', '经历', '均需', '必须', '经验', '人员',
    }

    def _replace_labeled_person_name(match):
        label, name = match.group(1), match.group(2)
        if name.startswith('的') or any(token in name for token in person_label_exclude):
            return match.group(0)
        return label

    text = re.sub(
        r'(客户|卖家|用户|联系人|对接人|负责人|店主|运营|经理|同事)([\u4e00-\u9fff]{2,4})(?=的|，|,|。|；|;|\s|$)',
        _replace_labeled_person_name,
        text
    )
    return sanitize_chat_content(text)


def fix_source_bound_qa_text(qa_info):
    source_text = ' '.join([
        str(qa_info.get('source_quote') or ''),
        str(qa_info.get('a') or ''),
    ])
    generated_text = ' '.join([
        str(qa_info.get('q') or ''),
        str(qa_info.get('a') or ''),
    ])
    source_names_bank_of_china = re.search(r'\bbank of china\b|\bBOC\b|中国银行', source_text, flags=re.I)
    generated_has_ambiguous_china_bank = re.search(r'中国银行\s*App|中国银行(?:账户|流水|对账单)', generated_text)
    if (
        (
            re.search(r'\bchinese bank\b', source_text, flags=re.I)
            or generated_has_ambiguous_china_bank
        )
        and not source_names_bank_of_china
    ):
        qa_info = dict(qa_info)
        def _fix_china_bank_text(value):
            value = re.sub(r'中国银行\s*App', '中国本地银行 App', str(value or ''))
            value = re.sub(r'中国银行流水', '中国本地银行流水', value)
            value = re.sub(r'中国银行对账单', '中国本地银行对账单', value)
            value = re.sub(r'中国银行账户', '中国本地银行账户', value)
            return value

        for field in ('q', 'a'):
            qa_info[field] = _fix_china_bank_text(qa_info.get(field))
        for field in ('tags', 'quality_info'):
            if isinstance(qa_info.get(field), list):
                qa_info[field] = [_fix_china_bank_text(item) for item in qa_info[field]]
    return qa_info


def clean_reusable_answer_source_quote(text):
    text = generalize_reusable_qa_text(text)
    text = re.sub(r'^(?:@[^ \n\r\t\u2005]+[\s\u2005]*)+', '', text)
    text = re.sub(r'^(?:哦哦|哦|嗯嗯|嗯|好的|好|是的|对的|对)[，,。.!！\s]*', '', text)
    return sanitize_chat_content(text)


def prefer_source_quote_answer_when_safe(qa_info):
    source_quote = str(qa_info.get('source_quote') or '').strip()
    answer = str(qa_info.get('a') or '').strip()
    if (
        not source_quote
        or not answer
        or looks_like_image_reference_answer(answer)
        or looks_like_image_reference_answer(source_quote)
        or is_weak_generated_answer(source_quote)
    ):
        return qa_info
    if text_overlap_ratio(source_quote, answer) < 0.45:
        return qa_info
    source_norm = normalize_qa_text(source_quote)
    answer_norm = normalize_qa_text(answer)
    if len(source_norm) < len(answer_norm) * 0.75:
        return qa_info
    qa_info = dict(qa_info)
    qa_info['a'] = clean_reusable_answer_source_quote(source_quote)
    return qa_info


def get_display_platform_name(platform):
    platform_norm = normalize_qa_text(platform)
    if platform_norm in {'skyee', 'skyeetest', 'skyremit'}:
        return 'SkyRemit'
    if platform_norm in {'mercado', 'mercadolibre', 'meli', '美客多'}:
        return '美客多'
    if platform_norm in {'payoneer', '派安盈', 'individual20'}:
        return '派安盈'
    return ''


def fix_platform_placeholder_qa_text(qa_info):
    platform_name = get_display_platform_name(qa_info.get('platform') or qa_info.get('client'))
    if not platform_name:
        return qa_info
    q = str(qa_info.get('q') or '')
    fixed_q = re.sub(r'\bthis platform\b', platform_name, q, flags=re.I)
    fixed_q = re.sub(r'该平台|这个平台', platform_name, fixed_q)
    fixed_q = re.sub(r'平台（平台名未知）', platform_name, fixed_q)
    fixed_q = re.sub(r'平台\(平台名未知\)', platform_name, fixed_q)
    fixed_q = re.sub(r'在平台(?=[注册向上中，,：:])', f'在{platform_name}', fixed_q)
    if fixed_q != q:
        qa_info = dict(qa_info)
        qa_info['q'] = fixed_q
    return qa_info


def fix_context_only_bank_detail(qa_info):
    q = str(qa_info.get('q') or '')
    source_text = ' '.join([
        str(qa_info.get('a') or ''),
        str(qa_info.get('source_quote') or ''),
    ])
    context_only_bank_patterns = [
        (r'用户使用\s*China\s*Citic银行，?', 'China Citic'),
        (r'用户使用\s*中信银行，?', '中信银行'),
        (r'\s*\(\s*e\.?g\.?,?\s*China\s*Citic\s*\)', 'China Citic'),
        (r'\s*（\s*e\.?g\.?,?\s*China\s*Citic\s*）', 'China Citic'),
        (r'\s*,?\s*e\.?g\.?,?\s*China\s*Citic', 'China Citic'),
        (r'（如中信银行）', '中信银行'),
        (r'\(如中信银行\)', '中信银行'),
    ]
    fixed_q = q
    for pattern, token in context_only_bank_patterns:
        if re.search(token, source_text, flags=re.I):
            continue
        fixed_q = re.sub(pattern, '', fixed_q, flags=re.I)
    fixed_q = re.sub(r'，{2,}', '，', fixed_q).strip('，, ')
    if fixed_q != q:
        qa_info = dict(qa_info)
        qa_info['q'] = fixed_q
    return qa_info


def fix_unsupported_business_object_terms(qa_info):
    prompt_text = str(qa_info.get('from_chat_history') or '')
    if not prompt_text:
        return qa_info
    prompt_norm = normalize_qa_text(prompt_text)
    qa_info = dict(qa_info)
    q = str(qa_info.get('q') or '')
    if 'tiktok' in normalize_qa_text(q) and 'tiktok' not in prompt_norm:
        fixed_q = re.sub(r'TikTok\s*Shop\s*跨境店', '跨境店', q, flags=re.I)
        fixed_q = re.sub(r'TikTok\s*跨境店', '跨境店', fixed_q, flags=re.I)
        fixed_q = re.sub(r'TikTok\s*Shop', '跨境店', fixed_q, flags=re.I)
        fixed_q = re.sub(r'TikTok', '跨境店', fixed_q, flags=re.I)
        fixed_q = re.sub(r'跨境店\s*跨境店', '跨境店', fixed_q)
        qa_info['q'] = fixed_q
        if isinstance(qa_info.get('tags'), list):
            qa_info['tags'] = [
                tag for tag in qa_info['tags']
                if 'tiktok' not in normalize_qa_text(tag)
            ]
            if '跨境店' not in qa_info['tags']:
                qa_info['tags'].append('跨境店')
    return qa_info


def fix_overbroad_listing_type_question(qa_info):
    q = str(qa_info.get('q') or '')
    answer_text = ' '.join([
        str(qa_info.get('a') or ''),
        str(qa_info.get('source_quote') or ''),
    ])
    if (
        re.search(r'classic', q, flags=re.I)
        and re.search(r'premium', q, flags=re.I)
        and re.search(r'区别|difference', q, flags=re.I)
        and re.search(r'不选|默认|一般模式|default', answer_text, flags=re.I)
        and not re.search(r'费率|流量|分期|installment|traffic|rate', answer_text, flags=re.I)
    ):
        qa_info = dict(qa_info)
        qa_info['q'] = '在美客多上传 Listing 时，如果不选择 listing type，默认是什么模式？'
    return qa_info


def normalize_prompt_client(client):
    """将 client 规范为安全的 prompt 文件名；异常值只走通用模板。"""
    normalized = str(client or '').strip().lower().replace('-', '_')
    if not re.match(r'^[a-z0-9_]+$', normalized):
        return ''
    return normalized


def resolve_direct_llm_system_prompt(client=None):
    """加载通用抽取 Prompt，并在存在时追加当前客户的差异规则。"""
    client = normalize_prompt_client(client)
    default_path = os.path.join(DIRECT_LLM_PROMPT_DIR, 'extract.default.md')
    try:
        with open(default_path, encoding='utf-8') as f:
            base_prompt = f.read().strip()
    except (IOError, OSError):
        logging.exception('direct llm default prompt load failed, fallback to inline prompt')
        base_prompt = DIRECT_LLM_JSON_SYSTEM_INSTRUCTION.strip()

    client_prompt = ''
    if client:
        client_path = os.path.join(DIRECT_LLM_PROMPT_DIR, f'extract.{client}.md')
        try:
            with open(client_path, encoding='utf-8') as f:
                client_prompt = f.read().strip()
        except (IOError, OSError):
            client_prompt = ''

    system_prompt = f'{base_prompt}\n\n{client_prompt}' if client_prompt else base_prompt
    return system_prompt, {
        'client': client,
        'client_prompt_applied': bool(client_prompt),
        'prompt_hash': hashlib.sha256(system_prompt.encode('utf-8')).hexdigest()[:12],
    }


def build_direct_llm_system_prompt(system_prompt=None, client=None):
    # system_prompt 仍用于旧任务中的答案来源姓名解析；业务抽取规则统一按 client 路由，
    # 避免把自动生成的超长同事名单重复注入模型 system prompt。
    prompt, _ = resolve_direct_llm_system_prompt(client=client)
    return prompt


class DirectLLMJsonRequest(object):
    """
    直接请求 DeepSeek/OpenAI-compatible chat completions，要求返回 JSON。
    环境变量优先级：
    CHATKNOWLEDGE_LLM_API_KEY > DEEPSEEK_API_KEY > OPENAI_API_KEY > GLOBAL_CONFIG
    """
    def __init__(self, api_base=None, api_key=None, model=None, max_retries=3,
                 system_prompt=None, client=None, timeout=600):
        self.api_base = (
            api_base or
            os.environ.get('CHATKNOWLEDGE_LLM_API_BASE') or
            os.environ.get('DEEPSEEK_API_BASE') or
            os.environ.get('OPENAI_BASE_URL') or
            config.get('chatknowledge_llm_api_base') or
            config.get('deepseek_api_base') or
            config.get('openai_base_url') or
            'https://api.deepseek.com'
        ).rstrip('/')
        self.api_key = (
            api_key or
            os.environ.get('CHATKNOWLEDGE_LLM_API_KEY') or
            os.environ.get('DEEPSEEK_API_KEY') or
            os.environ.get('OPENAI_API_KEY') or
            config.get('chatknowledge_llm_api_key') or
            config.get('deepseek_api_key') or
            config.get('openai_api_key')
        )
        self.model = (
            model or
            os.environ.get('CHATKNOWLEDGE_LLM_MODEL') or
            os.environ.get('DEEPSEEK_MODEL') or
            config.get('chatknowledge_llm_model') or
            config.get('deepseek_model') or
            'deepseek-chat'
        )
        self.max_retries = max_retries
        self.timeout = timeout
        self.system_prompt, self.prompt_meta = resolve_direct_llm_system_prompt(client=client)
        self.client = self.prompt_meta['client']
        logging.info(
            'DirectLLMJsonRequest prompt client=%s client_prompt_applied=%s hash=%s',
            self.client or 'default',
            self.prompt_meta['client_prompt_applied'],
            self.prompt_meta['prompt_hash'],
        )
        self._stats = {
            'logical_requests': 0,
            'http_attempts': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'timeout_attempts': 0,
            'non_200_attempts': 0,
            'response_format_fallbacks': 0,
            'prompt_chars': 0,
            'completion_chars': 0,
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'elapsed_seconds': 0.0,
        }

    def validate_config(self):
        if not self.api_key:
            raise RuntimeError(
                'missing LLM api key: set CHATKNOWLEDGE_LLM_API_KEY or DEEPSEEK_API_KEY'
            )

    def get_stats(self):
        stats = dict(self._stats)
        stats['elapsed_seconds'] = round(stats['elapsed_seconds'], 3)
        stats['model'] = self.model
        stats['api_base'] = self.api_base
        stats.update(self.prompt_meta)
        return stats

    def _chat_completions_url(self):
        if self.api_base.endswith('/chat/completions'):
            return self.api_base
        return self.api_base + '/chat/completions'

    def request_json(self, paragraph):
        self._stats['logical_requests'] += 1
        self._stats['prompt_chars'] += len(str(paragraph or ''))
        request_started_at = time.monotonic()
        try:
            self.validate_config()
        except Exception:
            self._stats['failed_requests'] += 1
            self._stats['elapsed_seconds'] += time.monotonic() - request_started_at
            raise

        headers = {
            'Authorization': 'Bearer %s' % self.api_key,
            'Content-Type': 'application/json',
        }
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': self.system_prompt},
                {'role': 'user', 'content': paragraph},
            ],
            'temperature': 0.1,
            'stream': False,
            'response_format': {'type': 'json_object'},
        }
        url = self._chat_completions_url()
        last_error = 'unknown error'

        for attempt in range(self.max_retries):
            request_payload = dict(payload)
            try:
                logging.info(
                    'calling direct llm json api: base=%s model=%s attempt=%s',
                    self.api_base,
                    self.model,
                    attempt + 1
                )
                self._stats['http_attempts'] += 1
                response = requests.post(url, headers=headers, json=request_payload, timeout=self.timeout)
                if response.status_code in (400, 422) and 'response_format' in request_payload:
                    logging.warning('llm response_format rejected, retry without response_format: %s', response.text[:500])
                    self._stats['response_format_fallbacks'] += 1
                    request_payload.pop('response_format', None)
                    self._stats['http_attempts'] += 1
                    response = requests.post(url, headers=headers, json=request_payload, timeout=self.timeout)

                if response.status_code != 200:
                    self._stats['non_200_attempts'] += 1
                    last_error = 'http status %s' % response.status_code
                    logging.error('direct llm api non-200 status=%s body=%s', response.status_code, response.text[:1000])
                    continue

                result = response.json()
                content = result['choices'][0]['message']['content']
                usage = result.get('usage') or {}
                for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                    value = usage.get(key, 0)
                    if isinstance(value, int) and not isinstance(value, bool):
                        self._stats[key] += value
                self._stats['successful_requests'] += 1
                self._stats['completion_chars'] += len(str(content or ''))
                self._stats['elapsed_seconds'] += time.monotonic() - request_started_at
                return content
            except requests.exceptions.Timeout:
                self._stats['timeout_attempts'] += 1
                last_error = 'request timeout'
                logging.error('direct llm api timeout')
            except requests.exceptions.RequestException as e:
                last_error = 'request error: %s' % str(e)
                logging.error('direct llm api request error: %s', str(e))
            except Exception as e:
                last_error = 'unexpected error: %s' % str(e)
                logging.error('direct llm api unexpected error:\n%s', traceback.format_exc())

            if attempt < self.max_retries - 1:
                time.sleep(5)

        self._stats['failed_requests'] += 1
        self._stats['elapsed_seconds'] += time.monotonic() - request_started_at
        raise RuntimeError(
            'direct llm request failed after %s attempts: %s' % (
                self.max_retries,
                last_error
            )
        )


def strip_json_response_text(text):
    text = str(text or '').strip()
    text = re.sub(r'^\s*```(?:json)?\s*', '', text, flags=re.I)
    text = re.sub(r'\s*```\s*$', '', text)
    return text.strip()


def parse_llm_json_data(result):
    if not result:
        return {}
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        return {'items': result}

    text = strip_json_response_text(result)
    try:
        return json.loads(text)
    except Exception:
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def iter_llm_json_items(data):
    if isinstance(data, list):
        for item in data:
            yield item, None
        return
    if not isinstance(data, dict):
        return

    if isinstance(data.get('items'), list):
        for item in data['items']:
            yield item, None
        return

    for level_key in ('high', 'mid', 'medium', 'low'):
        if isinstance(data.get(level_key), list):
            for item in data[level_key]:
                yield item, level_key
    if data.get('q') and data.get('a'):
        yield data, None


def looks_like_image_reference_answer(text):
    text = str(text or '').strip()
    if not text:
        return False
    parts = [part.strip() for part in re.split(r'[\n,，]+', text) if part.strip()]
    if not parts:
        return False
    return all(looks_like_image_address(part) for part in parts)


def normalize_llm_qa_items(result, extra_info_dict=None, default_platform=None, candidate_source=''):
    extra_info_dict = extra_info_dict or {}
    try:
        data = parse_llm_json_data(result)
    except Exception:
        logging.error('parse direct llm json failed. raw=%s\n%s', result, traceback.format_exc())
        return []

    qa_list = []
    for item, quality_from_bucket in iter_llm_json_items(data):
        if not isinstance(item, dict):
            continue
        qa_info = dict(extra_info_dict)
        raw_q = str(item.get('q') or item.get('question') or '').strip()
        raw_a = str(item.get('a') or item.get('answer') or '').strip()
        q = generalize_reusable_qa_text(raw_q)
        a = raw_a if looks_like_image_reference_answer(raw_a) else generalize_reusable_qa_text(raw_a)
        if not q or not a:
            continue

        model_platform = str(
            item.get('platform') or item.get('marketplace') or item.get('inferred_platform') or ''
        ).strip()
        if model_platform == 'mix':
            model_platform = str(item.get('inferred_platform') or '').strip()
        client_platform = str(default_platform or '').strip() or model_platform or 'unknown'
        marketplace = model_platform if model_platform and model_platform != client_platform else ''

        quality_level = normalize_quality_level(
            item.get('quality_level') or item.get('quality') or quality_from_bucket,
            default='mid'
        )
        reuse_scope = normalize_reuse_scope(item.get('reuse_scope'))

        qa_info.update({
            'q': q,
            'a': a,
            'source': str(item.get('source') or candidate_source or '').strip(),
            'platform': client_platform,
            'client': client_platform,
            'quality_level': quality_level,
            'is_qualified': infer_is_qualified(item, quality_level, reuse_scope),
            'quality_reason': str(item.get('quality_reason') or item.get('reason') or '').strip(),
            'tags': merge_qa_tags(item),
            'reuse_scope': reuse_scope,
            'confidence': normalize_confidence(item.get('confidence')),
            'source_quote': str(item.get('source_quote') or '').strip(),
        })
        if marketplace:
            qa_info['marketplace'] = marketplace
        if model_platform:
            qa_info['model_platform'] = model_platform
        if qa_info['quality_reason']:
            qa_info['reason'] = qa_info['quality_reason']
        qa_info['quality_info'] = normalize_string_list(item.get('quality_info'))
        qa_info = fix_source_bound_qa_text(qa_info)
        qa_info = prefer_source_quote_answer_when_safe(qa_info)
        qa_info = fix_platform_placeholder_qa_text(qa_info)
        qa_info = fix_context_only_bank_detail(qa_info)
        qa_info = fix_unsupported_business_object_terms(qa_info)
        qa_info = fix_overbroad_listing_type_question(qa_info)
        qa_list.append(qa_info)
    return qa_list


def load_jsonl_qa_file(qa_file):
    qa_list = []
    if not qa_file or not os.path.exists(qa_file):
        logging.warning('qa_file not found: %s', qa_file)
        return qa_list

    with open(qa_file, encoding='utf8') as f:
        content = f.read().strip()
    if not content:
        return qa_list

    try:
        data = json.loads(content)
        if isinstance(data, dict):
            if any(key in data for key in ('high', 'mid', 'low')):
                for key in ('high', 'mid', 'low'):
                    for qa_info in data.get(key, []):
                        qa_info = dict(qa_info)
                        qa_info.setdefault('quality_level', key)
                        qa_list.append(qa_info)
                return qa_list
            if isinstance(data.get('items'), list):
                return [item for item in data['items'] if isinstance(item, dict)]
            if data.get('q') and data.get('a'):
                return [data]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except Exception:
        pass

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            logging.error('parse qa json line failed file=%s line=%s', qa_file, line[:500])
            continue
        if isinstance(item, dict):
            qa_list.append(item)
    return qa_list


def build_quality_bucket_data(qa_list):
    bucket_data = {'high': [], 'mid': [], 'low': []}
    for qa_info in qa_list:
        if not isinstance(qa_info, dict):
            continue
        qa_info = dict(qa_info)
        quality_level = normalize_quality_level(
            qa_info.get('quality_level') or qa_info.get('quality'),
            default='mid'
        )
        qa_info['quality_level'] = quality_level
        bucket_data[quality_level].append(qa_info)
    return bucket_data


def write_quality_bucket_file(input_file, output_file):
    qa_list = load_jsonl_qa_file(input_file)
    bucket_data = build_quality_bucket_data(qa_list)
    with open(output_file, 'w', encoding='utf8') as f:
        json.dump(bucket_data, f, ensure_ascii=False, indent=2)
    logging.info(
        'write direct llm quality bucket file: input=%s output=%s high=%s mid=%s low=%s',
        input_file,
        output_file,
        len(bucket_data['high']),
        len(bucket_data['mid']),
        len(bucket_data['low'])
    )
    return output_file


def build_direct_llm_quality_batch(batch_file, output_batch_file, process_field_num=4,
                                   output_suffix='_direct_llm_quality_and_resplit.txt'):
    """
    直接 LLM 抽取阶段已经返回 quality_level。这里只把 JSONL 抽取文件转换成
    原 Dify 质量评估产物兼容的 {"high": [], "mid": [], "low": []} 文件，
    让后续 schema_trans 和 ES 写入链路保持原口径。
    """
    process_field_num = int(process_field_num)
    with open(batch_file, encoding='utf8') as f, open(output_batch_file, 'w', encoding='utf8') as of:
        for line in f:
            line = line.rstrip('\n')
            if not line:
                continue
            fields = line.split('\t')
            if len(fields) <= process_field_num:
                logging.warning('skip invalid batch line: %s', line)
                continue
            qa_file = fields[process_field_num]
            root, ext = os.path.splitext(qa_file)
            if ext:
                output_file = root + output_suffix
            else:
                output_file = qa_file + output_suffix
            write_quality_bucket_file(qa_file, output_file)
            of.write(line + '\t' + output_file + '\n')


def format_conversation_scope(message_info):
    group_name = str(message_info.get('group_name') or '').strip()
    if group_name:
        return f"群聊：{group_name}"
    peer_name = str(message_info.get('peer_name') or '').strip()
    if peer_name:
        return f"单聊：{peer_name}"
    return "单聊：unknown"


def get_message_identity_info(message_info, white_name_list=None, answer_source_names=None,
                              platform=None, identity_lookup=None):
    contact_identity = lookup_contact_identity(message_info, identity_lookup)
    return infer_speaker_identity(
        message_info.get('send_user', ''),
        white_name_list=white_name_list,
        answer_source_names=answer_source_names,
        platform=platform,
        contact_identity=contact_identity
    )


def get_readable_role_label(identity):
    if identity == LEADER_SOURCE_ROLE:
        return '本人'
    if identity == COLLEAGUE_SOURCE_ROLE:
        return '同事'
    if identity == QUESTION_SOURCE_ROLE:
        return '客户'
    return '未识别'


def get_readable_message_purpose(identity, marker=None):
    if marker:
        return '当前待评估答案'
    if identity in ANSWER_SOURCE_ROLES:
        return '答案来源'
    if identity == QUESTION_SOURCE_ROLE:
        return '问题来源'
    return '上下文参考'


def format_readable_speaker_label(speaker, identity):
    role_label = get_readable_role_label(identity)
    speaker = str(speaker or '').strip()
    if not speaker or normalize_qa_text(speaker) in {'unknown', 'unknow', 'none', 'null'}:
        return '未识别说话人' if role_label == '未识别' else role_label

    speaker_norm = _normalize_name(speaker)
    role_norm = _normalize_name(role_label)
    if speaker_norm == role_norm:
        return role_label
    if role_norm and (speaker_norm.startswith(role_norm) or role_norm in speaker_norm):
        return speaker
    return f"{role_label}{speaker}"


def format_chat_message_for_model(message_info, index=None, white_name_list=None, answer_source_names=None,
                                  platform=None, identity_lookup=None, marker=None):
    identity, identity_reason = get_message_identity_info(
        message_info,
        white_name_list=white_name_list,
        answer_source_names=answer_source_names,
        platform=platform,
        identity_lookup=identity_lookup
    )
    speaker = str(message_info.get('send_user', '') or '').strip()
    content = sanitize_chat_content(message_info.get('content', ''))
    content = re.sub(r'\s*\n\s*', ' / ', content)
    readable_label = format_readable_speaker_label(speaker, identity)
    purpose = get_readable_message_purpose(identity, marker=marker)
    return (
        f"{format_message_time(message_info.get('message_time', ''))}"
        f"｜{readable_label}/{purpose}：{content}"
    )


def merge_message_supplements(messages):
    images = []
    notes = []
    for message_info in messages or []:
        supplement = message_info.get('supplement')
        if not isinstance(supplement, dict):
            continue
        for image in supplement.get('images') or []:
            append_unique_image_info(images, image)
        note = supplement.get('note')
        if note and note not in notes:
            notes.append(note)
    merged = {}
    if images:
        merged['images'] = images
    if notes:
        merged['notes'] = notes
    return merged


def get_image_info_identity(image):
    if not isinstance(image, dict):
        return None
    label = str(image.get('label') or '').strip()
    address = str(image.get('address') or '').strip()
    if label or address:
        return label, address
    return json.dumps(image, ensure_ascii=False, sort_keys=True)


def append_unique_image_info(images, image):
    if not isinstance(image, dict):
        return
    image = normalize_backend_image_info(image)
    identity = get_image_info_identity(image)
    for exists in images:
        if get_image_info_identity(exists) == identity:
            for key, value in image.items():
                if key not in exists or not exists.get(key):
                    exists[key] = value
            return
    images.append(dict(image))


def merge_supplement_dicts(*supplements):
    images = []
    notes = []
    for supplement in supplements:
        if not isinstance(supplement, dict):
            continue
        for image in supplement.get('images') or []:
            append_unique_image_info(images, image)
        for note in supplement.get('notes') or []:
            if note and note not in notes:
                notes.append(note)
        note = supplement.get('note')
        if note and note not in notes:
            notes.append(note)
    merged = {}
    if images:
        merged['images'] = images
    if notes:
        merged['notes'] = notes
    return merged


def format_prompt_supplement(supplement):
    if not supplement:
        return ''
    return json.dumps(supplement, ensure_ascii=False, sort_keys=True)


def build_group_prompt_header(group_name, platform=None, answer_source_names=None, mode='full_timeline'):
    answer_source_text = '、'.join(sorted(answer_source_names)) if answer_source_names else '未配置明确名单，请严格按system prompt中的同事规则判断'
    display_platform = get_display_platform_name(platform) or platform or 'unknown'
    if mode == 'answer_window':
        return (
            "【metadata】\n"
            f"conversation_name: {group_name}\n"
            f"customer_or_platform: {display_platform}\n"
            f"raw_client: {platform or 'unknown'}\n"
            f"answer_source_names: {answer_source_text}\n\n"
        )
    return (
        "【metadata，仅用于追溯，不要写入 q/a】\n"
        f"conversation_name: {group_name}\n"
        f"customer_or_platform: {display_platform}\n"
        f"raw_client: {platform or 'unknown'}\n"
        f"answer_source_names: {answer_source_text}\n\n"
        "下面是按时间顺序整理后的聊天记录。每一行格式为：时间｜角色姓名/用途：原文内容。\n"
        "请把连续多行当作同一段对话来理解，重点识别客户提问、leader/同事回答、追问和补充说明之间的对应关系。\n"
        "用途=答案来源 或 当前待评估答案 的消息可以提供答案；用途=问题来源 的消息只能提供问题，不能作为答案。\n"
        "用途=上下文参考 的消息只能帮助理解对话脉络，不能作为答案。\n"
        "请结合时间顺序理解追问、引用和上下文，不要把后面无关消息拼到前面问题里；q/a 必须通用化、脱敏化，不能包含 metadata 或个体标识。\n\n"
        "聊天记录:\n"
    )


def is_answer_source_message(message_info, white_name_list=None, answer_source_names=None,
                             platform=None, identity_lookup=None):
    identity, _ = get_message_identity_info(
        message_info,
        white_name_list=white_name_list,
        answer_source_names=answer_source_names,
        platform=platform,
        identity_lookup=identity_lookup
    )
    content = sanitize_chat_content(message_info.get('content', ''))
    if identity not in ANSWER_SOURCE_ROLES:
        return False
    if is_noise_chat_content(content):
        return False
    if is_weak_answer(content):
        return False
    if not is_candidate_answer_like_content(content):
        return False
    return True


def get_qa_is_qualified(qa_info):
    return normalize_bool(qa_info.get('is_qualified'), default=False)


def get_unreusable_model_item_drop_reason(qa_info):
    """
    模型有时会承认“上下文不足”但仍输出 low/client_specific item。
    这类不是低价值样本，而是应该为空的误抽，直接预过滤掉。
    """
    if not get_qa_is_qualified(qa_info):
        return 'is_qualified=false'

    reason_text = ' '.join([
        str(qa_info.get('quality_reason') or ''),
        str(qa_info.get('reason') or ''),
        str(qa_info.get('q') or ''),
    ])
    q_text = str(qa_info.get('q') or '')
    a_text = ' '.join([
        str(qa_info.get('a') or ''),
        str(qa_info.get('source_quote') or ''),
    ])
    explicit_deictic_reason = re.search(r'指代|依赖上下文|结合上下文', reason_text, flags=re.I)
    unresolved_fill_object = re.search(
        r'\bfill\s+in\s+(?:it|this|that)\b|\bprint(?:ed)?\s+(?:it|this|that)\s+out\b',
        a_text,
        flags=re.I
    )
    q_names_form_object = re.search(r'表格|表单|模板|form|template', q_text, flags=re.I)
    if explicit_deictic_reason and unresolved_fill_object and not q_names_form_object:
        return 'it/this指代对象未在q中解析'

    reason_norm = normalize_qa_text(reason_text)
    reject_keywords = [
        '上下文不足',
        '缺少上下文',
        '背景不足',
        '背景不够',
        '指代不清',
        '无法确定具体平台',
        '无法确定平台',
        '无法确定具体场景',
        '无法判断业务场景',
        '无法确定具体平台和场景',
        '需要更多上下文',
        '具体账号',
        '具体店铺',
        '具体订单',
        '状态查询',
        '催办',
        '个案',
        '答案过于简短',
        '答案太简短',
        '过于简短',
        '缺乏具体',
        '缺少具体',
        '未提供具体',
        '无法独立作为可复用知识',
        '无法独立复用',
        '复用价值低',
        '仅为一个操作步骤',
        '没有具体步骤',
        '无具体步骤',
        '缺乏具体步骤',
    ]
    for keyword in reject_keywords:
        if normalize_qa_text(keyword) in reason_norm:
            return keyword
    return ''


def get_scope_mismatch_drop_reason(qa_info):
    q = str(qa_info.get('q') or '')
    answer_text = ' '.join([
        str(qa_info.get('a') or ''),
        str(qa_info.get('source_quote') or ''),
    ])
    q_has_transfer = re.search(
        r'\btransfer\b|\bremit\b|send money|汇款|转账|转款',
        q,
        flags=re.I
    )
    answer_only_register = (
        re.search(r'\bregister\b|注册|开户注册', answer_text, flags=re.I)
        and not re.search(r'\btransfer\b|\bremit\b|send money|汇款|转账|转款|USD|GBP|EUR|币种|currency', answer_text, flags=re.I)
    )
    if q_has_transfer and answer_only_register:
        return 'q提到汇款/转账但答案只支持注册'
    return ''


def get_temporary_bug_drop_reason(qa_info):
    text = ' '.join([
        str(qa_info.get('q') or ''),
        str(qa_info.get('a') or ''),
        str(qa_info.get('source_quote') or ''),
        str(qa_info.get('quality_reason') or ''),
    ])
    if re.search(
        r'bug期间|目前.{0,8}bug|近期.{0,8}bug|系统.{0,12}升级.{0,20}bug|KYC系统.{0,12}升级.{0,20}bug|系统\s*bug.{0,20}(?:改天|再尝试|VPN|修复)|系统.{0,20}bug.{0,20}(?:改天|再尝试|VPN|修复)|技术问题.{0,20}(?:修复|恢复)|我们已在修复|下个星期再尝试|下周再尝试|改天再尝试|正在修复|紧急修复|修复中|近期恢复正常|临时处理建议|换浏览器.{0,20}VPN.{0,30}(?:隔天|明天|今天|再试|多尝试)|如果今天无法连接.{0,20}隔天',
        text,
        flags=re.I
    ):
        return '临时bug状态/等待重试'
    return ''


def get_promo_bonus_drop_reason(qa_info):
    text = ' '.join([
        str(qa_info.get('q') or ''),
        str(qa_info.get('a') or ''),
        str(qa_info.get('source_quote') or ''),
    ])
    if re.search(r'trial bonus|¥\\s*100\\s*trial|bonus to verify', text, flags=re.I):
        return '推广/bonus测试话术'
    return ''


def get_case_coordination_drop_reason(qa_info):
    text = ' '.join([
        str(qa_info.get('q') or ''),
        str(qa_info.get('a') or ''),
        str(qa_info.get('source_quote') or ''),
        str(qa_info.get('quality_reason') or ''),
    ])
    if re.search(
        r'开个case.{0,8}申诉|订单号发给后台客服|把订单号发给后台客服|发给后台客服咨询|账单\s*id.{0,12}后台客服|费用.{0,20}账单\s*id.{0,20}后台客服|后台客服.{0,12}判断是什么支出|光看这个我看不出来|目前暂时',
        text,
        flags=re.I
    ):
        return '个案协作/临时处理'
    return ''


def get_low_information_answer_drop_reason(qa_info):
    """
    保留正常 mid；只丢弃答案本身几乎没有业务口径的误抽。
    """
    answer = str(qa_info.get('a') or '').strip()
    source_quote = str(qa_info.get('source_quote') or '').strip()
    answer_norm = normalize_qa_text(answer)
    source_norm = normalize_qa_text(source_quote)
    if not answer_norm:
        return '答案为空'

    if re.search(r'https?://|file\.marsmind\.cc|tmp/\d+|图片答案|图片\d+', answer, flags=re.I):
        return ''

    if re.fullmatch(
        r'(?:请)?(?:仔细)?(?:阅读|查看|参考|看)(?:一下)?(?:第?[0-9一二三四五六七八九十]+[\.、]?)?(?:条|项|点|适用范围|公告|文档|链接|附件|图片)?[。.!！]?',
        answer.strip(),
        flags=re.I
    ):
        return '答案仅指向阅读材料'
    if re.search(r'请.{0,4}(?:仔细)?(?:阅读|查看|参考).{0,12}(?:适用范围|公告|文档|链接|附件|第?[0-9一二三四五六七八九十]+[\.、]?(?:条|项|点))', answer, flags=re.I):
        return '答案仅指向阅读材料'

    action_pattern = (
        r'需要|可以|可用|可绑定|支持|不支持|必须|建议|无需|不需要|不能|不可以|'
        r'绑定|注册|上传|填写|提供|选择|确认|联系|申请|开通|完成|进入|点击|'
        r'提交|发货|收款|提现|设置|修改|更换|换|影响|预扣|缴纳|审核|'
        r'\bcan\b|\bcannot\b|\bneed\b|\bneeds\b|\bmust\b|\bshould\b|'
        r'\bsupport\b|\bsupported\b|\bregister\b|\bbind\b|\bupload\b|\bsubmit\b|\buse\b'
    )
    if len(answer_norm) <= 8 and not re.search(action_pattern, answer, flags=re.I):
        if not source_norm or len(source_norm) <= 8:
            return '答案只有名词短语'
    return ''


def filter_unreusable_model_misextracts(qa_list):
    filtered = []
    for qa_info in qa_list:
        drop_reason = (
            get_scope_mismatch_drop_reason(qa_info)
            or get_temporary_bug_drop_reason(qa_info)
            or get_promo_bonus_drop_reason(qa_info)
            or get_case_coordination_drop_reason(qa_info)
            or get_low_information_answer_drop_reason(qa_info)
            or get_unreusable_model_item_drop_reason(qa_info)
        )
        if drop_reason:
            logging.info(
                '预过滤丢弃不可复用误抽: reason=%s q=%s a=%s',
                drop_reason,
                qa_info.get('q', ''),
                qa_info.get('a', '')
            )
            continue
        filtered.append(qa_info)
    return filtered


def extract_numbered_image_labels(text):
    labels = []
    for match in re.finditer(
        r'(?:图片|截图|image|img|photo|picture)\s*(\d+)',
        str(text or ''),
        flags=re.I
    ):
        label = f"图片{match.group(1)}"
        if label not in labels:
            labels.append(label)
    return labels


def get_supplement_image_labels(supplement):
    labels = []
    if not isinstance(supplement, dict):
        return labels
    for index, image_info in enumerate(supplement.get('images') or [], start=1):
        if not isinstance(image_info, dict):
            continue
        label = str(image_info.get('label', '') or '').strip()
        if not label:
            label = f"图片{index}"
        if label not in labels:
            labels.append(label)
    return labels


def get_image_reference_values(image_info):
    values = set()
    if not isinstance(image_info, dict):
        return values
    for key in [
        'label',
        'address',
        'backend_url',
        'backend_path',
        'backend_file_path',
        'public_url',
        'url',
        'path',
        'file_url',
        'image_url',
        'image_path',
    ]:
        value = str(image_info.get(key) or '').strip()
        if value:
            values.add(value)
    for value in image_info.get('addresses') or []:
        value = str(value or '').strip()
        if value:
            values.add(value)
    return values


def image_info_matches(candidate_image, qa_image):
    candidate_values = get_image_reference_values(candidate_image)
    qa_values = get_image_reference_values(qa_image)
    return bool(candidate_values and qa_values and candidate_values.intersection(qa_values))


def get_matching_candidate_images(candidate_supplement, qa_supplement):
    if not isinstance(candidate_supplement, dict) or not isinstance(qa_supplement, dict):
        return []
    matches = []
    candidate_images = candidate_supplement.get('images') or []
    qa_images = qa_supplement.get('images') or []
    for candidate_image in candidate_images:
        for qa_image in qa_images:
            if image_info_matches(candidate_image, qa_image):
                append_unique_image_info(matches, candidate_image)
                break
    return matches


def format_image_answer_from_images(images):
    answer_parts = []
    for image_info in images or []:
        if not isinstance(image_info, dict):
            continue
        for key in ['backend_url', 'public_url', 'url', 'backend_file_path', 'backend_path', 'address']:
            value = str(image_info.get(key) or '').strip()
            if value and value not in answer_parts:
                answer_parts.append(value)
                break
    return '\n'.join(answer_parts).strip()


def get_supplement_image_mapping_error(supplement):
    if not isinstance(supplement, dict):
        return ''
    missing_labels = []
    for index, image_info in enumerate(supplement.get('images') or [], start=1):
        if not isinstance(image_info, dict):
            missing_labels.append(f"图片{index}")
            continue
        has_reference = any(
            str(image_info.get(key) or '').strip()
            for key in ['backend_url', 'public_url', 'url', 'backend_file_path', 'backend_path', 'address']
        )
        if not has_reference:
            missing_labels.append(str(image_info.get('label') or f"图片{index}"))
    if missing_labels:
        return 'image_mapping_missing_reference: ' + ','.join(missing_labels)
    return ''


def restore_answer_from_source_quote_if_needed(qa_info, candidate_answer, min_overlap=0.45):
    answer = str(qa_info.get('a', '') or '').strip()
    if not answer or looks_like_image_reference_answer(answer):
        return qa_info
    if text_overlap_ratio(answer, candidate_answer) >= min_overlap:
        return qa_info

    source_quote = str(qa_info.get('source_quote') or '').strip()
    if not source_quote or is_weak_generated_answer(source_quote):
        return qa_info
    if text_overlap_ratio(source_quote, candidate_answer) < min_overlap:
        return qa_info

    qa_info = dict(qa_info)
    qa_info['a'] = (
        source_quote
        if looks_like_image_reference_answer(source_quote)
        else generalize_reusable_qa_text(source_quote)
    )
    return qa_info


def is_image_only_candidate_turn(candidate_answer, candidate_supplement):
    if not candidate_supplement.get('images') and not is_image_only_placeholder_content(candidate_answer):
        return False
    content_without_images = re.sub(
        r'[\[【(（]?\s*(?:图片|image|img|photo|picture)\s*\d*\s*[\]】)）]?',
        '',
        sanitize_chat_content(candidate_answer),
        flags=re.I
    )
    return not content_without_images.strip()


def filter_qa_by_candidate_answer(qa_list, answer_turn):
    """
    防止模型从上方50句上下文偷抽其他答案：答案和来源都必须能回到候选答案。
    """
    candidate_messages = answer_turn.get('target_messages', [])
    candidate_answer = '\n'.join(str(message.get('content', '') or '') for message in candidate_messages)
    candidate_speakers = [str(message.get('send_user', '') or '').strip() for message in candidate_messages]
    candidate_supplement = merge_message_supplements(candidate_messages)
    candidate_has_image = bool(candidate_supplement.get('images')) or is_image_only_placeholder_content(candidate_answer)
    candidate_image_only = is_image_only_candidate_turn(candidate_answer, candidate_supplement)
    filtered = []
    for qa_info in qa_list:
        answer = str(qa_info.get('a', '') or '').strip()
        if is_null_answer(answer) or is_weak_generated_answer(answer):
            continue
        source = str(qa_info.get('source', '') or '').strip().strip('[]')
        if source and candidate_speakers and not any(
            _is_name_match(source, [speaker]) or _is_name_match(speaker, [source])
            for speaker in candidate_speakers
        ):
            continue
        if candidate_has_image:
            if candidate_image_only:
                source_quote = str(qa_info.get('source_quote') or '').strip()
                if not (
                    is_generic_image_answer_text(answer)
                    or is_generic_image_answer_text(source_quote)
                ):
                    continue
                qa_info = dict(qa_info)
                if candidate_supplement.get('images'):
                    qa_info['supplement'] = merge_supplement_dicts(qa_info.get('supplement'), candidate_supplement)
                    qa_info['a'] = (
                        format_image_answer_from_images(candidate_supplement.get('images'))
                        or format_supplement_image_placeholders(candidate_supplement)
                        or '图片答案'
                    )
                    mapping_error = get_supplement_image_mapping_error(candidate_supplement)
                    if mapping_error:
                        qa_info['supplement_mapping_error'] = mapping_error
                else:
                    qa_info['a'] = candidate_answer or answer or '图片答案'
                    qa_info['supplement_mapping_error'] = 'image_mapping_missing_metadata'
            else:
                qa_info = restore_answer_from_source_quote_if_needed(qa_info, candidate_answer, min_overlap=0.35)
                answer = str(qa_info.get('a', '') or '').strip()
                if not looks_like_image_reference_answer(answer) and text_overlap_ratio(answer, candidate_answer) < 0.35:
                    continue
            filtered.append(qa_info)
            continue
        qa_info = restore_answer_from_source_quote_if_needed(qa_info, candidate_answer)
        answer = str(qa_info.get('a', '') or '').strip()
        if text_overlap_ratio(answer, candidate_answer) < 0.45:
            continue
        filtered.append(qa_info)
    return filtered


def extract_leading_mention_key(content):
    content = sanitize_chat_content(content)
    match = re.match(r'^\s*@+([^\s\u2005:：，,。；;]+)', content)
    if not match:
        return ''
    return _normalize_name(match.group(1))


def should_merge_answer_source_message(current_turn, message_info, max_gap_seconds=180):
    if not current_turn:
        return False
    previous_message = current_turn['target_messages'][-1]
    previous_speaker = previous_message.get('send_user_id') or previous_message.get('send_user')
    current_speaker = message_info.get('send_user_id') or message_info.get('send_user')
    if previous_speaker != current_speaker:
        return False
    previous_ts = parse_message_time_ts(previous_message.get('message_time'))
    current_ts = parse_message_time_ts(message_info.get('message_time'))
    if previous_ts is None or current_ts is None:
        return False
    previous_mention = extract_leading_mention_key(previous_message.get('content', ''))
    current_mention = extract_leading_mention_key(message_info.get('content', ''))
    if previous_mention and current_mention and previous_mention != current_mention:
        return False
    return 0 <= current_ts - previous_ts <= max_gap_seconds


def build_answer_source_turns(group_chat_list, white_name_list=None, answer_source_names=None,
                              platform=None, identity_lookup=None):
    """
    以 leader/同事消息作为候选答案目标；连续同一人的候选答案合并为一个 answer turn。
    """
    turns = []
    current_turn = None
    group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
    for index, message_info in enumerate(group_chat_list):
        if is_answer_source_message(
            message_info,
            white_name_list=white_name_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup
        ):
            if should_merge_answer_source_message(current_turn, message_info):
                current_turn['target_messages'].append(message_info)
                current_turn['end_index'] = index
            else:
                if current_turn:
                    turns.append(current_turn)
                current_turn = {
                    'start_index': index,
                    'end_index': index,
                    'target_messages': [message_info],
                }
            continue

        if current_turn:
            turns.append(current_turn)
            current_turn = None
    if current_turn:
        turns.append(current_turn)
    return turns


def build_answer_window_prompt(group_name, group_chat_list, answer_turn, white_name_list=None,
                               answer_source_names=None, platform=None, identity_lookup=None,
                               context_message_limit=50):
    group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
    start_index = answer_turn['start_index']
    context_messages = group_chat_list[max(0, start_index - context_message_limit):start_index]
    context_lines = [
        format_chat_message_for_model(
            message_info,
            white_name_list=white_name_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup
        )
        for message_info in context_messages
    ]
    target_lines = [
        format_chat_message_for_model(
            message_info,
            white_name_list=white_name_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup,
            marker='current_answer'
        )
        for message_info in answer_turn['target_messages']
    ]
    context_text = '\n'.join(context_lines) if context_lines else '无'
    target_text = '\n'.join(target_lines)
    prompt_text = (
        build_group_prompt_header(group_name, platform, answer_source_names, mode='answer_window')
        + "【上方50句上下文】\n"
        + context_text
        + "\n\n【当前待评估答案】\n"
        + target_text
    )
    return prompt_text


def request_llm_for_answer_windows(group_name, platform, group_chat_list, group_white_list, llm_model,
                                   answer_source_names=None, identity_lookup=None):
    result_qa_list = []
    answer_turns = build_answer_source_turns(
        group_chat_list,
        white_name_list=group_white_list,
        answer_source_names=answer_source_names,
        platform=platform,
        identity_lookup=identity_lookup
    )
    logging.info('group_name:%s answer_source_turns:%s', group_name, len(answer_turns))
    for answer_turn in answer_turns:
        prompt_str = build_answer_window_prompt(
            group_name,
            group_chat_list,
            answer_turn,
            white_name_list=group_white_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup
        )
        logging.info(f'answer_window_prompt:\n{prompt_str}\n')
        target_message = answer_turn['target_messages'][0]
        sorted_group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
        window_supplement = merge_message_supplements(
            sorted_group_chat_list[max(0, answer_turn['start_index'] - 50):answer_turn['start_index']]
            + answer_turn['target_messages']
        )
        target_supplement = merge_message_supplements(answer_turn['target_messages'])
        extra_info_dict = {
            'from_file_name': group_name,
            'from_user': target_message.get('send_user', ''),
            'group_name': group_name,
            'candidate_answer_time': target_message.get('message_time', ''),
            'from_chat_history': prompt_str,
        }
        source_identity, source_identity_reason = get_message_identity_info(
            target_message,
            white_name_list=group_white_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup,
        )
        source_message_ids = [
            str(message.get('msg_id')).strip()
            for message in answer_turn['target_messages']
            if message.get('msg_id') not in (None, '')
        ]
        extra_info_dict.update({
            'source_user_id': target_message.get('send_user_id', ''),
            'source_message_ids': source_message_ids,
            'source_identity': source_identity,
            'source_identity_reason': source_identity_reason,
        })
        result = llm_model.request_json(prompt_str)
        qa_list = normalize_llm_qa_items(
            result,
            extra_info_dict=extra_info_dict,
            default_platform=platform,
            candidate_source=target_message.get('send_user', '')
        )
        qa_list = filter_unreusable_model_misextracts(qa_list)
        qa_list = filter_qa_by_candidate_answer(qa_list, answer_turn)
        qa_list = clean_and_dedupe_qa_list(qa_list)
        for qa_info in qa_list:
            if target_supplement:
                qa_info['supplement'] = merge_supplement_dicts(qa_info.get('supplement'), target_supplement)
                mapping_error = get_supplement_image_mapping_error(target_supplement)
                if mapping_error and not qa_info.get('supplement_mapping_error'):
                    qa_info['supplement_mapping_error'] = mapping_error
            qa_info['from_chat_history'] = prompt_str
        logging.info(f'direct_llm_answer_window_result:\n{result}\nqa_list:\n{qa_list}\n')
        result_qa_list.extend(qa_list)
    return clean_and_dedupe_qa_list(result_qa_list)


def load_robot_room_type(line_config_file, filter_group_name='all'):
    """
    config_file:#机器人\t群名\t平台\t类型(转发/普通群)
    """
    config = dict()
    with open(line_config_file, encoding='utf8') as f:
        for line in f:
            line = line.strip('\n')
            if not line:
                continue
            fields = line.split('\t')
            robot = fields[0]
            group = fields[1]
            platform = fields[2]
            room_type = fields[3]
            if filter_group_name != 'all' and group != filter_group_name:
                continue
            if robot not in config:
                config[robot] = {}
            black_group = set()
            if group == 'all':
                if len(fields) > 4:
                    black_group = set(item for item in fields[4].split('|') if item)
            config[robot][group] = {
                'platform': platform,
                'type': room_type,
                'black_group': black_group
            }
    return config

def save_3file_dict(save_file, data_dict):
    """
    保存3级字典
    """
    with open(save_file, 'w', encoding='utf8') as f:
        for robot, group_dict in data_dict.items():
            for group, value in group_dict.items():
                f.write(f"{robot}\t{group}\t{value}\n")

def load_white_list_dict(white_list_file):
    """
    加载白名单字典
    """
    white_list_dict = load_3file_dict(white_list_file)
    for robot, group_dict in white_list_dict.items():
        for group, white_list in group_dict.items():
            group_dict[group] = white_list.split(',')
    return white_list_dict


def get_message_speaker(message_info, fallback_send_name, robot_name=None):
    original_info = message_info.get('original_info', {}) or {}
    if message_info.get('type') == 'reply':
        return robot_name or fallback_send_name, '', '', '', '', ''

    actual_user_id = original_info.get('actual_user_id', '')
    actual_user_nickname = original_info.get('actual_user_nickname', '')
    from_user_id = original_info.get('from_user_id', '')
    from_user_nickname = original_info.get('from_user_nickname', '')
    send_user_id = actual_user_id or from_user_id
    send_user = (
        actual_user_nickname
        or from_user_nickname
        or message_info.get('send_name')
        or fallback_send_name
        or send_user_id
    )
    return send_user, send_user_id, actual_user_id, actual_user_nickname, from_user_id, from_user_nickname


def load_and_reorg_one_robot_data(robot_name, data_file, room_type_config, 
                                  robot_room_process_record,  need_robot_reply=False):
    """
    加载并重组单个机器人的数据
    """
    has_process_content = dict()
    reorga_chat_dict = dict() # 重组后的对话数据，key为群名，value为对话数据list
    image_count_by_group = dict()
    with open(data_file, encoding='utf8') as f:
        for line in f:
            try:
                line = line.strip('\n')
                if not line:
                    continue
                send_name, message_time, message_info_str = line.split('\t')
                message_info = json.loads(message_info_str)

                if not message_info.get('original_info', {}).get('is_group', False):  # 不处理单聊信息
                    continue
                group_name = message_info.get('original_info', {}).get('other_user_nickname', '')
                group_name = group_name if group_name else message_info.get('original_info', {}).get('other_user_id', '')
                #if group_name not in room_type_config:
                #    continue
                # 如果该数据已经处理过，则跳过
                processed_time = robot_room_process_record.get(robot_name, {}).get(group_name, '0000-00-00 00:00:00')
                if message_time <= processed_time:
                    continue
                if 'conent' in message_info: # 原始数据文件打错了,需要修正
                    message_info['content'] = message_info['conent']
                if message_info.get('type') == 'all':
                    ctype = message_info['original_info']['ctype']
                    send_content = message_info.get('content', '')
                    speaker_info = get_message_speaker(message_info, send_name, robot_name=robot_name)
                elif message_info.get('type') == 'reply': # 该数据是机器人回复数据
                    if not need_robot_reply:
                        continue
                    send_content = message_info['reply']['conent']
                    ctype = message_info['reply']['type']
                    speaker_info = get_message_speaker(message_info, send_name, robot_name=robot_name)
                else:
                    continue
                supplement = {}
                if is_text_message_type(ctype):
                    send_content = sanitize_chat_content(send_content)
                    if is_image_placeholder_or_address(send_content):
                        image_count_by_group[group_name] = image_count_by_group.get(group_name, 0) + 1
                        image_label = f"图片{image_count_by_group[group_name]}"
                        send_content, supplement = build_image_message_content_and_supplement(
                            message_info,
                            send_content,
                            'IMAGE_FROM_TEXT',
                            image_label
                        )
                        ctype = 'IMAGE_FROM_TEXT'
                    elif is_noise_chat_content(send_content):
                        continue
                elif is_image_mixed_message_type(ctype):
                    next_image_index = image_count_by_group.get(group_name, 0) + 1
                    send_content, supplement, used_image_count = build_mixed_image_text_content_and_supplement(
                        message_info,
                        send_content,
                        ctype,
                        next_image_index
                    )
                    if used_image_count:
                        image_count_by_group[group_name] = image_count_by_group.get(group_name, 0) + used_image_count
                    send_content = sanitize_chat_content(send_content)
                    if supplement and is_noise_chat_content(send_content):
                        if should_keep_image_payload_when_text_is_noise(send_content):
                            send_content = format_supplement_image_placeholders(supplement)
                        else:
                            continue
                    if not send_content or (not supplement and is_noise_chat_content(send_content)):
                        continue
                elif is_image_message_type(ctype):
                    image_count_by_group[group_name] = image_count_by_group.get(group_name, 0) + 1
                    image_label = f"图片{image_count_by_group[group_name]}"
                    send_content, supplement = build_image_message_content_and_supplement(
                        message_info,
                        send_content,
                        ctype,
                        image_label
                    )
                else:
                    continue
                send_user, send_user_id, actual_user_id, actual_user_nickname, from_user_id, from_user_nickname = speaker_info
                dedupe_key = (group_name, send_user_id or send_user, send_content)
                current_ts = parse_message_time_ts(message_time)
                last_ts = has_process_content.get(dedupe_key)
                if last_ts is not None and current_ts is not None and abs(current_ts - last_ts) <= 120:
                    continue
                if last_ts is not None and current_ts is None:
                    continue
                has_process_content[dedupe_key] = current_ts
                new_message_info = {
                    'msg_id': message_info.get('original_info', {}).get('msg_id', ''),
                    'send_user': send_user,
                    'send_user_id': send_user_id,
                    'actual_user_id': actual_user_id,
                    'actual_user_nickname': actual_user_nickname,
                    'from_user_id': from_user_id,
                    'from_user_nickname': from_user_nickname,
                    'group_id': message_info.get('original_info', {}).get('other_user_id', ''),
                    'group_name': group_name,
                    'content': send_content,
                    'ctype': ctype,
                    'message_time': message_time,
                }
                if supplement:
                    new_message_info['supplement'] = supplement
                reorga_chat_dict.setdefault(group_name, []).append(new_message_info)
            except:            
                tb = traceback.format_exc()
                logging.error(f'error_tb:{tb}')
                logging.error(f'error_line:{line}')
                #exit(1)
                continue
    return reorga_chat_dict


def get_forword_group_bigmodel_prompt(group_name, group_chat_list, sep='\n',
                                      white_name_list=None, answer_source_names=None, platform=None,
                                      identity_lookup=None):
    """
    获取转发群的大模型prompt
    """
    prompt_list = []
    group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
    for index, message_info in enumerate(group_chat_list, 1):
        prompt_list.append(format_chat_message_for_model(
            message_info, index,
            white_name_list=white_name_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup
        ))
    
    prompt_str = sep.join(prompt_list)
    if group_name:
        prompt_str = build_group_prompt_header(group_name, platform, answer_source_names) + prompt_str
    return prompt_str

def get_normal_group_bigmodel_prompt(group_name, group_chat_list, white_name_list, sep='\n',
                                     answer_source_names=None, platform=None, identity_lookup=None):
    """
    获取普通群的大模型prompt
    """
    prompt_list = []
    group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
    for index, message_info in enumerate(group_chat_list, 1):
        prompt_list.append(format_chat_message_for_model(
            message_info, index,
            white_name_list=white_name_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup
        ))
    prompt_str = sep.join(prompt_list)
    if group_name:
        prompt_str = build_group_prompt_header(group_name, platform, answer_source_names) + prompt_str
    return prompt_str

def process_forward_group_data(group_name, platform, group_chat_list, 
                               group_white_list, llm_model, answer_source_names=None,
                               identity_lookup=None):
    """
    处理转发群的数据
    """
    return request_llm_for_answer_windows(
        group_name,
        platform,
        group_chat_list,
        group_white_list,
        llm_model,
        answer_source_names=answer_source_names,
        identity_lookup=identity_lookup
    )

def process_normal_group_data(group_name, platform, group_chat_list, group_white_list, llm_model,
                              answer_source_names=None, identity_lookup=None):
    """
    处理普通群的数据
    """
    return request_llm_for_answer_windows(
        group_name,
        platform,
        group_chat_list,
        group_white_list,
        llm_model,
        answer_source_names=answer_source_names,
        identity_lookup=identity_lookup
    )


def process_one_group_data(group_name, group_chat_list, group_type, 
                           group_white_list, platform, forward_llm_model, norm_llm_model,
                           answer_source_names=None, identity_lookup=None):
    """
    处理单个群的数据
    """
    if group_type == 'forward':
        return process_forward_group_data(
            group_name, platform, group_chat_list, group_white_list,
            forward_llm_model,
            answer_source_names=answer_source_names,
            identity_lookup=identity_lookup
        )
    elif group_type == 'normal':
        return process_normal_group_data(
            group_name, platform, group_chat_list, group_white_list,
            norm_llm_model,
            answer_source_names=answer_source_names,
            identity_lookup=identity_lookup
        )

    else:
        raise ValueError(f"群类型错误: {group_type}")

def process_one_robot_group_data(robot_name, data_file,
                                robot_room_type_config, robot_white_list_dict, robot_room_process_record=None, 
                                need_robot_reply=False, need_add_chat_history=True, prompt_file=None,
                                client=None,
                                identity_lookup=None, mysql_config_file='config/mysql_conn_config.json',
                                run_stats=None):
    """
    处理单个机器人的数据
    """
    logging.info(f'process robot_name:{robot_name} data_file:{data_file}')
    if isinstance(robot_room_type_config, str):
        robot_room_type_config = load_robot_room_type(robot_room_type_config)
    if robot_room_process_record is None:
        robot_room_process_record = dict()
    if isinstance(robot_white_list_dict, str):
        robot_white_list_dict = load_white_list_dict(robot_white_list_dict)
    if identity_lookup is None:
        identity_lookup = load_contact_identity_lookup(mysql_config_file)

    reorga_chat_dict = load_and_reorg_one_robot_data(robot_name, data_file, robot_room_type_config.get(robot_name, {}), 
                                                     robot_room_process_record, need_robot_reply)
    logging.info(f'robot_name:{robot_name} reorga_chat_dict:\n{reorga_chat_dict}\n')
    if prompt_file:
        system_prompt = open(prompt_file, encoding='utf8').read()
    else:
        system_prompt = None
    answer_source_names = extract_answer_source_names(system_prompt)
    
    logging.info(f'robot_name:{robot_name} prompt_file:{prompt_file} system_prompt:\n{system_prompt}\n')
    direct_llm_model = DirectLLMJsonRequest(system_prompt=system_prompt, client=client)
    if hasattr(direct_llm_model, 'validate_config'):
        direct_llm_model.validate_config()
    forward_llm_model_nomix = direct_llm_model
    forward_llm_model_mix = direct_llm_model
    norm_llm_model_nomix = direct_llm_model
    norm_llm_model_mix = direct_llm_model
    all_qa_list = []
    eligible_group_count = 0
    successful_group_count = 0
    group_failures = []
    group_type_config = robot_room_type_config.get(robot_name, {})
    logging.info(f'group_type_config:\n{group_type_config}\n')
    logging.info(f'reorga_chat_dict:\n{len(reorga_chat_dict)}\n')
    for group_name, group_chat_list in reorga_chat_dict.items():
        if group_name in group_type_config:
            group_type = group_type_config[group_name].get('type', 'unknown')
            platform = group_type_config[group_name].get('platform', 'unknown')
        elif 'all' in group_type_config:
            # 命中黑名单
            logging.info('group_name[%s], black_name_set[%s], is_hit[%s]', group_name, group_type_config['all'].get('black_group', set()), group_name in group_type_config['all'].get('black_group', set()))
            if group_name in group_type_config['all'].get('black_group', set()):
                continue
            group_type = group_type_config['all'].get('type', 'unknown')
            platform = group_type_config['all'].get('platform', 'unknown')
        else:
            logging.info(f'group_name[{group_name}] not in group_type_config and not has all')
            continue
        eligible_group_count += 1
        logging.info(f'group_name:{group_name} group_type:{group_type} platform:{platform}')
        white_list = robot_white_list_dict.get(robot_name, {}).get(group_name, [])
        if platform == 'mix':
            norm_llm_model = norm_llm_model_mix
            forward_llm_model = forward_llm_model_mix
        else:
            norm_llm_model = norm_llm_model_nomix
            forward_llm_model = forward_llm_model_nomix
        try:
            qa_list = process_one_group_data(
                group_name,
                group_chat_list,
                group_type,
                white_list,
                platform,
                forward_llm_model,
                norm_llm_model,
                answer_source_names=answer_source_names,
                identity_lookup=identity_lookup
            )
        except Exception as e:
            # 继续处理同一机器人其它群以保留完整失败证据；批次入口会在所有群处理完后
            # 将任何群失败升级为任务失败，因此 App/全局水位都不会推进。
            group_failures.append({
                'group_name': group_name,
                'error_type': type(e).__name__,
                'error': str(e)[:500],
            })
            logging.error(
                'group[%s] process failed, skip without advancing watermark. err: %s',
                group_name,
                e,
                exc_info=True
            )
            continue
        successful_group_count += 1
        if need_add_chat_history:
            history_prompt = get_normal_group_bigmodel_prompt(
                group_name, group_chat_list, white_list, sep='\n',
                answer_source_names=answer_source_names,
                platform=platform,
                identity_lookup=identity_lookup
            ) # 增加聊天历史对话，为了让人知道qa从哪里出来。方便审核
            for qa_info in qa_list:
                qa_info.setdefault('from_chat_history', history_prompt)

        if 'all' in group_type_config:
            qa_list = list(filter(lambda x: x.get('source', 'unknow') not in group_type_config['all'].get('black_group', set()), qa_list)) # 过滤部分答案来源为非专业人士的数据
        all_qa_list.extend(qa_list)
        max_process_time = list(sorted(group_chat_list, key=lambda x: x['message_time']))[-1]['message_time']
        robot_room_process_record.setdefault(robot_name, {})
        robot_room_process_record[robot_name][group_name] = max_process_time
    if run_stats is not None:
        run_stats.update({
            'robot_name': robot_name,
            'groups_seen': len(reorga_chat_dict),
            'groups_eligible': eligible_group_count,
            'groups_succeeded': successful_group_count,
            'groups_failed': len(group_failures),
            'failed_groups': group_failures,
            'qa_count': len(all_qa_list),
            'llm': direct_llm_model.get_stats() if hasattr(direct_llm_model, 'get_stats') else {},
        })
    return all_qa_list


LLM_STAT_TOTAL_KEYS = (
    'logical_requests',
    'http_attempts',
    'successful_requests',
    'failed_requests',
    'timeout_attempts',
    'non_200_attempts',
    'response_format_fallbacks',
    'prompt_chars',
    'completion_chars',
    'prompt_tokens',
    'completion_tokens',
    'total_tokens',
    'elapsed_seconds',
)


def build_llm_run_summary(robot_stats_list, fatal_errors=None):
    totals = {
        'robots': len(robot_stats_list),
        'groups_seen': 0,
        'groups_eligible': 0,
        'groups_succeeded': 0,
        'groups_failed': 0,
        'qa_count': 0,
    }
    totals.update({key: 0 for key in LLM_STAT_TOTAL_KEYS})
    for robot_stats in robot_stats_list:
        for key in (
            'groups_seen', 'groups_eligible', 'groups_succeeded',
            'groups_failed', 'qa_count'
        ):
            totals[key] += robot_stats.get(key, 0) or 0
        llm_stats = robot_stats.get('llm') or {}
        for key in LLM_STAT_TOTAL_KEYS:
            totals[key] += llm_stats.get(key, 0) or 0
    totals['elapsed_seconds'] = round(totals['elapsed_seconds'], 3)
    return {
        'schema_version': 1,
        'totals': totals,
        'robots': robot_stats_list,
        'fatal_errors': fatal_errors or [],
    }


def write_llm_run_summary(llm_stats_file, summary):
    if not llm_stats_file:
        return
    stats_dir = os.path.dirname(llm_stats_file)
    if stats_dir:
        os.makedirs(stats_dir, exist_ok=True)
    temp_file = llm_stats_file + '.tmp'
    with open(temp_file, 'w', encoding='utf8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temp_file, llm_stats_file)




def run_batch_robot_chat_data(data_file, output_dir, 
                              robot_room_type_config_file, robot_process_record_file, 
                              robot_white_list_file, need_robot_reply=False, data_file_field_num=2, filter_group_name='all', flag='', prompt_file_map=None,
                              mysql_config_file='config/mysql_conn_config.json', llm_stats_file=None):
    """
    批量处理机器人的数据
    """
    robot_room_type_config = load_robot_room_type(robot_room_type_config_file, filter_group_name)
    
    if os.path.exists(robot_process_record_file):
        robot_process_record = load_3file_dict(robot_process_record_file)
    else:
        robot_process_record = dict()
    robot_white_list_dict = load_white_list_dict(robot_white_list_file)
    logging.info(f'robot_white:\n{robot_white_list_dict}\n')
    identity_lookup = load_contact_identity_lookup(mysql_config_file)
    prompt_file_map_dict = common_utils.load_map_dict(prompt_file_map, k_field=0, value_field=1)
    logging.info(f'prompt_file_map:\n{prompt_file_map}\nprompt_file_map_dict:\n{prompt_file_map_dict}\n')
    robot_stats_list = []
    fatal_errors = []
    fatal_exception = None
    try:
        with open(data_file, encoding='utf8') as f:
            for line in f:
                line = line.strip('\n')
                if not line:
                    continue
                fields = line.split('\t')
                robot_name = fields[0]
                platform = fields[1]
                robot_data_file = fields[data_file_field_num]
                prompt_file = prompt_file_map_dict.get(platform, None)
                if prompt_file:
                    prompt_file = prompt_file.strip()
                logging.info(f'robot_name:{robot_name} platform:{platform} data_file:{robot_data_file} prompt_file:{prompt_file}')
                robot_stats = {'robot_name': robot_name}
                try:
                    qa_list = process_one_robot_group_data(
                        robot_name,
                        robot_data_file,
                        robot_room_type_config,
                        robot_white_list_dict,
                        robot_process_record,
                        prompt_file=prompt_file,
                        client=platform,
                        identity_lookup=identity_lookup,
                        mysql_config_file=mysql_config_file,
                        run_stats=robot_stats
                    )
                except Exception as e:
                    robot_stats['fatal_error'] = {
                        'error_type': type(e).__name__,
                        'error': str(e)[:500],
                    }
                    fatal_errors.append({
                        'robot_name': robot_name,
                        'error_type': type(e).__name__,
                        'error': str(e)[:500],
                    })
                    fatal_exception = e
                    robot_stats_list.append(robot_stats)
                    break
                robot_stats_list.append(robot_stats)
                qa_save_file = f"{output_dir}/{robot_name}_{platform}_json_{flag}.txt"
                with open(qa_save_file, 'w', encoding='utf8') as qa_file:
                    for qa_info in qa_list:
                        qa_file.write(json.dumps(qa_info, ensure_ascii=False) + '\n')
                print(f'{line}\t{qa_save_file}')
    finally:
        write_llm_run_summary(
            llm_stats_file,
            build_llm_run_summary(robot_stats_list, fatal_errors=fatal_errors)
        )

    if fatal_exception is not None:
        raise fatal_exception

    failed_group_count = sum(item.get('groups_failed', 0) for item in robot_stats_list)
    if failed_group_count:
        raise RuntimeError(
            'chat QA group processing failed for %s group(s); task and watermarks must fail' %
            failed_group_count
        )

    save_3file_dict(robot_process_record_file, robot_process_record)


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    import fire
    fire.Fire({
        'run_batch_robot_chat_data': run_batch_robot_chat_data,
        'process_one_robot_group_data': process_one_robot_group_data,
        'build_direct_llm_quality_batch': build_direct_llm_quality_batch,
        'write_quality_bucket_file': write_quality_bucket_file,
    })
