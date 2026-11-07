# -*- coding: utf-8 -*-
"""文档解析成本：每个文档固定 100 积分的回归测试。

2026-09-17 改动：原来按 token_count/10000 + image_count 计价，
改为按文档数计费（CREDITS_PER_DOCUMENT=100），与文档内容无关。
字符/token/图片数仍照常统计返回，但不再参与计费。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_document_clear_price.py')
import os
import sys
import tempfile
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))

fitz = pytest.importorskip("fitz", reason="统计 PDF 需要 pymupdf")
m = pytest.importorskip("data_preprocess.document_clear_price_access",
                        reason="需要 minio/config 依赖")


def _make_pdf(path, pages=1, text="测试内容"):
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), text[:2000])
    doc.save(path)
    doc.close()
    return path


def test_credits_per_document_is_100():
    assert m.CREDITS_PER_DOCUMENT == 100


def test_credits_independent_of_document_size(tmp_path):
    """核心：1 页和 30 页、短文本和长文本，积分都该是 100。

    这正是本次改动的目的——前端只要知道「几个文档 = 几百积分」。
    """
    small = m.count_pdf_stats(_make_pdf(str(tmp_path / "s.pdf"), 1, "短"))
    big = m.count_pdf_stats(_make_pdf(str(tmp_path / "b.pdf"), 30, "很长的内容 " * 500))

    assert small["credits"] == 100
    assert big["credits"] == 100
    # 统计数据仍然有差异，只是不参与计费
    assert big["token_count"] > small["token_count"]


def test_stats_still_reported(tmp_path):
    """字符/token/图片数要照常返回，供观察与对账。"""
    s = m.count_pdf_stats(_make_pdf(str(tmp_path / "a.pdf"), 2, "内容内容内容"))
    for k in ("char_count", "token_count", "image_count", "credits"):
        assert k in s
    assert s["char_count"] > 0


def test_failed_document_is_not_charged(tmp_path):
    """解析失败的文档必须 0 积分，不能也收 100。"""
    bad = tmp_path / "x.txt"
    bad.write_text("not a pdf")
    r = m.access_document_clear_price(str(bad))
    assert r["credits"] == 0
    assert "error" in r


def _files(n):
    return [{"name": "f%d" % i, "ext": "pdf", "store_method": "minio",
             "address": "a%d" % i} for i in range(n)]


def test_batch_total_is_count_times_100():
    ok = {"char_count": 10, "token_count": 20, "image_count": 1, "credits": 100}
    with mock.patch.object(m.S3_DOWNLOADER, "download_file", return_value=True), \
         mock.patch.object(m.os.path, "exists", return_value=True), \
         mock.patch.object(m, "access_document_clear_price", return_value=ok):
        r = m.asscess_document_clear_price(_files(3))
    assert r["total_credits"] == 300
    assert len(r["detail_info"]) == 3


def test_batch_skips_failed_downloads():
    """下载失败的不计入积分，只进 error_files。"""
    ok = {"char_count": 10, "token_count": 20, "image_count": 1, "credits": 100}
    with mock.patch.object(m.S3_DOWNLOADER, "download_file",
                           side_effect=[True, True, True, False]), \
         mock.patch.object(m.os.path, "exists", return_value=True), \
         mock.patch.object(m, "access_document_clear_price", return_value=ok):
        r = m.asscess_document_clear_price(_files(4))
    assert r["total_credits"] == 300, "4 个文件只有 3 个成功，应为 300 而非 400"
    assert len(r["error_files"]) == 1


def test_batch_skips_parse_errors():
    """解析失败的同样不计费。"""
    ok = {"char_count": 10, "token_count": 20, "image_count": 1, "credits": 100}
    bad = {"char_count": 0, "token_count": 0, "image_count": 0,
           "credits": 0, "error": "文件转换失败"}
    with mock.patch.object(m.S3_DOWNLOADER, "download_file", return_value=True), \
         mock.patch.object(m.os.path, "exists", return_value=True), \
         mock.patch.object(m, "access_document_clear_price", side_effect=[ok, bad, ok]):
        r = m.asscess_document_clear_price(_files(3))
    assert r["total_credits"] == 200
    assert len(r["error_files"]) == 1
