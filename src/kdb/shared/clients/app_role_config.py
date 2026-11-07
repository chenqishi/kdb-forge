#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
应用角色配置（peer / teacher / management）读取。

原来这段逻辑写死在 `control_service/chat_qa_mining_task_control.py:_generate_prompt_file`
里，只服务于「生成挖掘 prompt」这一个场景。质量审核也要用同一份同事名单
（判断答案是同事说的还是卖家说的），所以抽出来共用。
"""

import logging
from typing import Any, Dict, List, Sequence

import requests

from kdb.shared.config.legacy_config import GLOBAL_CONFIG

DEFAULT_ROLE_KEYS = ('peer', 'teacher', 'management')


def fetch_role_config(app_id: str, client: str, timeout: int = 30) -> List[Dict[str, Any]]:
    """
    拉 app 的角色配置列表（intranet 接口，不需要 token）。

    失败直接抛：名单为空会让「答案是否来自同事」的判定整体失效，不能静默降级成空列表。
    """
    url = GLOBAL_CONFIG['app_config_get_url'].format(app_id=app_id, client=client)
    logging.info('拉取应用角色配置: %s', url)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if str(data.get('code')) != '00000':
        raise RuntimeError('角色配置接口返回异常: code=%s msg=%s' % (data.get('code'), data.get('msg')))
    items = data.get('data')
    if not isinstance(items, list):
        raise RuntimeError('角色配置接口 data 不是列表: %r' % (type(items),))
    return items


def extract_colleague_names(config_items: List[Dict[str, Any]],
                            config_keys: Sequence[str] = DEFAULT_ROLE_KEYS) -> List[str]:
    """从角色配置里抽同事昵称，去重保序；configValue 有 list/dict/str 三种形态"""
    names: List[str] = []
    seen = set()

    def _add(name: Any) -> None:
        if isinstance(name, str) and name.strip() and name.strip() not in seen:
            seen.add(name.strip())
            names.append(name.strip())

    for item in config_items or []:
        if not isinstance(item, dict) or item.get('configKey') not in config_keys:
            continue
        value = item.get('configValue')
        if isinstance(value, list):
            for user_info in value:
                if isinstance(user_info, dict):
                    _add(user_info.get('userName'))
        elif isinstance(value, dict):
            _add(value.get('userName'))
        elif isinstance(value, str):
            _add(value)
    return names
