from kdb.shared.config.paths import resource_path as _resource_path
import os

PROMPT_DIR = str(_resource_path('prompts', 'mining', 'chat_qa_extract'))


def load_prompt(name: str) -> str:
    """读取 prompts/<name>.md，不存在时返回空串"""
    path = os.path.join(PROMPT_DIR, f'{name}.md')
    if not os.path.exists(path):
        return ''
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()
