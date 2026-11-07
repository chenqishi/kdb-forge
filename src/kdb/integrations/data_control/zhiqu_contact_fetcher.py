#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
致趣(Bes) 企业微信外部联系人 API 客户端。

- 读 config/zhiqu_credentials.json 取 (app_id, app_secret)。
- 进程内缓存 access_token，2h TTL；命中 10003 自动刷新重试一次。
- fetch_all_contacts(client) 分页拉全量，返回每条 (wx_external_userid, name, owners)。

API 详情：docs 见 knowledge_database_builder/zhiqu_contact_list_api.md。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('data_control_tools/zhiqu_contact_fetcher.py')
import json
import logging
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = 'https://openapi.beschannels.com'
TOKEN_PATH = '/api/get-access-token'
CONTACT_LIST_PATH = '/mochat/open-api/contact/list'

DEFAULT_CRED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))),
    'config', 'zhiqu_credentials.json',
)
# 留出 60s 余量提前刷新
TOKEN_TTL_SECONDS = 7200 - 60
DEFAULT_PAGE_SIZE = 100
HTTP_TIMEOUT = 30
EXPIRED_CODE = 10003
# 网络层重试：对 timeout/SSL/URL 抖动指数退避（不覆盖业务错误）
MAX_NET_RETRY = 5


def _load_credentials(cred_path):
    with open(cred_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _post_json(path, json_body=None, query=None, timeout=HTTP_TIMEOUT):
    """POST + json；网络层错误（SSL/timeout/URLError）指数退避重试 MAX_NET_RETRY 次。"""
    url = BASE_URL + path
    if query:
        url = url + '?' + urllib.parse.urlencode(query)
    data = json.dumps(json_body or {}, ensure_ascii=False).encode('utf-8')
    last_err = None
    for attempt in range(MAX_NET_RETRY):
        req = urllib.request.Request(
            url, data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, ssl.SSLError, socket.timeout, TimeoutError, ConnectionError) as e:
            last_err = e
            wait = 2 ** attempt
            logging.warning('_post_json %s attempt %d/%d failed: %s. sleep %ds',
                            path, attempt + 1, MAX_NET_RETRY, e, wait)
            time.sleep(wait)
    raise last_err


class ZhiquClient:
    """单 client 的致趣 API 客户端，复用 token 缓存。"""

    def __init__(self, client, app_id, app_secret):
        self.client = client
        self.app_id = app_id
        self.app_secret = app_secret
        self._token = None
        self._token_expire_at = 0

    def _fetch_token(self):
        resp = _post_json(TOKEN_PATH, json_body={'appId': self.app_id, 'appSecret': self.app_secret})
        if resp.get('code') != 0:
            raise RuntimeError(f'[zhiqu][{self.client}] 获取 access_token 失败: {resp}')
        token = resp['data']['access_token']
        self._token = token
        self._token_expire_at = time.time() + TOKEN_TTL_SECONDS
        logging.info('[zhiqu][%s] access_token refreshed', self.client)
        return token

    def get_token(self):
        if not self._token or time.time() >= self._token_expire_at:
            return self._fetch_token()
        return self._token

    def list_contacts_page(self, page, page_size=DEFAULT_PAGE_SIZE):
        """调一页。命中 10003 刷新 token 重试一次。"""
        token = self.get_token()
        body = {'page': page, 'page_size': page_size}
        resp = _post_json(CONTACT_LIST_PATH, json_body=body, query={'access_token': token})
        if resp.get('code') == EXPIRED_CODE:
            logging.info('[zhiqu][%s] token 过期(10003)，刷新重试', self.client)
            token = self._fetch_token()
            resp = _post_json(CONTACT_LIST_PATH, json_body=body, query={'access_token': token})
        if resp.get('code') != 0:
            raise RuntimeError(f'[zhiqu][{self.client}] contact/list 失败 page={page}: {resp}')
        return resp.get('data') or {}

    def fetch_all_contacts(self, page_size=DEFAULT_PAGE_SIZE):
        """
        分页拉全量。返回 list[dict]：
          {wx_external_userid, name, owners=[添加人 nick_name, ...]}
        owners 顺序：is_primary=1 在前，其余按返回顺序。
        """
        results = []
        page = 1
        total_page = None
        while True:
            data = self.list_contacts_page(page, page_size)
            items = data.get('list') or []
            for item in items:
                wx_id = item.get('wx_external_userid')
                if not wx_id:
                    continue
                owners_raw = item.get('user_owner') or []
                primary = [o.get('name') for o in owners_raw if o.get('is_primary') == 1 and o.get('name')]
                others = [o.get('name') for o in owners_raw if o.get('is_primary') != 1 and o.get('name')]
                # 去重保序
                owners = []
                for n in primary + others:
                    if n and n not in owners:
                        owners.append(n)
                results.append({
                    'wx_external_userid': wx_id,
                    'name': (item.get('name') or '').strip(),
                    'owners': owners,
                })
            page_info = data.get('page') or {}
            total_page = page_info.get('totalPage', total_page)
            if not items or total_page is None or page >= total_page:
                break
            page += 1
        return results


def build_clients(cred_path=DEFAULT_CRED_PATH):
    """凭据文件 → {client: ZhiquClient}"""
    creds = _load_credentials(cred_path)
    return {c: ZhiquClient(c, v['app_id'], v['app_secret']) for c, v in creds.items()}


def fetch_all_contacts(client, cred_path=DEFAULT_CRED_PATH, page_size=DEFAULT_PAGE_SIZE):
    """便捷入口。"""
    clients = build_clients(cred_path)
    if client not in clients:
        raise KeyError(f'zhiqu_credentials.json 中未找到 client="{client}"，已知: {list(clients)}')
    return clients[client].fetch_all_contacts(page_size=page_size)
