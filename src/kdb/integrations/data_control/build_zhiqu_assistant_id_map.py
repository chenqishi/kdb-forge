#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
一次性脚本：构建「rfwkt 企业微信助手账号 ↔ 致趣 employee_user_id」映射，落
config/zhiqu_assistant_id_map.json。

由人工触发，cron 不会调本脚本。仅当账号增减/改名时重跑。

匹配口径：
- rfwkt 侧取 we_com_corp_id 指定 corp 下 del_flag=0 的 account。
  默认 corp_id = 1970325020467087（美国国际销售深圳代表处）。
- 致趣侧从 contact/list 全量数据里聚合 user_owner，按 name 撞 rfwkt nick_name。
- 仅唯一命中(rfwkt nick_name 在致趣只对应一个 employee_user_id) 进入映射；
  其他情况报 warning 走人工核对。

Usage:
    python data_control_tools/build_zhiqu_assistant_id_map.py \
        [--client mercado] \
        [--corp-id 1970325020467087] \
        [--config config/mysql_conn_config.json] \
        [--cred-path config/zhiqu_credentials.json] \
        [--out config/zhiqu_assistant_id_map.json] \
        [--dry-run]
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('data_control_tools/build_zhiqu_assistant_id_map.py')
import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))
from commons.mysql_connector import MySQLConnector
from data_control_tools.zhiqu_contact_fetcher import ZhiquClient, build_clients

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
DEFAULT_MYSQL = os.path.join(BASE, 'config', 'mysql_conn_config.json')
DEFAULT_CRED = os.path.join(BASE, 'config', 'zhiqu_credentials.json')
DEFAULT_OUT = os.path.join(BASE, 'config', 'zhiqu_assistant_id_map.json')
DEFAULT_CORP = '1970325020467087'  # 美国国际销售深圳代表处
DEFAULT_CLIENT = 'mercado'


def load_rfwkt_accounts(cur, corp_id):
    """rfwkt 端某 corp 下未删除的 account 列表。"""
    cur.execute(
        """
        SELECT we_com_user_id, nick_name, we_com_mobile
        FROM rf_wkt_we_com_account
        WHERE we_com_corp_id = %s AND del_flag = 0
        ORDER BY nick_name
        """,
        (corp_id,),
    )
    return cur.fetchall()


def aggregate_zhiqu_owners(zhiqu_client, page_size=100):
    """致趣端：拉全量 contact，聚合 owner，返回 dict{name: set(employee_user_id)}。"""
    owners_by_name = {}
    page = 1
    total_page = None
    while True:
        data = zhiqu_client.list_contacts_page(page=page, page_size=page_size)
        items = data.get('list') or []
        page_meta = data.get('page') or {}
        if total_page is None:
            total_page = page_meta.get('totalPage')
            logging.info('[zhiqu] total contacts=%s totalPage=%s', page_meta.get('total'), total_page)
        for it in items:
            for o in it.get('user_owner') or []:
                name = o.get('name')
                uid = o.get('employee_user_id')
                if not name or not uid:
                    continue
                owners_by_name.setdefault(name, set()).add(uid)
        if page % 50 == 0:
            logging.info('[zhiqu] aggregated page %d/%s', page, total_page)
        if not items or total_page is None or page >= total_page:
            break
        page += 1
    return owners_by_name


def build_assistant_map(accounts, zhiqu_owners_by_name):
    """按 nick_name 撞，组装 assistants 列表 + warning。"""
    assistants = []
    warnings = []
    for acc in accounts:
        nick = acc['nick_name']
        uids = zhiqu_owners_by_name.get(nick)
        if not uids:
            warnings.append(f'未在致趣 owner 中找到 nick_name="{nick}" (rfwkt we_com_user_id={acc["we_com_user_id"]})')
            continue
        if len(uids) > 1:
            warnings.append(f'致趣 owner name="{nick}" 对应多个 employee_user_id={sorted(uids)}，跳过')
            continue
        assistants.append({
            'nick_name': nick,
            'rfwkt_we_com_user_id': acc['we_com_user_id'],
            'zhiqu_employee_user_id': next(iter(uids)),
        })
    return assistants, warnings


def main():
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s: %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', default=DEFAULT_CLIENT)
    parser.add_argument('--corp-id', default=DEFAULT_CORP)
    parser.add_argument('--config', default=DEFAULT_MYSQL)
    parser.add_argument('--cred-path', default=DEFAULT_CRED)
    parser.add_argument('--out', default=DEFAULT_OUT)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--from-dump',
                        help='可选：从本地 JSON 文件(致趣 contact list 全量 dump) 加载 owner，跳过 API 拉取')
    args = parser.parse_args()

    conn = MySQLConnector(args.config)
    c = conn.get_connection()
    cur = c.cursor(dictionary=True)
    try:
        accounts = load_rfwkt_accounts(cur, args.corp_id)
    finally:
        conn.close_connection(c, cur)
    logging.info('rfwkt corp=%s accounts=%d', args.corp_id, len(accounts))
    if not accounts:
        raise SystemExit(f'corp_id={args.corp_id} 下无存活 account')

    if args.from_dump:
        logging.info('从本地 dump 加载致趣 contact: %s', args.from_dump)
        with open(args.from_dump, 'r', encoding='utf-8') as f:
            items = json.load(f)
        owners_by_name = {}
        for it in items:
            for o in it.get('user_owner') or []:
                name, uid = o.get('name'), o.get('employee_user_id')
                if not name or not uid:
                    continue
                owners_by_name.setdefault(name, set()).add(uid)
        logging.info('dump 中 contact=%d, unique owner 名=%d', len(items), len(owners_by_name))
    else:
        zhiqu = build_clients(args.cred_path)
        if args.client not in zhiqu:
            raise SystemExit(f'zhiqu_credentials.json 无 client={args.client}')
        owners_by_name = aggregate_zhiqu_owners(zhiqu[args.client])
        logging.info('zhiqu unique owner 名: %d', len(owners_by_name))

    assistants, warnings = build_assistant_map(accounts, owners_by_name)

    # 装载现有文件（如有），用于增量合并：仅追加/更新本 client，不动其他
    existing = {}
    if os.path.exists(args.out):
        try:
            with open(args.out, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except Exception as e:
            logging.warning('读取现有 %s 失败，将整体覆盖：%s', args.out, e)
            existing = {}

    existing[args.client] = {
        'corp_id': args.corp_id,
        'assistants': assistants,
    }

    print()
    print('========== 建图结果 ==========')
    print(f'  client:   {args.client}')
    print(f'  corp_id:  {args.corp_id}')
    print(f'  命中:     {len(assistants)} / {len(accounts)}')
    for a in assistants:
        print(f'    {a["nick_name"]:<25}  rfwkt={a["rfwkt_we_com_user_id"]}  zhiqu={a["zhiqu_employee_user_id"]}')
    if warnings:
        print()
        print(f'========== {len(warnings)} 条 WARNING ==========')
        for w in warnings:
            print(' ', w)

    if args.dry_run:
        print('\n[dry-run] 不写文件')
        return

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f'\n已写出: {args.out}')


if __name__ == '__main__':
    main()
