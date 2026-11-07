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


try:
    __import__("kdb.shared.text.common_utils")
except Exception:
    _make_stub(
        "kdb.shared.text.common_utils",
        count_alaph_char=lambda text: len(str(text).split()),
        count_chinese_char=lambda text: sum(1 for char in str(text) if "\u4e00" <= char <= "\u9fff"),
    )
try:
    __import__("kdb.shared.text.text_utils")
except Exception:
    _make_stub(
        "kdb.shared.text.text_utils",
        cluster_by_edit_distance=lambda words, **kwargs: ([], len(set(words))),
        construct_multimodel_undestanding_content=lambda content, results: content,
    )
_stub_if_import_fails("kdb.shared.clients.dify_tools", DIfyWorkFlowMlutiVisionRequest=object)
_stub_if_import_fails("kdb.integrations.data_control.minio_tools", MinioTools=object)

from kdb.mining.parsing.multimodal_process import MultimodalProcess


def test_repeated_image_hash_blacklist_skips_before_ocr(tmp_path):
    duplicate_paths = []
    for index in range(11):
        path = tmp_path / f"duplicate_{index}.png"
        path.write_bytes(b"same-image-content")
        duplicate_paths.append(str(path))

    unique_path = tmp_path / "unique.png"
    unique_path.write_bytes(b"unique-image-content")

    payload = {
        "1": [{"type": "image", "image_path": path} for path in duplicate_paths],
        "2": [{"type": "image", "image_path": str(unique_path)}],
    }
    processor = MultimodalProcess(
        {
            "enable_upload": False,
            "enable_image_ocr": True,
            "enable_image_understanding": True,
            "enable_image_hash_blacklist": True,
            "image_hash_blacklist_threshold": 10,
        }
    )

    processor.prepare_image_hash_blacklist(payload)
    result = processor.process_one_data({"type": "image", "image_path": duplicate_paths[0]})

    assert len(processor.image_hash_blacklist) == 1
    assert result["is_hash_blacklisted"] is True
    assert result["image_hash_occurrence_count"] == 11
    assert result["public_url"] is None
    assert result["image_ocr"] is None
    assert result["image_understanding"] is None


def test_text_rich_page_uses_ocr_without_second_description(monkeypatch):
    processor = MultimodalProcess({"enable_upload": False})
    monkeypatch.setattr(processor, "_is_valid_image", lambda *a, **kw: True)
    monkeypatch.setattr(processor, "_image_ocr", lambda *a: "招商入驻要求" * 50)
    monkeypatch.setattr(processor, "_is_valid_image_by_ocr", lambda *a, **kw: (True, "rich"))
    descriptions = []
    monkeypatch.setattr(processor, "_image_understanding", lambda *a, **kw: descriptions.append(a))
    item = {"type": "image", "image_path": "/slide.png",
            "public_url": "https://example.com/slide.png", "image_source": "rendered_page"}
    result = processor.process_one_data(item)
    assert result["is_valid"] and result["image_ocr"]
    assert not descriptions
    processor.process_one_data(dict(item, image_source="rendered_block"))
    assert len(descriptions) == 1


def test_page_table_is_kept_despite_repeated_ocr_labels(monkeypatch):
    processor = MultimodalProcess({"enable_upload": False})
    monkeypatch.setattr(processor, "_is_valid_image", lambda *a, **kw: True)
    monkeypatch.setattr(processor, "_image_ocr", lambda *a: "海外仓\n半托管\n" * 40)
    monkeypatch.setattr(processor, "_is_valid_image_by_ocr", lambda *a, **kw: (False, "repeated"))
    monkeypatch.setattr(processor, "_image_understanding", lambda *a, **kw: None)
    item = {"type": "image", "image_path": "/slide.png",
            "public_url": "https://example.com/slide.png", "image_source": "rendered_page"}
    assert processor.process_one_data(item)["is_valid"]
    assert not processor.process_one_data(dict(item, image_source="rendered_block"))["is_valid"]
