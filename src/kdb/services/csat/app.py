from kdb.shared.config.paths import source_path as _source_path
from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
CSAT 满意度报告服务

启动方式：
    python single_service/csat_report_service.py \
        --mysql-config config/mysql_conn_config.json \
        --auth-config  config/csat_auth_config.json \
        [--port 7000]

接口：POST /csat_report
    Body JSON: { "start_time": "YYYY-MM-DD HH:MM:SS",
                 "end_time":   "YYYY-MM-DD HH:MM:SS",
                 "channel_type": "<渠道类型>",
                 "client":     "<租户标识>",
                 "signature":  "<md5(secret+timestamp)>",
                 "timestamp":  <unix秒级时间戳> }
"""
import argparse
import hashlib
import json
import logging
import os
import sys
import time

from flask import Flask, request, Response

# 将项目根目录加入 sys.path，以便引用 commons 等包

from kdb.shared.clients.mysql_connector import MySQLConnector
from kdb.reporting.csat.csat_data_query import query_csat_sessions
from kdb.reporting.csat.user_id_map_query import query_user_id_map

app = Flask(__name__, root_path=str(_source_path('kdb', 'services', 'csat')))

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] [%(asctime)s] [%(name)s] [%(filename)s:%(lineno)d]: %(message)s'
)

mysql_connector: MySQLConnector = None
client_secrets: dict = {}


def json_response(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False),
        status=status,
        mimetype='application/json'
    )


def verify_signature(client, signature, timestamp, secrets):
    """
    签名鉴权。

    Args:
        client:    租户标识
        signature: 客户端提交的签名（md5(secret+timestamp) hex）
        timestamp: 客户端提交的 Unix 时间戳（秒级，int 或 str）
        secrets:   {client: secret} 映射

    Returns:
        (ok: bool, errmsg: str)
    """
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False, 'invalid timestamp'

    if abs(time.time() - ts) > 300:
        return False, 'timestamp expired'

    if client not in secrets:
        return False, 'unknown client'

    secret = secrets[client]
    expected = hashlib.md5(f'{secret}{ts}'.encode('utf-8')).hexdigest()
    if signature != expected:
        return False, 'invalid signature'

    return True, ''


@app.route('/csat_report', methods=['POST'], strict_slashes=False)
def get_csat_report():
    body = request.get_json(silent=True) or {}

    client = body.get('client')
    signature = body.get('signature')
    timestamp = body.get('timestamp')

    if not all([client, signature, timestamp]):
        return json_response({'code': 1, 'message': 'client, signature, timestamp 均为必填项'}, 400)

    ok, errmsg = verify_signature(client, signature, timestamp, client_secrets)
    if not ok:
        return json_response({'code': 401, 'message': errmsg}, 401)

    return _parse_and_query(body)


def _parse_and_query(body):
    """提取公共参数并执行查询，供两个接口复用。"""
    start_time = body.get('start_time')
    end_time = body.get('end_time')
    channel_type = body.get('channel_type')
    client = body.get('client')
    if not all([start_time, end_time, channel_type, client]):
        return json_response({'code': 1, 'message': 'start_time, end_time, channel_type, client 均为必填项'}, 400)
    include_chat_detail = bool(body.get('include_chat_detail', False))
    try:
        records = query_csat_sessions(mysql_connector, start_time, end_time, channel_type, client, include_chat_detail)
        return json_response({'code': 0, 'message': 'success', 'data': records})
    except Exception as e:
        logging.exception('查询失败')
        return json_response({'code': 1, 'message': str(e)}, 500)


@app.route('/inner_csat_report', methods=['POST'], strict_slashes=False)
def inner_get_csat_report():
    """内部接口，无需签名鉴权，仅供内网调试使用。"""
    body = request.get_json(silent=True) or {}
    return _parse_and_query(body)


@app.route('/inner_external_user_id_map', methods=['POST'], strict_slashes=False)
def inner_user_id_map():
    """查询用户 cid / email / external_id 映射，无需鉴权。"""
    body = request.get_json(silent=True) or {}
    client = body.get('client')
    start_time = body.get('start_time')
    end_time = body.get('end_time')
    if not all([client, start_time, end_time]):
        return json_response({'code': 1, 'message': 'client, start_time, end_time 均为必填项'}, 400)
    user_id = body.get('user_id') or None
    try:
        records = query_user_id_map(mysql_connector, client, start_time, end_time, user_id)
        return json_response({'code': 0, 'message': 'success', 'data': records})
    except Exception as e:
        logging.exception('查询失败')
        return json_response({'code': 1, 'message': str(e)}, 500)


def main():
    parser = argparse.ArgumentParser(description='CSAT 满意度报告服务')
    parser.add_argument('--mysql-config', required=True, help='MySQL 配置文件路径')
    parser.add_argument('--auth-config', required=True, help='鉴权配置文件路径（JSON，{"client": "secret"}）')
    parser.add_argument('--port', type=int, default=7000, help='服务端口（默认 7000）')
    args = parser.parse_args()

    global mysql_connector, client_secrets
    mysql_connector = MySQLConnector(args.mysql_config)

    with open(args.auth_config, 'r', encoding='utf-8') as f:
        client_secrets = json.load(f)
    logging.info(f'已加载鉴权配置，clients: {list(client_secrets.keys())}')

    logging.info(f'CSAT 报告服务启动，端口: {args.port}')
    app.run(host='0.0.0.0', port=args.port)


if __name__ == '__main__':
    main()
