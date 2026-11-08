from kdb.mining.chat._batch_state import ANSWER_SOURCE_ROLES
from kdb.mining.chat._batch_state import COLLEAGUE_SOURCE_ROLE
from kdb.mining.chat._batch_state import LEADER_SOURCE_ROLE
from kdb.mining.chat._batch_state import QUESTION_SOURCE_ROLE
from kdb.mining.chat.identity import _normalize_name
from kdb.mining.chat.identity import infer_speaker_identity
from kdb.mining.chat.identity import lookup_contact_identity
from kdb.mining.chat.media import normalize_backend_image_info
from kdb.mining.chat.message_cleaning import format_message_time
from kdb.mining.chat.message_cleaning import sanitize_chat_content
from kdb.mining.chat.quality.normalization import get_display_platform_name
from kdb.mining.chat.quality.qa import normalize_qa_text
from kdb.shared.config.paths import resource_path as _resource_path
import hashlib
import json
import logging
import os
import re

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


DIRECT_LLM_PROMPT_DIR = str(_resource_path('prompts', 'mining', 'chat_qa_extract'))


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
