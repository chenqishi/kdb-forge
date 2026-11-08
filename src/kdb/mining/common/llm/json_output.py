import json
import re

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
