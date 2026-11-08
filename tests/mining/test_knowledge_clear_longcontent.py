import json
import sys
import types


def _make_stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


try:
    import openpyxl  # noqa: F401
except ImportError:
    openpyxl = _make_stub("openpyxl", Workbook=object, load_workbook=lambda *args, **kwargs: None)
    openpyxl.__path__ = []
    _make_stub("openpyxl.utils", get_column_letter=lambda col: str(col))

if "openpyxl_image_loader" not in sys.modules:
    _make_stub("openpyxl_image_loader", SheetImageLoader=object)

try:
    import PIL  # noqa: F401
except ImportError:
    pil = _make_stub("PIL")
    pil.__path__ = []
    _make_stub("PIL.Image", open=lambda *args, **kwargs: None)

from kdb.mining.common.generation.long_qa import build_page_chunks
from kdb.mining.common.generation.long_qa import clear_pdf_json_content
from kdb.mining.common.generation.long_qa import fallback_page_segments
from kdb.mining.common.generation.long_qa import normalize_segments_in_chunk
from kdb.mining.common.generation.long_qa import add_quality_info_to_qa_json
from kdb.mining.common.generation.long_qa import parse_answer
from kdb.mining.common.generation.long_qa import parse_dify_segment
from kdb.mining.common.generation.long_qa import split_segment_for_qa


class DummyDify:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request_dify(self, paragraph):
        self.calls.append(paragraph)
        return self.response


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


def test_build_page_chunks_limits_to_40_pages():
    chunks = build_page_chunks(_make_pages(85), max_chars=80000, max_pages=40)

    assert chunks == [
        {"pages": [1, 40]},
        {"pages": [41, 80]},
        {"pages": [81, 85]},
    ]


def test_normalize_segments_clamps_to_hard_chunk():
    normalized = normalize_segments_in_chunk(
        [
            {"title": "before", "pages": [1, 12]},
            {"title": "inside", "pages": [13, 15]},
            {"title": "after", "pages": [21, 22]},
        ],
        {"pages": [10, 20]},
    )

    assert normalized == [
        {"title": "before", "pages": [10, 12]},
        {"title": "inside", "pages": [13, 15]},
    ]


def test_fallback_and_qa_split_are_page_bounded():
    assert fallback_page_segments({"pages": [1, 25]}, max_pages=10) == [
        {"title": "第1-10页", "pages": [1, 10]},
        {"title": "第11-20页", "pages": [11, 20]},
        {"title": "第21-25页", "pages": [21, 25]},
    ]

    qa_segments = split_segment_for_qa(_make_pages(25), {"title": "all", "pages": [1, 25]}, max_pages=10)
    assert [item["pages"] for item in qa_segments] == [[1, 10], [11, 20], [21, 25]]


def test_parse_none_outputs_do_not_raise():
    assert parse_dify_segment(None) == []
    assert parse_answer(None, "demo.docx", [1, 1]) == []


def test_clear_pdf_json_content_uses_hard_chunks_and_fallback(tmp_path):
    pdf_json = tmp_path / "content.json"
    output = tmp_path / "qa.json"
    pdf_json.write_text(json.dumps(_make_pages(45), ensure_ascii=False), encoding="utf-8")

    dify_segment = DummyDify(None)
    dify_subtract = DummyDify("问题: 测试问题\n答案: 测试答案")

    result = clear_pdf_json_content(
        str(pdf_json),
        str(output),
        dify_segment,
        dify_subtract,
        "demo.docx",
        use_image_content=0,
    )

    assert len(dify_segment.calls) == 2
    assert len(dify_subtract.calls) == 5
    assert [item["from_page"] for item in result] == [
        [1, 10],
        [11, 20],
        [21, 30],
        [31, 40],
        [41, 45],
    ]
    assert json.loads(output.read_text(encoding="utf-8")) == result


def test_parse_answer_accepts_fullwidth_colon():
    """模型输出的冒号形态不稳定：同一批里既有 `问题:` 也有 `问题：`。

    只认半角会让整页解析成空列表，再被 add_quality_info_to_qa_json 当空输入抛异常，
    整页 QA 静默丢失（实测 task 9e92dc27 的 FAQs 页就这么丢的）。
    """
    answer = "问题：如何在沙盒中测试集成？\n答案：使用沙盒应用密钥进行 API 调用身份验证。"
    result = parse_answer(answer, "faq.html", [1, 1])
    assert len(result) == 1
    assert result[0]["q"] == "如何在沙盒中测试集成？"
    assert result[0]["a"] == "使用沙盒应用密钥进行 API 调用身份验证。"


def test_parse_answer_still_accepts_halfwidth_colon():
    result = parse_answer("问题: 半角问题\n答案: 半角答案", "a.html", [1, 1])
    assert len(result) == 1 and result[0]["q"] == "半角问题"


def test_parse_answer_mixed_colon_forms_in_one_answer():
    answer = "问题：全角问\n答案：全角答\n###\n问题: 半角问\n答案: 半角答"
    result = parse_answer(answer, "a.html", [1, 1])
    assert [r["q"] for r in result] == ["全角问", "半角问"]


def test_add_quality_info_returns_empty_instead_of_raising_on_empty_qa():
    """空 QA 列表不该调 Dify —— 空输入会抛 ValueError 把整页产出带没。"""
    class ExplodingDify:
        def request_dify(self, text, other_inputs=None):
            raise AssertionError("空 QA 时不应该调用 Dify")

    result = add_quality_info_to_qa_json([], ExplodingDify())
    assert result == {"high": [], "mid": []}
