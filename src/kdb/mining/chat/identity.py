from kdb.mining.chat._batch_state import ANSWER_SOURCE_ROLES
from kdb.mining.chat._batch_state import COLLEAGUE_SOURCE_ROLE
from kdb.mining.chat._batch_state import LEADER_SOURCE_ROLE
from kdb.mining.chat._batch_state import QUESTION_SOURCE_ROLE
import logging
import os
import re
import traceback

UNKNOWN_SOURCE_ROLE = '未识别/不能作为答案来源'


IDENTITY_PRIORITY = {
    LEADER_SOURCE_ROLE: 100,
    COLLEAGUE_SOURCE_ROLE: 90,
    QUESTION_SOURCE_ROLE: 10,
    UNKNOWN_SOURCE_ROLE: 0,
}


AI_SPEAKER_KEYWORD_RE = re.compile(r'(?i)(?<![A-Za-z])ai(?![A-Za-z])')


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
        from kdb.shared.database.mysql import MySQLConnector

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
