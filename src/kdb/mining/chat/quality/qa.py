from kdb.mining.chat.message_cleaning import sanitize_chat_content
import re

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
