from datetime import datetime
from datetime import timedelta
from kdb.mining.tasks.reports.learning import build_report
from kdb.mining.tasks.reports.learning import load_recipients
from kdb.mining.tasks.reports.learning import parse_time
from kdb.mining.tasks.reports.learning import query_tasks
from kdb.mining.tasks.reports.learning import send_report
from kdb.mining.tasks.reports.learning import summarize_tasks
from kdb.mining.tasks.reports.learning import write_report_file
import argparse
import logging
import sys

def main():
    parser = argparse.ArgumentParser(description='聊天 QA 学习日报')
    parser.add_argument('--mysql-config', default='config/mysql_conn_config.json')
    parser.add_argument('--report-config', default='config/chatkonwledge_report_platform_map.txt')
    parser.add_argument('--data-dir', default='data/off_task_data')
    parser.add_argument('--start-time', default='')
    parser.add_argument('--end-time', default='')
    parser.add_argument('--window-hours', type=int, default=24)
    parser.add_argument('--report-output', default='log/chatqa_learning_daily_report_latest.txt')
    parser.add_argument('--strict-send', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] %(message)s',
    )

    end_time = parse_time(args.end_time) or datetime.now()
    start_time = parse_time(args.start_time) or (end_time - timedelta(hours=args.window_hours))

    tasks = query_tasks(args.mysql_config, start_time, end_time)
    summary = summarize_tasks(tasks, args.data_dir)
    message = build_report(summary, start_time, end_time)

    print(message)
    write_report_file(message, args.report_output)

    if args.dry_run:
        return

    recipients = load_recipients(args.report_config)
    if not recipients:
        raise RuntimeError('没有可用的日报接收人配置: %s' % args.report_config)

    results = send_report(message, recipients)
    failed = [r for r in results if not r[2]]
    for receiver, send_url, ok, detail in results:
        logging.info('send receiver=%s url=%s ok=%s detail=%s', receiver, send_url, ok, detail)
    if failed:
        logging.error('部分日报发送失败，不中断定时任务；报告已写入 %s: %s', args.report_output, failed)
        if args.strict_send:
            raise RuntimeError('部分日报发送失败: %s' % failed)


if __name__ == '__main__':
    main()
