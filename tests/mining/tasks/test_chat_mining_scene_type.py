from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""
`chat_mining_scene_type` 配置值的规范化行为。

关注点是"配置写错时不能静默放大挖掘范围"：下游 get_data_from_sql.py 只认 group/single
两个词，两个都不命中就不追加任何过滤条件，等于群聊单聊全挖。
"""
import os
import sys

import pytest



@pytest.fixture
def normalize():
    from kdb.mining.tasks.submission.chat_batch import BatchChatQARequestRunner

    runner = BatchChatQARequestRunner.__new__(BatchChatQARequestRunner)
    return lambda value: runner._normalize_scene_type(value, app_id='test_app')


@pytest.mark.parametrize('value', [None, '', '   '])
def test_missing_config_keeps_group_only(normalize, value):
    """没配置就维持历史行为：只挖群聊"""
    assert normalize(value) == 'group'


@pytest.mark.parametrize('value,expected', [
    ('group', 'group'),
    ('single', 'single'),
    ('group,single', 'group,single'),
])
def test_valid_values_pass_through(normalize, value, expected):
    assert normalize(value) == expected


@pytest.mark.parametrize('value', ['single,group', 'Group, Single', ' GROUP , single '])
def test_order_and_case_are_normalized(normalize, value):
    """顺序、大小写、空格不同都归一到同一个规范值"""
    assert normalize(value) == 'group,single'


@pytest.mark.parametrize('value', ['groups', 'all', 'both', 'group;single', '1'])
def test_invalid_values_fall_back_to_group(normalize, value):
    """写错的取值必须退回 group，绝不能变成"不过滤"""
    assert normalize(value) == 'group'


def test_enabled_apps_keep_inner_join_support_explicit_disabled_app_override_and_skip_missing_owner():
    from kdb.mining.tasks.submission.chat_batch import BatchChatQARequestRunner

    class FakeCursor:
        def __init__(self):
            self.sql = ''

        def execute(self, sql):
            self.sql = sql

        def fetchall(self):
            return [
                ('app-ok', 'mercado', 'robot-ok', 'single,group'),
                ('app-no-client', '', 'robot-2', 'group'),
                ('app-no-user', 'mercado', None, 'group'),
            ]

    class FakeConnector:
        def __init__(self):
            self.cursor = FakeCursor()

        def get_connection(self):
            connector = self

            class FakeConnection:
                def cursor(self):
                    return connector.cursor

            return FakeConnection()

        def close_connection(self, connection, cursor):
            return None

    runner = BatchChatQARequestRunner.__new__(BatchChatQARequestRunner)
    runner.mysql_connector = FakeConnector()

    apps = runner.get_enabled_appids()

    assert apps == [{
        'app_id': 'app-ok',
        'client': 'mercado',
        'user': 'robot-ok',
        'scene_type': 'group,single',
    }]
    assert 'INNER JOIN rufitai.rf_app_info' in runner.mysql_connector.cursor.sql
    assert 'LEFT JOIN rufitai.rf_app_info' not in runner.mysql_connector.cursor.sql
    assert 'IFNULL(ai.is_enabled, 1) = 1' in runner.mysql_connector.cursor.sql
    assert "allow_disabled.config_key = 'chat_mining_allow_disabled_app'" in runner.mysql_connector.cursor.sql
    assert "allow_disabled.config_value = '1'" in runner.mysql_connector.cursor.sql
