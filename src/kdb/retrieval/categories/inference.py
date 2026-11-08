from typing import Any
from typing import Dict
import re

def _category_name_occurs(text: str, category_name: str) -> bool:
    """在自然语言里匹配类目名；短英文名必须有词边界，避免 Bol 命中 symbol。"""
    text = str(text or '')
    category_name = str(category_name or '').strip()
    if not text or not category_name:
        return False
    if re.fullmatch(r'[A-Za-z0-9 .&/()_-]+', category_name):
        return re.search(
            rf'(?<![A-Za-z0-9]){re.escape(category_name)}(?![A-Za-z0-9])',
            text,
            flags=re.I,
        ) is not None
    return category_name.casefold() in text.casefold()


def infer_payoneer_olive_category(self, client: str, data: Dict[str, Any]):
    """用实时类目树从平台字段、标签和问题中识别 Payoneer Olive 平台类目。"""
    client_norm = str(client or '').strip().lower().replace('_', '').replace('-', '')
    if client_norm != 'payoneerolive':
        return None, None

    if not self.all_client_category_dict.get(client, {}).get('name_map_dict'):
        self.load_category_map_dict(client)
    name_map = self.all_client_category_dict.get(client, {}).get('name_map_dict', {})
    if not name_map:
        return None, None

    ext_info = data.get('ext_info') if isinstance(data.get('ext_info'), dict) else {}
    explicit_values = [
        ext_info.get('marketplace'),
        ext_info.get('model_platform'),
    ]
    tags = ext_info.get('tags') or data.get('tags') or []
    if not isinstance(tags, list):
        tags = [tags]
    title = str(data.get('title') or '')

    matches = []
    for category_path, chain in name_map.items():
        if not chain:
            continue
        leaf_name = str(chain[-1].get('category_name') or '').strip()
        if not leaf_name or leaf_name == '默认分组':
            continue
        score = 0
        source = None
        if any(str(value or '').strip().casefold() == leaf_name.casefold()
               for value in explicit_values):
            score, source = 300, 'model_platform'
        elif any(self._category_name_occurs(tag, leaf_name) for tag in tags):
            score, source = 200, 'model_tag'
        elif self._category_name_occurs(title, leaf_name):
            score, source = 100, 'question_text'
        if score:
            # 同等来源时优先更具体的长类目，如 TikTok Shop-美国ACCU。
            matches.append((score, len(category_path), category_path, chain, source))

    if not matches:
        return None, None
    _, _, _, chain, source = sorted(matches, reverse=True)[0]
    leaf = chain[-1]
    category_info = {
        'category_id': str(leaf.get('category_id') or ''),
        'category_name': leaf.get('category_name'),
        'score': 0.9,
        'source': source,
    }
    return chain, category_info
