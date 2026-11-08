from kdb.mining.chat.prompts import resolve_direct_llm_system_prompt
from kdb.shared.config.global_config import GLOBAL_CONFIG as config
import logging
import os
import requests
import time
import traceback

class DirectLLMJsonRequest(object):
    """
    直接请求 DeepSeek/OpenAI-compatible chat completions，要求返回 JSON。
    环境变量优先级：
    CHATKNOWLEDGE_LLM_API_KEY > DEEPSEEK_API_KEY > OPENAI_API_KEY > GLOBAL_CONFIG
    """
    def __init__(self, api_base=None, api_key=None, model=None, max_retries=3,
                 system_prompt=None, client=None, timeout=600):
        self.api_base = (
            api_base or
            os.environ.get('CHATKNOWLEDGE_LLM_API_BASE') or
            os.environ.get('DEEPSEEK_API_BASE') or
            os.environ.get('OPENAI_BASE_URL') or
            config.get('chatknowledge_llm_api_base') or
            config.get('deepseek_api_base') or
            config.get('openai_base_url') or
            'https://api.deepseek.com'
        ).rstrip('/')
        self.api_key = (
            api_key or
            os.environ.get('CHATKNOWLEDGE_LLM_API_KEY') or
            os.environ.get('DEEPSEEK_API_KEY') or
            os.environ.get('OPENAI_API_KEY') or
            config.get('chatknowledge_llm_api_key') or
            config.get('deepseek_api_key') or
            config.get('openai_api_key')
        )
        self.model = (
            model or
            os.environ.get('CHATKNOWLEDGE_LLM_MODEL') or
            os.environ.get('DEEPSEEK_MODEL') or
            config.get('chatknowledge_llm_model') or
            config.get('deepseek_model') or
            'deepseek-chat'
        )
        self.max_retries = max_retries
        self.timeout = timeout
        self.system_prompt, self.prompt_meta = resolve_direct_llm_system_prompt(client=client)
        self.client = self.prompt_meta['client']
        logging.info(
            'DirectLLMJsonRequest prompt client=%s client_prompt_applied=%s hash=%s',
            self.client or 'default',
            self.prompt_meta['client_prompt_applied'],
            self.prompt_meta['prompt_hash'],
        )
        self._stats = {
            'logical_requests': 0,
            'http_attempts': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'timeout_attempts': 0,
            'non_200_attempts': 0,
            'response_format_fallbacks': 0,
            'prompt_chars': 0,
            'completion_chars': 0,
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'elapsed_seconds': 0.0,
        }

    def validate_config(self):
        if not self.api_key:
            raise RuntimeError(
                'missing LLM api key: set CHATKNOWLEDGE_LLM_API_KEY or DEEPSEEK_API_KEY'
            )

    def get_stats(self):
        stats = dict(self._stats)
        stats['elapsed_seconds'] = round(stats['elapsed_seconds'], 3)
        stats['model'] = self.model
        stats['api_base'] = self.api_base
        stats.update(self.prompt_meta)
        return stats

    def _chat_completions_url(self):
        if self.api_base.endswith('/chat/completions'):
            return self.api_base
        return self.api_base + '/chat/completions'

    def request_json(self, paragraph):
        self._stats['logical_requests'] += 1
        self._stats['prompt_chars'] += len(str(paragraph or ''))
        request_started_at = time.monotonic()
        try:
            self.validate_config()
        except Exception:
            self._stats['failed_requests'] += 1
            self._stats['elapsed_seconds'] += time.monotonic() - request_started_at
            raise

        headers = {
            'Authorization': 'Bearer %s' % self.api_key,
            'Content-Type': 'application/json',
        }
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': self.system_prompt},
                {'role': 'user', 'content': paragraph},
            ],
            'temperature': 0.1,
            'stream': False,
            'response_format': {'type': 'json_object'},
        }
        url = self._chat_completions_url()
        last_error = 'unknown error'

        for attempt in range(self.max_retries):
            request_payload = dict(payload)
            try:
                logging.info(
                    'calling direct llm json api: base=%s model=%s attempt=%s',
                    self.api_base,
                    self.model,
                    attempt + 1
                )
                self._stats['http_attempts'] += 1
                response = requests.post(url, headers=headers, json=request_payload, timeout=self.timeout)
                if response.status_code in (400, 422) and 'response_format' in request_payload:
                    logging.warning('llm response_format rejected, retry without response_format: %s', response.text[:500])
                    self._stats['response_format_fallbacks'] += 1
                    request_payload.pop('response_format', None)
                    self._stats['http_attempts'] += 1
                    response = requests.post(url, headers=headers, json=request_payload, timeout=self.timeout)

                if response.status_code != 200:
                    self._stats['non_200_attempts'] += 1
                    last_error = 'http status %s' % response.status_code
                    logging.error('direct llm api non-200 status=%s body=%s', response.status_code, response.text[:1000])
                    continue

                result = response.json()
                content = result['choices'][0]['message']['content']
                usage = result.get('usage') or {}
                for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                    value = usage.get(key, 0)
                    if isinstance(value, int) and not isinstance(value, bool):
                        self._stats[key] += value
                self._stats['successful_requests'] += 1
                self._stats['completion_chars'] += len(str(content or ''))
                self._stats['elapsed_seconds'] += time.monotonic() - request_started_at
                return content
            except requests.exceptions.Timeout:
                self._stats['timeout_attempts'] += 1
                last_error = 'request timeout'
                logging.error('direct llm api timeout')
            except requests.exceptions.RequestException as e:
                last_error = 'request error: %s' % str(e)
                logging.error('direct llm api request error: %s', str(e))
            except Exception as e:
                last_error = 'unexpected error: %s' % str(e)
                logging.error('direct llm api unexpected error:\n%s', traceback.format_exc())

            if attempt < self.max_retries - 1:
                time.sleep(5)

        self._stats['failed_requests'] += 1
        self._stats['elapsed_seconds'] += time.monotonic() - request_started_at
        raise RuntimeError(
            'direct llm request failed after %s attempts: %s' % (
                self.max_retries,
                last_error
            )
        )
