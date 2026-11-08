from kdb.mining.chat.message_cleaning import looks_like_image_address
from kdb.mining.chat.message_cleaning import looks_like_image_reference_answer
from kdb.mining.chat.message_cleaning import normalize_message_ctype
from kdb.mining.chat.message_cleaning import sanitize_chat_content
from kdb.mining.chat.quality.qa import normalize_qa_text
from kdb.shared.config.global_config import GLOBAL_CONFIG as config
import contextlib
import hashlib
import json
import logging
import mimetypes
import os
import re
import traceback

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
        from kdb.shared.storage.minio import MinioTools
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
