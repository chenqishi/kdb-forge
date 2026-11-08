from kdb.mining.chat._batch_state import ANSWER_SOURCE_ROLES
from kdb.mining.chat._batch_state import COLLEAGUE_SOURCE_ROLE
from kdb.mining.chat._batch_state import LEADER_SOURCE_ROLE
from kdb.mining.chat.message_cleaning import sanitize_chat_content
from kdb.mining.chat.prompts import get_message_identity_info
from kdb.mining.chat.quality.noise import is_noise_chat_content
from kdb.mining.chat.quality.normalization import normalize_bool
from kdb.mining.chat.quality.qa import is_candidate_answer_like_content
from kdb.mining.chat.quality.qa import is_weak_answer
from kdb.mining.chat.quality.qa import normalize_qa_text
import logging
import re

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
