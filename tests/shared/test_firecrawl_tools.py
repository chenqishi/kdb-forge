# -*- coding: utf-8 -*-
"""src/kdb/shared/clients/firecrawl_tools.py 的离线单测（不打网络，requests.post 全部打桩）。"""

import json

import pytest

import kdb.shared.clients.firecrawl_tools as firecrawl_tools
from kdb.shared.clients.firecrawl_tools import FirecrawlScraper
from kdb.shared.clients.firecrawl_tools import build_cookie_headers
from kdb.shared.clients.firecrawl_tools import fetch_firecrawl_content


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


def ok_payload(markdown='正文'):
    return {'success': True, 'data': {'markdown': markdown}}


@pytest.fixture
def scraper():
    return FirecrawlScraper(api_key='fc-test', max_retries=3)


class TestBuildCookieHeaders:
    def test_raw_cookie_string(self):
        assert build_cookie_headers('DEV-PORTAL-LANGUAGE=zh-CN; a=b') == {
            'Cookie': 'DEV-PORTAL-LANGUAGE=zh-CN; a=b'}

    def test_dict_of_cookies_is_joined(self):
        assert build_cookie_headers({'DEV-PORTAL-LANGUAGE': 'zh-CN', 'a': 'b'}) == {
            'Cookie': 'DEV-PORTAL-LANGUAGE=zh-CN; a=b'}

    def test_dict_already_headers_is_passed_through(self):
        # 已经是 headers 字典就别再包一层 Cookie
        assert build_cookie_headers({'Cookie': 'x=1'}) == {'Cookie': 'x=1'}
        assert build_cookie_headers({'cookie': 'x=1'}) == {'cookie': 'x=1'}

    def test_empty_inputs_give_empty_dict(self):
        assert build_cookie_headers(None) == {}
        assert build_cookie_headers('') == {}
        assert build_cookie_headers('   ') == {}
        assert build_cookie_headers({}) == {}

    def test_user_agent_and_extra_headers(self):
        assert build_cookie_headers('a=b', user_agent='UA/1', extra_headers={'X': 'y'}) == {
            'Cookie': 'a=b', 'User-Agent': 'UA/1', 'X': 'y'}


class TestScrapePayload:
    def _capture(self, monkeypatch):
        sent = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            sent['url'] = url
            sent['auth'] = headers.get('Authorization')
            sent['body'] = json
            return FakeResponse(payload=ok_payload())

        monkeypatch.setattr(firecrawl_tools.requests, 'post', fake_post)
        return sent

    def test_defaults_match_the_dify_workflow(self, monkeypatch, scraper):
        # 默认值抄自 data/网页爬取url.yml，换实现后产物必须不变
        sent = self._capture(monkeypatch)
        scraper.scrape('https://x.test/p')
        body = sent['body']
        assert body['formats'] == ['markdown']
        assert body['onlyMainContent'] is True
        assert body['timeout'] == 30000
        assert body['waitFor'] == 0
        assert 'headers' not in body          # 不传 cookie 时不放 headers
        assert 'includeTags' not in body
        assert 'excludeTags' not in body
        assert sent['url'] == 'https://api.firecrawl.dev/v2/scrape'
        assert sent['auth'] == 'Bearer fc-test'

    def test_headers_dict_is_sent(self, monkeypatch, scraper):
        sent = self._capture(monkeypatch)
        scraper.scrape('https://x.test/p', headers={'Cookie': 'k=v'})
        assert sent['body']['headers'] == {'Cookie': 'k=v'}

    def test_headers_string_is_normalized(self, monkeypatch, scraper):
        sent = self._capture(monkeypatch)
        scraper.scrape('https://x.test/p', headers='k=v')
        assert sent['body']['headers'] == {'Cookie': 'k=v'}

    def test_overrides(self, monkeypatch, scraper):
        sent = self._capture(monkeypatch)
        scraper.scrape('https://x.test/p', wait_for=5000, page_timeout=60000,
                       only_main_content=False, include_tags=['main'], exclude_tags=['nav'])
        body = sent['body']
        assert (body['waitFor'], body['timeout'], body['onlyMainContent']) == (5000, 60000, False)
        assert body['includeTags'] == ['main'] and body['excludeTags'] == ['nav']


class TestScrapeBehavior:
    def test_returns_markdown(self, monkeypatch, scraper):
        monkeypatch.setattr(firecrawl_tools.requests, 'post',
                            lambda *a, **k: FakeResponse(payload=ok_payload('# 标题')))
        assert scraper.scrape('https://x.test/p') == '# 标题'

    def test_retries_then_succeeds(self, monkeypatch, scraper):
        calls = []

        def flaky(*a, **k):
            calls.append(1)
            if len(calls) < 3:
                return FakeResponse(status_code=502, text='Bad Gateway')
            return FakeResponse(payload=ok_payload('ok'))

        monkeypatch.setattr(firecrawl_tools.requests, 'post', flaky)
        assert scraper.scrape('https://x.test/p') == 'ok'
        assert len(calls) == 3

    def test_raises_after_retries_exhausted(self, monkeypatch, scraper):
        monkeypatch.setattr(firecrawl_tools.requests, 'post',
                            lambda *a, **k: FakeResponse(status_code=500, text='boom'))
        with pytest.raises(RuntimeError):
            scraper.scrape('https://x.test/p')

    def test_success_false_raises(self, monkeypatch, scraper):
        monkeypatch.setattr(firecrawl_tools.requests, 'post',
                            lambda *a, **k: FakeResponse(payload={'success': False, 'error': 'nope'}))
        with pytest.raises(RuntimeError):
            scraper.scrape('https://x.test/p')

    def test_empty_markdown_returns_empty_without_retrying(self, monkeypatch, scraper):
        # 关掉长度校验时，请求本身成功，重试也是一样的空——不该浪费 3 次调用
        calls = []

        def counting(*a, **k):
            calls.append(1)
            return FakeResponse(payload={'success': True, 'data': {'markdown': ''}})

        monkeypatch.setattr(firecrawl_tools.requests, 'post', counting)
        assert scraper.scrape('https://x.test/p', min_content_length=0) == ''
        assert len(calls) == 1

    def test_short_content_is_retried_then_succeeds(self, monkeypatch, scraper):
        """firecrawl 间歇性返回只剩样板的近乎空内容却 success=true，必须重试。"""
        calls = []

        def flaky(*a, **k):
            calls.append(1)
            md = '/posts/x' if len(calls) < 3 else '正文' * 300
            return FakeResponse(payload={'success': True, 'data': {'markdown': md}})

        monkeypatch.setattr(firecrawl_tools.requests, 'post', flaky)
        out = scraper.scrape('https://x.test/p', min_content_length=400)
        assert len(out) >= 400
        assert len(calls) == 3

    def test_short_content_raises_when_never_recovers(self, monkeypatch, scraper):
        monkeypatch.setattr(firecrawl_tools.requests, 'post',
                            lambda *a, **k: FakeResponse(
                                payload={'success': True, 'data': {'markdown': '/posts/x'}}))
        with pytest.raises(RuntimeError, match='正文过短'):
            scraper.scrape('https://x.test/p', min_content_length=400)

    def test_min_content_length_zero_disables_the_check(self, monkeypatch, scraper):
        monkeypatch.setattr(firecrawl_tools.requests, 'post',
                            lambda *a, **k: FakeResponse(payload=ok_payload('短')))
        assert scraper.scrape('https://x.test/p', min_content_length=0) == '短'

    def test_missing_api_key_raises_instead_of_silent_fallback(self, monkeypatch):
        monkeypatch.setitem(firecrawl_tools.GLOBAL_CONFIG, 'firecrawl_api_key', None)
        with pytest.raises(ValueError):
            FirecrawlScraper()


class TestFetchFirecrawlContent:
    def test_passes_cookie_through(self, monkeypatch, scraper):
        sent = {}

        body_text = '中文正文' * 200

        def fake_post(url, headers=None, json=None, timeout=None):
            sent['body'] = json
            return FakeResponse(payload=ok_payload(body_text))

        monkeypatch.setattr(firecrawl_tools.requests, 'post', fake_post)
        out = fetch_firecrawl_content('https://x.test/p', cookie='DEV-PORTAL-LANGUAGE=zh-CN',
                                      scraper=scraper)
        assert out == body_text
        assert sent['body']['headers'] == {'Cookie': 'DEV-PORTAL-LANGUAGE=zh-CN'}

    def test_default_min_content_length_is_applied(self, monkeypatch, scraper):
        """默认就要挡住 firecrawl 的间歇性空返回，调用方不必自己想起来设。"""
        calls = []

        def short(*a, **k):
            calls.append(1)
            return FakeResponse(payload=ok_payload('/posts/x'))

        monkeypatch.setattr(firecrawl_tools.requests, 'post', short)
        assert fetch_firecrawl_content('https://x.test/p', scraper=scraper) == ''
        assert len(calls) == 3      # 重试过，不是一次就放行

    def test_swallows_errors_by_default(self, monkeypatch, scraper):
        monkeypatch.setattr(firecrawl_tools.requests, 'post',
                            lambda *a, **k: FakeResponse(status_code=500, text='boom'))
        assert fetch_firecrawl_content('https://x.test/p', scraper=scraper) == ''

    def test_raise_on_error_propagates(self, monkeypatch, scraper):
        monkeypatch.setattr(firecrawl_tools.requests, 'post',
                            lambda *a, **k: FakeResponse(status_code=500, text='boom'))
        with pytest.raises(RuntimeError):
            fetch_firecrawl_content('https://x.test/p', scraper=scraper, raise_on_error=True)
