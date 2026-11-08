from kdb.mining.chat.media import is_image_placeholder_or_address
from kdb.mining.chat.message_cleaning import sanitize_chat_content
from kdb.mining.chat.quality.qa import normalize_qa_text
import re

NOISE_ACK_TEXT = {
    '好', '好的', '收到', '已收到', '嗯', '嗯嗯', 'ok', 'OK', 'Ok', '谢谢',
    '感谢', '辛苦了', '麻烦了', '可以', '可以的', '是的', '对', '对的', '不是', '1',
    '应该是', '应该可以', '看着应该是了', '没问题',
    'yes', 'no', 'yep', 'nope', 'sure', 'thanks', 'thank you', 'thx',
    'noted', 'noted a moment', 'one moment', 'wait a moment', 'sorry', 'oh sorry',
}


CHAT_URL_PATTERN = r'https?://[^\s，。；、）)】\]\}<>"“”]+|www\.[^\s，。；、）)】\]\}<>"“”]+'


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
