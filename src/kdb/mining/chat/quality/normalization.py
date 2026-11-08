from kdb.mining.chat.message_cleaning import looks_like_image_reference_answer
from kdb.mining.chat.message_cleaning import sanitize_chat_content
from kdb.mining.chat.quality.noise import replace_chat_urls
from kdb.mining.chat.quality.qa import is_weak_generated_answer
from kdb.mining.chat.quality.qa import normalize_qa_text
from kdb.mining.chat.quality.qa import text_overlap_ratio
import json
import re

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
