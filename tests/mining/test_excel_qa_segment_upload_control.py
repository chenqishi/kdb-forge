from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
import json
import os
import sys
import types
import pytest
from types import SimpleNamespace


from openpyxl import Workbook

from kdb.mining.document.pipelines.excel import ExcelQASegmentUploadController


class _StatusUpdaterStub:
    def __init__(self):
        self.stages = []

    def update_task_stage(self, task_id, stage):
        self.stages.append((task_id, stage))


def _make_controller(tmp_path):
    controller = ExcelQASegmentUploadController.__new__(ExcelQASegmentUploadController)
    controller.script_dir = str(_PROJECT_ROOT)
    controller.task_id = "task with spaces"
    controller.task_info = {}
    controller.data_dir = str(tmp_path)
    controller.log_dir = str(tmp_path / "logs")
    controller.downloaded_excel_path = str(tmp_path / "FBA FAQ SU Facing.xlsx.xlsx")
    controller.json_file_path = str(tmp_path / "audit output.jsonl")
    controller.image_processed_json_file_path = str(tmp_path / "audit image output.jsonl")
    controller.index_input_file_path = controller.json_file_path
    controller.excel_classification = {}
    controller.excel_process_mode = None
    controller.document_fallback_completed = False
    controller.status_updater = _StatusUpdaterStub()
    os.makedirs(controller.log_dir, exist_ok=True)
    return controller


def _make_xlsx(path, headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)


@pytest.mark.requires_process
def test_run_command_list_preserves_space_containing_argument(tmp_path):
    controller = _make_controller(tmp_path)
    output_file = tmp_path / "argv.json"
    spaced_arg = str(tmp_path / "file name with spaces.xlsx")

    cmd = [
        sys.executable,
        "-c",
        "import json, sys; open(sys.argv[2], 'w', encoding='utf-8').write(json.dumps(sys.argv[1], ensure_ascii=False))",
        spaced_arg,
        str(output_file),
    ]

    assert controller._run_command(cmd, "argv_check")
    assert json.loads(output_file.read_text(encoding="utf-8")) == spaced_arg


def test_stage_2_excel_to_json_uses_argument_list_for_space_paths(tmp_path):
    controller = _make_controller(tmp_path)
    controller.task_info = {
        "category_name": "默认分组",
        "category_id": 1,
        "client": "wayfair",
        "index_name": "wayfair",
    }
    _make_xlsx(
        controller.downloaded_excel_path,
        ["title", "content"],
        [["How?", "Like this"]],
    )
    captured = {}

    def fake_run_command(cmd, stage_name):
        captured["cmd"] = cmd
        captured["stage_name"] = stage_name
        with open(controller.json_file_path, "w", encoding="utf-8") as f:
            f.write('{"title": "ok"}\n')
        return True

    controller._run_command = fake_run_command

    assert controller.stage_2_excel_to_json()
    assert captured["stage_name"] == "excel_to_json"
    assert isinstance(captured["cmd"], list)
    assert f"--excel_file={controller.downloaded_excel_path}" in captured["cmd"]
    assert any(arg.startswith("--extra_field_name_dict=") for arg in captured["cmd"])
    assert controller.excel_process_mode == "standard_qa"
    assert controller.status_updater.stages == [(controller.task_id, "excel_to_json")]


def test_stage_2_mapped_excel_routes_to_structured_json(tmp_path):
    controller = _make_controller(tmp_path)
    _make_xlsx(
        controller.downloaded_excel_path,
        ["问题", "答案", "检索词"],
        [["怎么退货", "进入订单申请退货", "退货|退款"]],
    )
    captured = {}

    def fake_run_command(cmd, stage_name):
        captured["cmd"] = cmd
        with open(controller.json_file_path, "w", encoding="utf-8") as f:
            f.write('{"title": "怎么退货", "content": "进入订单申请退货"}\n')
        return True

    controller._run_command = fake_run_command

    assert controller.stage_2_excel_to_json()
    assert controller.excel_process_mode == "mapped_qa"
    assert captured["cmd"][0] == sys.executable
    assert controller.index_input_file_path == controller.json_file_path


def test_stage_2_unstructured_excel_falls_back_to_document_flow(tmp_path):
    controller = _make_controller(tmp_path)
    _make_xlsx(
        controller.downloaded_excel_path,
        ["Topic details", "CAN team answer/feedback"],
        [["Anti-dumping", "Answer"]],
    )
    called = {}

    def fake_fallback():
        called["fallback"] = True
        return True

    controller._run_unstructured_document_fallback = fake_fallback

    assert controller.stage_2_excel_to_json()
    assert called["fallback"]
    assert controller.excel_process_mode == "unstructured_excel"
    assert controller.document_fallback_completed


def test_stage_2_5_image_process_skips_without_images(tmp_path):
    controller = _make_controller(tmp_path)
    controller.excel_process_mode = "standard_qa"
    with open(controller.json_file_path, "w", encoding="utf-8") as f:
        f.write('{"title": "q", "content": "a"}\n')

    assert controller.stage_2_5_process_images()
    assert controller.index_input_file_path == controller.json_file_path


def test_stage_2_5_image_process_writes_processed_output(tmp_path, monkeypatch):
    controller = _make_controller(tmp_path)
    controller.excel_process_mode = "standard_qa"
    image_path = str(tmp_path / "image file.png")
    with open(controller.json_file_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"title": "q", "content": "a", "ori_image_path": [image_path]}, ensure_ascii=False) + "\n")

    captured = {}

    def fake_run(cmd, shell, stdout, stderr, text, cwd, env):
        captured["cmd"] = cmd
        captured["shell"] = shell
        assert str(_PROJECT_ROOT / "src") in env["PYTHONPATH"].split(os.pathsep)
        stdout.write('{"title": "q", "content": "a", "image_indexes": [{"text": "img"}]}\n')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("kdb.mining.document.workflows.excel.stages.subprocess.run", fake_run)

    assert controller.stage_2_5_process_images()
    assert captured["shell"] is False
    assert captured["cmd"][0] == sys.executable
    assert controller.index_input_file_path == controller.image_processed_json_file_path
    assert os.path.exists(controller.image_processed_json_file_path)
