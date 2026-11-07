import json

from control_service.html_kg_gen_task_control import HtmlKgGenTaskController
from knowledge_interface_tools import search_index_data_interface as search_module


def test_insert_data_cli_override_disables_only_llm(monkeypatch, tmp_path):
    data_file = tmp_path / "data.jsonl"
    data_file.write_text(json.dumps({"title": "q", "content": "a"}) + "\n")
    calls = []

    class FakeSearchDataInterface:
        def __init__(self, **kwargs):
            pass

        def insert_data(self, data, **kwargs):
            calls.append(kwargs)
            data["_id"] = "test-id"
            return True, "ok"

    monkeypatch.setattr(search_module, "SearchDataInterface", FakeSearchDataInterface)

    result = search_module.insert_data_to_search_index(
        str(data_file),
        "unused.json",
        index_name_assign="mercado_local",
        check_duplicate=True,
        is_need_llm="false",
    )

    assert result["insert_success_num"] == 1
    assert calls == [{
        "index_name": "mercado_local",
        "check_duplicate": True,
        "is_need_llm": False,
        "is_update_data": False,
        "is_only_title": False,
        "basic_threshold": 0.7,
        "title_basic_threshold": 0.95,
    }]


def _controller_for_insert(tmp_path, value, check_duplicate=None):
    controller = HtmlKgGenTaskController.__new__(HtmlKgGenTaskController)
    controller.search_data_file_path = str(tmp_path / "qa.jsonl")
    controller.segment_search_data_file_path = str(tmp_path / "segment.jsonl")
    controller.index_name = "mercado_local"
    controller.script_dir = "/repo"
    controller.insert_is_need_llm = value
    controller.insert_check_duplicate = check_duplicate
    controller.status_updater = type(
        "Updater", (), {"update_task_stage": lambda self, *args: None}
    )()
    controller.task_id = "task-id"
    controller._get_index_config_path = lambda: "/repo/config/search.json"
    return controller


def test_html_insert_stages_pass_task_level_dedup_overrides(tmp_path):
    controller = _controller_for_insert(tmp_path, False, False)
    (tmp_path / "segment.jsonl").write_text("{}\n")
    commands = []
    controller._run_command = lambda cmd, stage: commands.append((cmd, stage)) or True

    assert controller.stage_8_insert_index() is True
    assert controller.stage_11_insert_segment_index() is True
    assert len(commands) == 2
    assert all("--is_need_llm=false" in command for command, _ in commands)
    assert all("--check_duplicate=false" in command for command, _ in commands)


def test_html_insert_stages_preserve_config_default_when_override_missing(tmp_path):
    controller = _controller_for_insert(tmp_path, None)
    commands = []
    controller._run_command = lambda cmd, stage: commands.append(cmd) or True

    assert controller.stage_8_insert_index() is True
    assert "--is_need_llm" not in commands[0]
    assert "--check_duplicate" not in commands[0]
