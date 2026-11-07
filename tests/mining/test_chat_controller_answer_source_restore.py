from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""Chat QA controller 恢复后的阶段契约。"""
import json
import os
import sys


ROOT = str(_PROJECT_ROOT)

from kdb.mining.pipelines import chat_qa as controller_module
from kdb.mining.pipelines.chat_qa import ChatQAMiningTaskController


class _StatusUpdater:
    def __init__(self):
        self.stages = []

    def update_task_stage(self, task_id, stage):
        self.stages.append((task_id, stage))


def _controller():
    controller = ChatQAMiningTaskController.__new__(ChatQAMiningTaskController)
    controller.script_dir = '/srv/knowledge_database_builder'
    controller.task_id = 'task-restore'
    controller.qa_file_path = '/tmp/extract_batch.txt'
    controller.qa_quality_file_path = '/tmp/quality_batch.txt'
    controller.search_data_file_path = '/tmp/search_data.txt'
    controller.llm_stats_file_path = '/tmp/llm_call_stats.json'
    controller.review_stats_file_path = '/tmp/qa_review_stats.json'
    controller.insert_result_file_path = '/tmp/qa_insert_result.json'
    controller.category_id = None
    controller.category_name = None
    controller.client = 'mercado'
    controller.status_updater = _StatusUpdater()
    return controller


def test_quality_stage_runs_independent_review_model():
    controller = _controller()
    commands = []
    controller._run_command = lambda cmd, stage: commands.append((cmd, stage)) or True

    assert controller.stage_3_qa_quality() is True

    cmd, stage = commands[0]
    assert stage == 'qa_quality'
    assert '-m kdb.mining.quality.chat_qa_extract.reviewer review_batch' in cmd
    assert '--client=mercado' in cmd
    assert '--stats_file=/tmp/qa_review_stats.json' in cmd
    assert controller.status_updater.stages == [('task-restore', 'qa_quality')]


def test_schema_stage_preserves_task_id_contract():
    controller = _controller()
    commands = []
    controller._run_command = lambda cmd, stage: commands.append((cmd, stage)) or True

    assert controller.stage_4_schema_transform() is True

    cmd, stage = commands[0]
    assert stage == 'schema_transform'
    assert '--task-id=task-restore' in cmd
    assert '--field_num=5' in cmd


def test_schema_stage_carries_explicit_category_contract():
    controller = _controller()
    controller.category_id = '2084870960369385473'
    controller.category_name = 'Bol'
    commands = []
    controller._run_command = lambda cmd, stage: commands.append((cmd, stage)) or True

    assert controller.stage_4_schema_transform() is True

    cmd, _ = commands[0]
    assert '--category_id=2084870960369385473' in cmd
    assert '--category_name=Bol' in cmd


def test_generation_stage_requests_machine_readable_llm_stats(tmp_path):
    controller = _controller()
    controller.data_dir = str(tmp_path)
    controller.qa_file_path = str(tmp_path / 'extract_batch.txt')
    controller.robot_data_map_file_path = str(tmp_path / 'robot_map.txt')
    controller.robot_room_type_config_path = str(tmp_path / 'room_config.txt')
    controller.robot_room_process_record_path = str(tmp_path / 'process_record.txt')
    controller.robot_room_white_name_path = str(tmp_path / 'white_list.txt')
    controller.prompt_file_map_path = str(tmp_path / 'prompt_map.txt')
    controller.llm_stats_file_path = str(tmp_path / 'llm_call_stats.json')
    commands = []

    def fake_run(cmd, stage):
        commands.append((cmd, stage))
        open(controller.qa_file_path, 'w', encoding='utf8').close()
        return True

    controller._run_command = fake_run

    assert controller.stage_2_generate_qa() is True
    cmd, stage = commands[0]
    assert stage == 'qa_generation'
    assert '--llm_stats_file=%s' % controller.llm_stats_file_path in cmd


def test_task_qa_num_is_real_insert_success_count(tmp_path):
    controller = _controller()
    controller.search_data_file_path = str(tmp_path / 'search.jsonl')
    controller.llm_stats_file_path = str(tmp_path / 'extract_stats.json')
    controller.review_stats_file_path = str(tmp_path / 'review_stats.json')
    controller.insert_result_file_path = str(tmp_path / 'insert_stats.json')
    rows = [
        {'data_type': 'qa', 'quality_level': 'high', 'review_decision': 'accept'},
        {'data_type': 'qa', 'quality_level': 'high', 'review_decision': 'accept'},
        {'data_type': 'qa', 'quality_level': 'mid', 'review_decision': 'review'},
        {'data_type': 'qa', 'quality_level': 'low', 'review_decision': 'reject'},
    ]
    with open(controller.search_data_file_path, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')
    (tmp_path / 'review_stats.json').write_text(
        json.dumps({'extracted_candidate_num': 4}), encoding='utf-8'
    )
    (tmp_path / 'insert_stats.json').write_text(json.dumps({
        'insert_attempt_num': 2,
        'insert_success_num': 1,
        'duplicate_skip_num': 1,
        'gate_skip_num': 2,
        'insert_failure_num': 0,
    }), encoding='utf-8')

    result = controller.count_qa_results()

    assert result['qa_num'] == 1
    assert result['high_candidate_num'] == 2
    assert result['review_accept_num'] == 2
    assert result['insert_success_num'] == 1
    assert result['duplicate_skip_num'] == 1
    assert result['gate_skip_num'] == 2
    assert result['metrics_complete'] is True


def test_command_uses_remaining_task_deadline(monkeypatch, tmp_path):
    controller = ChatQAMiningTaskController.__new__(ChatQAMiningTaskController)
    controller.script_dir = str(tmp_path)
    controller.config_dir = str(tmp_path)
    controller.log_dir = str(tmp_path)
    controller.task_timeout_seconds = 60
    controller.task_started_monotonic = 100.0
    monkeypatch.setattr(controller_module.time, 'monotonic', lambda: 110.0)
    calls = []

    class FakeProcess:
        pid = 123
        returncode = 0

        def __init__(self, cmd, **kwargs):
            calls.append((cmd, kwargs, []))

        def wait(self, timeout=None):
            calls[0][2].append(timeout)
            return self.returncode

    monkeypatch.setattr(controller_module.subprocess, 'Popen', FakeProcess)

    assert controller._run_command('true', 'deadline_test') is True
    assert calls[0][2] == [50.0]
