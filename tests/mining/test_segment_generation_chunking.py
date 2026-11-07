import json
import os
import re
import sys
import types


def _make_stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


try:
    __import__("requests")
except Exception:
    _make_stub("requests")
if "kdb.shared.clients.dify_tools" not in sys.modules:
    _make_stub("kdb.shared.clients.dify_tools", DifyWorkFlowRequest=object)
if "kdb.shared.text.text_utils" not in sys.modules:
    _make_stub(
        "kdb.shared.text.text_utils",
        text_segment_by_limit=lambda text, **kwargs: ([text], [text]),
    )
if "openpyxl_image_loader" not in sys.modules:
    _make_stub("openpyxl_image_loader", SheetImageLoader=object)
try:
    __import__("PIL")
except Exception:
    pil = _make_stub("PIL")
    pil.__path__ = []
    _make_stub("PIL.Image", open=lambda *args, **kwargs: None)

from kdb.mining.generation.builders.knowlege_segment_builder_by_dify import fill_uncovered_segments_in_chunk
from kdb.mining.generation.builders.knowlege_segment_builder_by_dify import get_segment_knowledge_by_dify


class DummySegmentDify:
    def __init__(self):
        self.calls = []

    def request_dify(self, paragraph):
        self.calls.append(paragraph)
        pages = [int(page) for page in re.findall(r"第(\d+)页内容如下", paragraph)]
        return f"主题 第{pages[0]}页 第{pages[-1]}页"


class DummyIndexDify:
    def __init__(self):
        self.calls = []

    def request_dify(self, paragraph):
        self.calls.append(paragraph)
        return "关键词:Wayfair\n短语:运营宝典\n主题:供应商运营"


def test_sparse_original_page_number_is_not_lost(tmp_path):
    pdf_json = tmp_path / "content.json"
    pdf_json.write_text(json.dumps({"23": [{"type": "text", "text_content": "入驻要求"}]}))
    index = DummyIndexDify()
    segments = get_segment_knowledge_by_dify(
        str(pdf_json), DummySegmentDify(), index, from_file_name="slides.pdf",
    )
    assert "入驻要求" in index.calls[0]
    assert segments


def test_image_ocr_is_used_in_chunk_boundaries():
    from kdb.mining.generation.processing.knowledge_clear_by_dify_model_longcontent import build_page_chunks
    pages = {str(n): [{"type": "image", "is_valid": True,
                      "public_url": "https://example.com/slide.png",
                      "image_ocr": "文字" * 100}] for n in range(1, 4)}
    chunks = build_page_chunks(pages, max_chars=500, use_image_content=1)
    assert len(chunks) == 3


def test_image_only_document_passes_ocr_to_segmentation_and_index(tmp_path):
    pdf_json = tmp_path / "content.json"
    pages = {str(n): [{"type": "image", "is_valid": True,
                      "public_url": f"https://example.com/slide{n}.png",
                      "image_ocr": "招商入驻要求" * 500}] for n in range(1, 4)}
    pdf_json.write_text(json.dumps(pages))
    segment, index = DummySegmentDify(), DummyIndexDify()
    result = get_segment_knowledge_by_dify(
        str(pdf_json), segment, index, from_file_name="slides.pdf", use_image_content=1,
    )
    assert result
    assert segment.calls and all("招商入驻要求" in call for call in segment.calls)
    assert index.calls and all("招商入驻要求" in call for call in index.calls)


def test_parallel_segment_indexes_keep_page_order_and_limit(tmp_path):
    import threading
    import time
    pdf_json = tmp_path / "content.json"
    pdf_json.write_text(json.dumps(_make_pages(85)))

    class ConcurrentIndex(DummyIndexDify):
        def __init__(self):
            super().__init__()
            self.lock = threading.Lock()
            self.active = self.peak = 0

        def request_dify(self, paragraph):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                time.sleep(0.02)
                return super().request_dify(paragraph)
            finally:
                with self.lock:
                    self.active -= 1

    index = ConcurrentIndex()
    result = get_segment_knowledge_by_dify(
        str(pdf_json), DummySegmentDify(), index, from_file_name="slides.pdf", index_workers=4,
    )
    assert 1 < index.peak <= 4
    assert [x['pages'] for x in result] == [[1, 10], [11, 20], [21, 30], [31, 40],
                                          [41, 50], [51, 60], [61, 70], [71, 80], [81, 85]]


def _make_pages(page_count, text_len=80):
    return {
        str(page): [
            {
                "type": "text",
                "text_content": f"page {page} " + ("x" * text_len),
            }
        ]
        for page in range(1, page_count + 1)
    }


def test_segment_generation_chunks_long_document_before_dify(tmp_path):
    pdf_json = tmp_path / "content.json"
    pdf_json.write_text(json.dumps(_make_pages(85), ensure_ascii=False), encoding="utf-8")

    segment_dify = DummySegmentDify()
    index_dify = DummyIndexDify()
    segments = get_segment_knowledge_by_dify(
        str(pdf_json),
        segment_dify,
        index_dify,
        from_file_name="Wayfair.docx",
        use_image_content=0,
    )

    assert len(segment_dify.calls) == 3
    assert ["第1页内容如下" in call for call in segment_dify.calls] == [True, False, False]
    assert ["第41页内容如下" in call for call in segment_dify.calls] == [False, True, False]
    assert ["第81页内容如下" in call for call in segment_dify.calls] == [False, False, True]
    assert len(index_dify.calls) == 9
    assert [segment["pages"] for segment in segments] == [
        [1, 10],
        [11, 20],
        [21, 30],
        [31, 40],
        [41, 50],
        [51, 60],
        [61, 70],
        [71, 80],
        [81, 85],
    ]


def test_fill_uncovered_segments_in_chunk_adds_gap_segments():
    segments = [
        {"title": "A", "pages": [41, 42]},
        {"title": "B", "pages": [81, 85]},
    ]

    filled = fill_uncovered_segments_in_chunk(segments, {"pages": [41, 85]})

    assert [segment["pages"] for segment in filled] == [
        [41, 42],
        [43, 52],
        [53, 62],
        [63, 72],
        [73, 80],
        [81, 85],
    ]
