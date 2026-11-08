from collections import Counter
from collections import defaultdict
from datetime import datetime
from kdb.shared.clients.channel_communicate_by_request import ChannelRequestCommunicate
from kdb.shared.database.mysql import MySQLConnector
import json
import logging
import os

TASK_TYPE = 'chat_qa_mining'


SEARCH_DATA_FILE = 'chatknowledege_extract_qa_quality_batch_search_data.txt'


def parse_time(value):
    if not value:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y%m%d%H%M%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError('无法识别时间格式: %s' % value)


def format_dt(value):
    return value.strftime('%Y-%m-%d %H:%M:%S')


def load_recipients(report_config):
    recipients = []
    seen = set()
    with open(report_config, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) < 3:
                logging.warning('忽略无法解析的日报接收配置: %s', line)
                continue
            _, receiver, send_url = parts[:3]
            key = (receiver.strip(), send_url.strip())
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            recipients.append(key)
    return recipients


def query_tasks(mysql_config, start_time, end_time):
    connector = MySQLConnector(mysql_config)
    connection = connector.get_connection()
    if connection is None:
        raise RuntimeError('无法连接 MySQL')
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT task_id, task_type, client, user, task_stage, run_status,
                   create_time, update_time, task_result
            FROM rufitai.dops_task_kggen_info
            WHERE task_type = %s
              AND update_time >= %s
              AND update_time < %s
            ORDER BY update_time ASC
            """,
            (TASK_TYPE, start_time, end_time),
        )
        return cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        connection.close()


def parse_task_result(raw_value):
    if not raw_value:
        return {}
    try:
        return json.loads(raw_value)
    except Exception:
        return {}


def read_search_data(data_dir, task):
    path = os.path.join(data_dir, task['task_id'], SEARCH_DATA_FILE)
    rows = []
    if not os.path.exists(path):
        return rows, path, 'missing'

    with open(path, encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                logging.warning('跳过无法解析的 search data: task_id=%s line=%s', task['task_id'], line_num)
    return rows, path, ''


def new_client_bucket():
    return {
        'qa_total': 0,
        'high': 0,
        'mid': 0,
        'low': 0,
        'qualified': 0,
        'pending_audit': 0,
        'approved': 0,
        'rejected': 0,
        'tasks': 0,
        'users': Counter(),
    }


def summarize_tasks(tasks, data_dir):
    summary = {
        'tasks_total': len(tasks),
        'tasks_completed': 0,
        'tasks_failed': 0,
        'tasks_running_or_other': 0,
        'missing_output_tasks': [],
        'client_stats': defaultdict(new_client_bucket),
        'client_zero_tasks': defaultdict(int),
        'client_task_results': defaultdict(int),
        'client_mismatch_rows': [],
    }

    for task in tasks:
        client = str(task.get('client') or 'unknown').strip() or 'unknown'
        user = str(task.get('user') or 'unknown').strip() or 'unknown'
        run_status = task.get('run_status')
        task_result = parse_task_result(task.get('task_result'))
        summary['client_task_results'][client] += int(task_result.get('qa_num') or 0)

        if run_status == 3:
            summary['tasks_completed'] += 1
        elif run_status == 1:
            summary['tasks_failed'] += 1
        else:
            summary['tasks_running_or_other'] += 1

        if run_status != 3:
            continue

        rows, path, output_status = read_search_data(data_dir, task)
        if output_status == 'missing':
            summary['missing_output_tasks'].append((task['task_id'], client, user, path))
            summary['client_zero_tasks'][client] += 1
            continue

        bucket = summary['client_stats'][client]
        bucket['tasks'] += 1
        bucket['users'][user] += 1

        task_qa_total = 0
        for row in rows:
            row_client = str(row.get('client') or (row.get('ext_info') or {}).get('client') or client).strip() or client
            if row_client != client:
                summary['client_mismatch_rows'].append((task['task_id'], client, row_client, row.get('title') or ''))
                continue

            if row.get('data_type') != 'qa':
                continue

            task_qa_total += 1
            bucket['qa_total'] += 1
            quality_level = str(row.get('quality_level') or '').lower()
            if quality_level in ('high', 'mid', 'low'):
                bucket[quality_level] += 1

            ext_info = row.get('ext_info') or {}
            if ext_info.get('is_qualified') is True:
                bucket['qualified'] += 1

            audit_result = row.get('audit_result')
            if audit_result == -1:
                bucket['pending_audit'] += 1
            elif audit_result == 1:
                bucket['approved'] += 1
            elif audit_result == 0:
                bucket['rejected'] += 1

        if task_qa_total == 0:
            summary['client_zero_tasks'][client] += 1

    return summary


def build_report(summary, start_time, end_time):
    client_stats = summary['client_stats']
    total_qa = sum(v['qa_total'] for v in client_stats.values())
    total_high = sum(v['high'] for v in client_stats.values())
    total_mid = sum(v['mid'] for v in client_stats.values())
    total_low = sum(v['low'] for v in client_stats.values())
    total_pending = sum(v['pending_audit'] for v in client_stats.values())
    total_qualified = sum(v['qualified'] for v in client_stats.values())

    lines = [
        '聊天 QA 学习日报',
        '统计窗口：%s ~ %s' % (format_dt(start_time), format_dt(end_time)),
        '',
        '结论：过去 24 小时完成 %d 个聊天 QA 任务，新增 QA %d 条；high %d / mid %d / low %d，待审核 %d 条。'
        % (
            summary['tasks_completed'],
            total_qa,
            total_high,
            total_mid,
            total_low,
            total_pending,
        ),
        '',
        '📊 客户分布',
    ]

    if not client_stats:
        lines.append('- 无新增 QA。')
    else:
        sorted_clients = sorted(
            client_stats.items(),
            key=lambda item: (-item[1]['qa_total'], item[0]),
        )
        for client, stat in sorted_clients:
            top_users = ', '.join('%s×%d' % (user, count) for user, count in stat['users'].most_common(3))
            if not top_users:
                top_users = '无'
            lines.append(
                '- %s：新增 %d 条；high %d / mid %d / low %d；is_qualified %d；待审核 %d；任务 %d；来源 %s'
                % (
                    client,
                    stat['qa_total'],
                    stat['high'],
                    stat['mid'],
                    stat['low'],
                    stat['qualified'],
                    stat['pending_audit'],
                    stat['tasks'],
                    top_users,
                )
            )

    zero_clients = sorted(summary['client_zero_tasks'].items())
    if zero_clients:
        lines.extend(['', '🧩 已跑但无新增 QA'])
        lines.append('- ' + '；'.join('%s %d 个任务' % item for item in zero_clients))

    if summary['tasks_failed'] or summary['tasks_running_or_other'] or summary['missing_output_tasks'] or summary['client_mismatch_rows']:
        lines.extend(['', '⚠️ 需要关注'])
        if summary['tasks_failed']:
            lines.append('- 失败任务：%d 个' % summary['tasks_failed'])
        if summary['tasks_running_or_other']:
            lines.append('- 未完成/其它状态任务：%d 个' % summary['tasks_running_or_other'])
        if summary['missing_output_tasks']:
            lines.append('- 完成但缺少 search data 文件：%d 个' % len(summary['missing_output_tasks']))
        if summary['client_mismatch_rows']:
            lines.append('- 发现 client 不一致行：%d 条，已从统计中剔除' % len(summary['client_mismatch_rows']))

    lines.extend([
        '',
        '🔍 口径',
        '- 统计任务表中 update_time 落在窗口内的 chat_qa_mining 任务。',
        '- QA 数量读取每个任务目录下的 %s；包括 high/mid/low，不把 mid 自动丢弃。' % SEARCH_DATA_FILE,
        '- task_result.qa_num 是历史高质量 QA 计数；本日报以实际 search data 行数作为“新增 QA”。',
    ])

    return '\n'.join(lines)


def send_report(message, recipients):
    results = []
    for receiver, send_url in recipients:
        is_group = False
        target = receiver
        if target.endswith(':group'):
            target = target[:-len(':group')]
            is_group = True
        sender = ChannelRequestCommunicate(base_url=send_url)
        ok, detail = sender.send_wx(message, target, is_group)
        results.append((receiver, send_url, ok, detail))
    return results


def write_report_file(message, output_path):
    if not output_path:
        return
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(message)
        f.write('\n')
