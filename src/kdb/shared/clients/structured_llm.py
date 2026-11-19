"""Explicit direct LLM calls with JSON validation and measured usage."""
import json

import requests


def record_usage(usage, raw):
    if usage is None:
        return
    usage['calls'] = usage.get('calls', 0) + 1
    raw = raw or {}
    for key, alias in [('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens')]:
        value = raw.get(key, raw.get(alias))
        if value is not None:
            usage[key] = usage.get(key, 0) + int(value)
    total = raw.get('total_tokens')
    if total is None and ('input_tokens' in raw or 'prompt_tokens' in raw) and ('output_tokens' in raw or 'completion_tokens' in raw):
        total = raw.get('input_tokens', raw.get('prompt_tokens')) + raw.get('output_tokens', raw.get('completion_tokens'))
    if total is None:
        usage['unknown_usage_calls'] = usage.get('unknown_usage_calls', 0) + 1
    else:
        usage['total_tokens'] = usage.get('total_tokens', 0) + int(total)


def request_json(system, payload, config=None, usage=None):
    config = config or {}
    query = json.dumps(payload, ensure_ascii=False)
    raw_usage = {}
    try:
        if config.get('endpoint'):
            if not config.get('api_key') or not config.get('model'):
                raise ValueError('LLM api_key and model are required')
            response = requests.post(config['endpoint'],
                headers={'Authorization': 'Bearer ' + config['api_key']},
                json={'model': config['model'], 'temperature': 0,
                      **({'response_format': {'type': 'json_object'}} if config.get('json_mode', True) else {}),
                      'max_tokens': config.get('max_tokens', 1500),
                      'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': query}]},
                timeout=config.get('timeout', 90))
            response.raise_for_status()
            body = response.json()
            raw_usage = body.get('usage') or {}
            content = body['choices'][0]['message']['content']
        else:
            from kdb.shared.clients.local_llm_adapter import request_knowledge_llm
            content = request_knowledge_llm(query=query, system_message=system,
                model_name=config.get('model'), provider=config.get('provider'),
                temperature=0, max_tokens=config.get('max_tokens', 1500), usage_out=raw_usage)
        if not content:
            raise RuntimeError('LLM is unavailable or returned an empty result')
        content = content.strip()
        if content.startswith('```') and content.endswith('```'):
            content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError('LLM response must be a JSON object')
        return parsed
    finally:
        record_usage(usage, raw_usage)
