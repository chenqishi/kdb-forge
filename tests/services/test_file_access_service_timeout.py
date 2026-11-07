# -*- coding: utf-8 -*-
"""file_access_service 下载超时的回归测试。

原来 upload_from_url 硬编码 timeout=30 且 /upload_from_url 端点不透传，
大文件或慢源站必然超时失败。改为可配置后，守住三件事：
1. 默认值来自 DEFAULT_DOWNLOAD_TIMEOUT，不再是 30
2. 连接超时与读取超时分开（连不上尽快失败，别把 180 秒耗在握手上）
3. 调用方可按需放大
"""
import importlib
import os
from unittest import mock

import pytest

fs = importlib.import_module("kdb.services.files.app")


def _captured_timeout(**kwargs):
    """调一次 upload_from_url，返回它实际传给 requests.get 的 timeout。"""
    with mock.patch.object(fs.requests, "get") as g:
        g.side_effect = RuntimeError("stop-before-network")
        fs.upload_from_url("https://example.com/a.pdf", **kwargs)
        return g.call_args.kwargs.get("timeout")


def test_default_timeout_is_not_30_seconds():
    """30 秒不够用，这是本次改动的起因。"""
    assert fs.DEFAULT_DOWNLOAD_TIMEOUT > 30


def test_connect_and_read_timeout_are_separate():
    """必须是 (连接, 读取) 二元组：源站连不上要尽快失败，而不是干等读取超时。"""
    t = _captured_timeout()
    assert isinstance(t, tuple) and len(t) == 2
    connect, read = t
    assert connect == fs.CONNECT_TIMEOUT
    assert read == fs.DEFAULT_DOWNLOAD_TIMEOUT
    assert connect < read, "连接超时应远小于读取超时"


def test_caller_can_override_timeout():
    assert _captured_timeout(timeout=600) == (fs.CONNECT_TIMEOUT, 600)


def test_env_var_overrides_default(monkeypatch):
    """运维可用环境变量调整，不必改代码。"""
    monkeypatch.setenv("FILE_SERVICE_DOWNLOAD_TIMEOUT", "600")
    reloaded = importlib.reload(fs)
    try:
        assert reloaded.DEFAULT_DOWNLOAD_TIMEOUT == 600
    finally:
        monkeypatch.delenv("FILE_SERVICE_DOWNLOAD_TIMEOUT", raising=False)
        importlib.reload(fs)


def test_upload_from_url_returns_none_on_download_failure():
    """下载失败要返回 None 由调用方处理，不能抛出去把请求打成 500。"""
    with mock.patch.object(fs.requests, "get") as g:
        g.side_effect = RuntimeError("boom")
        assert fs.upload_from_url("https://example.com/a.pdf") is None


@pytest.mark.parametrize("bad", ["abc", 0, -5])
def test_endpoint_rejects_invalid_timeout(bad):
    """端点传非法 timeout 要 400，而不是拿去当秒数用。"""
    client = fs.app.test_client()
    resp = client.post("/upload_from_url",
                       json={"url": "https://example.com/a.pdf", "timeout": bad})
    assert resp.status_code == 400
    assert "timeout" in resp.get_json()["message"]


def test_endpoint_passes_timeout_through():
    """端点要把 timeout 透传下去——原实现漏了这一步，导致参数形同虚设。"""
    client = fs.app.test_client()
    with mock.patch.object(fs, "upload_from_url", return_value="b/k") as up:
        client.post("/upload_from_url",
                    json={"url": "https://example.com/a.pdf", "timeout": 300})
    assert up.call_args.kwargs.get("timeout") == 300


def test_endpoint_without_timeout_uses_service_default():
    client = fs.app.test_client()
    with mock.patch.object(fs, "upload_from_url", return_value="b/k") as up:
        client.post("/upload_from_url", json={"url": "https://example.com/a.pdf"})
    assert up.call_args.kwargs.get("timeout") is None, "不传则交给函数用默认值"
