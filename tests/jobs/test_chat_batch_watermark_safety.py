from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""定时批任务只为真实完成的 app 推进水位。"""
import os
import sys

import pytest


ROOT = str(_PROJECT_ROOT)

import kdb.jobs.chat_mining as batch_module
from kdb.jobs.chat_mining import BatchChatQARequestRunner


def test_failed_task_keeps_old_watermark(monkeypatch):
    runner = BatchChatQARequestRunner.__new__(BatchChatQARequestRunner)
    runner.running_tasks = {}
    apps = [
        {'app_id': 'app-ok', 'client': 'mercado', 'user': 'robot-ok', 'scene_type': 'group'},
        {'app_id': 'app-failed', 'client': 'wayfair', 'user': 'robot-failed', 'scene_type': 'group'},
    ]
    monkeypatch.setattr(runner, 'load_appid_records', lambda: {})
    monkeypatch.setattr(runner, 'get_enabled_appids', lambda: apps)
    monkeypatch.setattr(
        runner,
        'create_task_request',
        lambda app, records: {
            'client': app['client'],
            'user': app['user'],
            'end_time': '2026-08-03 18:00:00',
            'scene_type': app['scene_type'],
        },
    )
    monkeypatch.setattr(
        runner,
        'send_task_request',
        lambda task: 'task-ok' if task['client'] == 'mercado' else 'task-failed',
    )
    monkeypatch.setattr(
        runner,
        'wait_for_tasks_completion',
        lambda: {'task-ok': 3, 'task-failed': 1},
    )
    recorded = []
    monkeypatch.setattr(runner, 'update_appid_records', lambda values: recorded.append(values))

    with pytest.raises(RuntimeError, match='运行失败任务'):
        runner.run()

    assert recorded == [{'app-ok': '2026-08-03 18:00:00'}]


def test_launch_failure_does_not_advance_watermark(monkeypatch):
    runner = BatchChatQARequestRunner.__new__(BatchChatQARequestRunner)
    runner.running_tasks = {}
    app = {'app_id': 'app-failed', 'client': 'mercado', 'user': 'robot', 'scene_type': 'group'}
    monkeypatch.setattr(runner, 'load_appid_records', lambda: {})
    monkeypatch.setattr(runner, 'get_enabled_appids', lambda: [app])
    monkeypatch.setattr(runner, 'create_task_request', lambda app_info, records: app_info)
    monkeypatch.setattr(runner, 'send_task_request', lambda task: None)
    recorded = []
    monkeypatch.setattr(runner, 'update_appid_records', lambda values: recorded.append(values))

    with pytest.raises(RuntimeError, match='没有成功启动任何任务'):
        runner.run()

    assert recorded == []


def test_empty_enabled_app_query_fails_batch(monkeypatch):
    runner = BatchChatQARequestRunner.__new__(BatchChatQARequestRunner)
    runner.running_tasks = {}
    monkeypatch.setattr(runner, 'load_appid_records', lambda: {})
    monkeypatch.setattr(runner, 'get_enabled_appids', lambda: [])

    with pytest.raises(RuntimeError, match='启用 App 查询结果为空'):
        runner.run()


def test_status_poll_deadline_marks_running_tasks_failed(monkeypatch):
    runner = BatchChatQARequestRunner.__new__(BatchChatQARequestRunner)
    runner.running_tasks = {'task-stuck': {'app_id': 'app-stuck'}}
    runner.poll_timeout_seconds = 30
    runner.poll_interval_seconds = 10
    monkeypatch.setattr(runner, 'check_task_status', lambda task_id: (2, 'qa_generation'))

    monotonic_values = iter([100.0, 100.0, 130.0, 130.0])
    monkeypatch.setattr(batch_module.time, 'monotonic', lambda: next(monotonic_values))
    monkeypatch.setattr(batch_module.time, 'sleep', lambda seconds: None)

    assert runner.wait_for_tasks_completion() == {'task-stuck': 1}
    assert runner.running_tasks == {}
