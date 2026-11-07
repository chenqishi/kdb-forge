from kdb.mining.pipelines.html_qa_segment import HtmlKgGenTaskController


class _StatusUpdater:
    def __init__(self):
        self.stages = []

    def update_task_stage(self, task_id, stage):
        self.stages.append((task_id, stage))


def test_skip_multimodal_keeps_firecrawl_mapping(tmp_path):
    source = tmp_path / "processed.txt"
    source.write_text("row\n", encoding="utf-8")
    controller = HtmlKgGenTaskController.__new__(HtmlKgGenTaskController)
    controller.task_id = "text-only"
    controller.status_updater = _StatusUpdater()
    controller.processed_result_file = str(source)
    controller.skip_multimodal = True
    controller.is_use_firecrawl = True

    assert controller.stage_3_multimodal_process() is True
    assert controller.processed_result_file == str(source)
    assert controller.status_updater.stages == [("text-only", "multimodal_process")]


def test_text_only_stages_read_firecrawl_content_when_untranslated(
    tmp_path, monkeypatch
):
    source = tmp_path / "processed.txt"
    translated = tmp_path / "translated.txt"
    qa_result = tmp_path / "qa.txt"
    segment_result = tmp_path / "segment.txt"
    source.write_text("row\n", encoding="utf-8")
    translated.write_text("row\n", encoding="utf-8")

    controller = HtmlKgGenTaskController.__new__(HtmlKgGenTaskController)
    controller.task_id = "text-only"
    controller.status_updater = _StatusUpdater()
    controller.script_dir = str(tmp_path)
    controller.log_dir = str(tmp_path)
    controller.processed_result_file = str(source)
    controller.translated_result_file = str(translated)
    controller.qa_result_file = str(qa_result)
    controller.segment_knowledge_file_path = str(segment_result)
    controller.skip_multimodal = True
    controller.is_use_firecrawl = True
    controller.is_need_translated = True
    monkeypatch.setattr(controller, "_qa_context_cli_args", lambda: "")

    commands = []

    def run_command(command, stage):
        commands.append((stage, command))
        if stage == "translate":
            translated.write_text("row\n", encoding="utf-8")
        if stage == "qa_generation":
            qa_result.write_text("row\n", encoding="utf-8")
        if stage == "segment_generation":
            segment_result.write_text("row\n", encoding="utf-8")
        return True

    monkeypatch.setattr(controller, "_run_command", run_command)

    assert controller.stage_4_translate_documents() is True
    controller.is_need_translated = False
    assert controller.stage_5_generate_qa() is True
    assert controller.stage_9_generate_segment() is True
    assert all("firecrawl_content" in command for _, command in commands)
    assert all(
        "content_with_multimodal_unsderstanding" not in command
        for _, command in commands
    )
