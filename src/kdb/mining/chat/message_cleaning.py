from datetime import datetime
import re

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


def looks_like_image_reference_answer(text):
    text = str(text or '').strip()
    if not text:
        return False
    parts = [part.strip() for part in re.split(r'[\n,，]+', text) if part.strip()]
    if not parts:
        return False
    return all(looks_like_image_address(part) for part in parts)
