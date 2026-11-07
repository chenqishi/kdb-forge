import os
import sys
import types


def _make_stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _stub_if_import_fails(name, **attrs):
    try:
        __import__(name)
    except Exception:
        _make_stub(name, **attrs)


for module_name in ("PyPDF2", "fitz"):
    _stub_if_import_fails(module_name)
_stub_if_import_fails("docx2pdf", convert=None)
try:
    __import__("docx")
except Exception:
    docx_pkg = _make_stub("docx", Document=None)
    docx_pkg.__path__ = []
_stub_if_import_fails("docx.oxml", parse_xml=lambda *args, **kwargs: None)
_stub_if_import_fails("docx.oxml.ns", nsdecls=lambda *args, **kwargs: {})
try:
    import PIL  # noqa: F401
except ImportError:
    pil = _make_stub("PIL")
    pil.__path__ = []
    _make_stub("PIL.Image", open=None)

from kdb.mining.generation.processing.wordtotext import _extract_rendered_pdf_images


class FakePage:
    def get_text(self, mode=None):
        assert mode == "dict"
        return {
            "blocks": [
                {"type": 0, "text": "ignored"},
                {
                    "type": 1,
                    "image": b"rendered-image",
                    "ext": "png",
                    "bbox": [1.0, 2.0, 3.0, 4.0],
                    "width": 10,
                    "height": 20,
                },
            ]
        }


def test_extract_rendered_pdf_images_writes_only_image_blocks(tmp_path):
    items = _extract_rendered_pdf_images(FakePage(), 7, str(tmp_path))

    assert len(items) == 1
    item = items[0]
    assert item["type"] == "image"
    assert item["image_source"] == "rendered_block"
    assert item["image_width"] == 10
    assert item["image_height"] == 20
    assert os.path.basename(item["image_path"]) == "7_0.png"
    with open(item["image_path"], "rb") as image_file:
        assert image_file.read() == b"rendered-image"


def test_image_only_pdf_renders_pages_omitted_by_image_blocks(tmp_path, monkeypatch):
    import json
    from kdb.mining.generation.processing import wordtotext

    class Pixmap:
        width, height = 1920, 1080

        def tobytes(self, fmt):
            assert fmt == "png"
            return b"visible-slide"

    class Page:
        def get_text(self, mode=None):
            return {"blocks": []} if mode == "dict" else ""

        def get_pixmap(self, **kwargs):
            return Pixmap()

    class Pdf:
        def __len__(self):
            return 2

        def __getitem__(self, index):
            return Page()

        def close(self):
            pass

    monkeypatch.setattr(wordtotext.fitz, "open", lambda _: Pdf(), raising=False)
    monkeypatch.setattr(wordtotext.fitz, "Matrix", lambda *args: args, raising=False)
    result = json.loads(wordtotext.parse_pdf_to_json("slides.pdf", str(tmp_path)))
    assert set(result) == {"1", "2"}
    assert all(items[0]["image_source"] == "rendered_page" for items in result.values())
    assert (tmp_path / "2_0.png").read_bytes() == b"visible-slide"
