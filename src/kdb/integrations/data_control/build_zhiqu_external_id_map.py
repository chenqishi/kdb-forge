from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
cron 主流程：致趣 wx_external_userid → 本系统 cid 映射，写 `data_scrm_id_map`
（type=`zhiqu_external_id`）。

桥接事实（已验证 2026-06-18）：
- rf_wkt_we_com_contact.we_com_contact_user_id（数字） ≡ data_scrm.cid
- 致趣 contact.user_owner.employee_user_id 通过 config/zhiqu_assistant_id_map.json
  与 rfwkt.we_com_user_id 一一映射（人工触发的一次性脚本生成，cron 不会重建）。

主流程：
  1. 加载 config/zhiqu_assistant_id_map.json（用 employee_user_id 防改名）
  2. 拉致趣全量 contact（--from-dump 可走本地 JSON 跳过 API）
  3. 对每条 contact：
     - 过滤 owner.employee_user_id ∈ 映射表 → 拿到 rfwkt we_com_user_id 集合（同账号 scope）
     - 用 (rfwkt_uid, contact.name) 查 rfwkt 外部好友 → 得到 we_com_contact_user_id（= data_scrm.cid）
     - 多 owner 时取所有 scope 的并集；
     - 候选 cid 0 → unmatched；1 → matched；≥2 → ambiguous（保守不写库）
  4. 差集 INSERT 到 data_scrm_id_map (cid, client, type=zhiqu_external_id, sid=wx_external_userid)
  5. 落 ambiguous / unmatched 日志，打印 stats

Usage:
    # dry-run 试算
    python data_control_tools/build_zhiqu_external_id_map.py --dry-run
    # 正式写库
    python data_control_tools/build_zhiqu_external_id_map.py
    # 复用本地 dump（开发/调试用）
    python data_control_tools/build_zhiqu_external_id_map.py --from-dump data/zhiqu/zhiqu_contacts_raw_mercado.json
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime

from kdb.shared.clients.mysql_connector import MySQLConnector
from kdb.integrations.data_control.wecom_name_matcher import load_scoped_index, match_within_scope
from kdb.integrations.data_control.zhiqu_contact_fetcher import build_clients

BASE = str(_PROJECT_ROOT)
DEFAULT_MYSQL = os.path.join(BASE, 'config', 'mysql_conn_config.json')
DEFAULT_CRED = os.path.join(BASE, 'config', 'zhiqu_credentials.json')
DEFAULT_MAP = os.path.join(BASE, 'config', 'zhiqu_assistant_id_map.json')
DEFAULT_LOG_DIR = os.path.join(BASE, 'logs')
DEFAULT_SID_ROBOTS_TMPL = os.path.join(BASE, 'config', 'zhiqu_sid_to_robots_{client}.json')

ID_MAP_TYPE = 'zhiqu_external_id'


def load_assistant_id_map(path, client):
    """加载 config/zhiqu_assistant_id_map.json，返回:
        zhiqu_uid -> rfwkt_we_com_user_id   (dict)
        rfwkt_uids                          (set)
        zhiqu_uid -> nick_name              (dict)
    """
    with open(path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    if client not in cfg:
        raise SystemExit(f'{path} 缺少 client="{client}" 段，请先运行 build_zhiqu_assistant_id_map.py')
    z2r, z2nick = {}, {}
    rfwkt_uids = set()
    for a in cfg[client].get('assistants') or []:
        z2r[a['zhiqu_employee_user_id']] = a['rfwkt_we_com_user_id']
        z2nick[a['zhiqu_employee_user_id']] = a['nick_name']
        rfwkt_uids.add(a['rfwkt_we_com_user_id'])
    if not z2r:
        raise SystemExit(f'{path}.{client}.assistants 为空')
    return z2r, rfwkt_uids, z2nick


def fetch_zhiqu_contacts(client, cred_path, from_dump=None, page_size=100):
    """拉致趣全量；可选从本地 dump JSON 复用。"""
    if from_dump:
        logging.info('从本地 dump 加载: %s', from_dump)
        with open(from_dump, 'r', encoding='utf-8') as f:
            return json.load(f)
    zhiqu = build_clients(cred_path)
    if client not in zhiqu:
        raise SystemExit(f'zhiqu_credentials.json 无 client={client}')
    cli = zhiqu[client]
    items, page, total_page = [], 1, None
    while True:
        data = cli.list_contacts_page(page=page, page_size=page_size)
        page_items = data.get('list') or []
        meta = data.get('page') or {}
        if total_page is None:
            total_page = meta.get('totalPage')
            logging.info('[zhiqu][%s] total=%s totalPage=%s', client, meta.get('total'), total_page)
        items.extend(page_items)
        if page % 50 == 0:
            logging.info('[zhiqu][%s] fetched page %d/%s, accumulated %d', client, page, total_page, len(items))
        if not page_items or total_page is None or page >= total_page:
            break
        page += 1
    logging.info('[zhiqu][%s] fetched total %d', client, len(items))
    return items


def load_existing_mapping(cur, client):
    """已落库的 (cid, sid) 集合（本 client + 本 type），用于差集判断。"""
    cur.execute(
        """
        SELECT cid, sid FROM data_scrm_id_map
        WHERE client = %s AND type = %s
        """,
        (client, ID_MAP_TYPE),
    )
    return {(r['cid'], r['sid']) for r in cur.fetchall()}


def categorize(contacts, z2r, scoped):
    """
    按致趣 contact 分类。返回 (matched_rows, ambiguous_rows, unmatched_rows, out_of_scope_cnt)：
      matched: [{wx_external_userid, name, cid, rfwkt_uids_used, owner_names}]
      ambiguous: [{wx_external_userid, name, candidates=[...], rfwkt_uids_used, owner_names}]
      unmatched: [{wx_external_userid, name, rfwkt_uids_used, owner_names}]
      out_of_scope_cnt: 没有任何 owner 在映射里的 contact 数
    """
    matched, ambig, unmatched = [], [], []
    out_of_scope = 0
    for it in contacts:
        wx = it.get('wx_external_userid')
        name = (it.get('name') or '').strip()
        if not wx:
            continue
        owners = it.get('user_owner') or []
        # 过滤 owner 在 scope 中（按 employee_user_id 匹配，防改名）
        rfwkt_uids = []
        owner_names = []
        for o in owners:
            zuid = o.get('employee_user_id')
            ruid = z2r.get(zuid)
            if ruid is None:
                continue
            if ruid not in rfwkt_uids:
                rfwkt_uids.append(ruid)
            n = o.get('name')
            if n and n not in owner_names:
                owner_names.append(n)
        if not rfwkt_uids:
            out_of_scope += 1
            continue
        # 各 owner scope 内取名称命中并集
        cand = set()
        for ruid in rfwkt_uids:
            cand.update(match_within_scope(ruid, name, scoped))
        record = {
            'wx_external_userid': wx,
            'name': name,
            'owner_names': ';'.join(owner_names),
            'rfwkt_uids_used': ';'.join(rfwkt_uids),
        }
        if len(cand) == 0:
            unmatched.append(record)
        elif len(cand) == 1:
            record['cid'] = next(iter(cand))
            matched.append(record)
        else:
            record['candidates'] = ';'.join(sorted(cand))
            ambig.append(record)
    return matched, ambig, unmatched, out_of_scope


def insert_mappings(cur, client, to_insert):
    """批量 INSERT。to_insert: [(cid, sid)]"""
    if not to_insert:
        return 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sql = """
        INSERT INTO data_scrm_id_map (cid, client, type, sid, create_time, update_time)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    rows = [(cid, client, ID_MAP_TYPE, sid, now, now) for cid, sid in to_insert]
    cur.executemany(sql, rows)
    return len(rows)


def write_tsv(path, headers, rows):
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\t'.join(headers) + '\n')
        for r in rows:
            f.write('\t'.join(str(r.get(h, '')) for h in headers) + '\n')


def main():
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s: %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', default='mercado')
    parser.add_argument('--map', default=DEFAULT_MAP, help='zhiqu_assistant_id_map.json')
    parser.add_argument('--config', default=DEFAULT_MYSQL)
    parser.add_argument('--cred-path', default=DEFAULT_CRED)
    parser.add_argument('--from-dump', help='可选: 本地 zhiqu contact dump JSON，跳过 API')
    parser.add_argument('--log-dir', default=DEFAULT_LOG_DIR)
    parser.add_argument('--dry-run', action='store_true', help='只统计不写库')
    args = parser.parse_args()

    z2r, rfwkt_uids, z2nick = load_assistant_id_map(args.map, args.client)
    logging.info('assistants in scope: %d (client=%s)', len(z2r), args.client)

    contacts = fetch_zhiqu_contacts(args.client, args.cred_path, from_dump=args.from_dump)

    # 顺手维护 sid -> in-scope robots 索引（被 user_id_map_query 用于反查 robot_name）
    sid_to_robots = {}
    for it in contacts:
        sid = it.get('wx_external_userid')
        if not sid:
            continue
        robots = []
        for o in (it.get('user_owner') or []):
            nm = z2nick.get(o.get('employee_user_id'))
            if nm and nm not in robots:
                robots.append(nm)
        if robots:
            sid_to_robots[sid] = sorted(robots)
    sid_robots_path = DEFAULT_SID_ROBOTS_TMPL.format(client=args.client)
    with open(sid_robots_path, 'w', encoding='utf-8') as f:
        json.dump(sid_to_robots, f, ensure_ascii=False)
    logging.info('sid_to_robots 索引写出: %s (sid 数=%d)', sid_robots_path, len(sid_to_robots))

    conn = MySQLConnector(args.config)
    c = conn.get_connection()
    cur = c.cursor(dictionary=True)
    try:
        logging.info('载入 rfwkt scoped_index（uid IN %d 个 account）', len(rfwkt_uids))
        scoped = load_scoped_index(cur, rfwkt_uids)
        logging.info('scoped index entries: %d', len(scoped))
        existing = load_existing_mapping(cur, args.client)
        logging.info('已存在 (cid,sid) 对: %d', len(existing))

        matched, ambig, unmatched, out_of_scope = categorize(contacts, z2r, scoped)

        # 差集
        to_insert = []
        skipped_existing = 0
        for m in matched:
            key = (m['cid'], m['wx_external_userid'])
            if key in existing:
                skipped_existing += 1
            else:
                to_insert.append(key)

        # 落日志
        today = datetime.now().strftime('%Y%m%d')
        write_tsv(
            os.path.join(args.log_dir, f'ambiguous_zhiqu_{today}.tsv'),
            ['wx_external_userid', 'name', 'owner_names', 'rfwkt_uids_used', 'candidates'],
            ambig,
        )
        write_tsv(
            os.path.join(args.log_dir, f'unmatched_zhiqu_{today}.tsv'),
            ['wx_external_userid', 'name', 'owner_names', 'rfwkt_uids_used'],
            unmatched,
        )

        # 写库
        inserted = 0
        if args.dry_run:
            logging.info('[dry-run] 不写库, 待插入 %d 条', len(to_insert))
        else:
            cur2 = c.cursor()
            try:
                inserted = insert_mappings(cur2, args.client, to_insert)
                c.commit()
                logging.info('inserted %d 条', inserted)
            finally:
                cur2.close()
    finally:
        conn.close_connection(c, cur)

    total = len(contacts)
    in_scope = total - out_of_scope
    print()
    print('========== 致趣 external_id 映射 ==========')
    print(f'  client:           {args.client}')
    print(f'  scope assistants: {len(z2r)}')
    print(f'  致趣总 contact:    {total}')
    print(f'  scope 内 contact:  {in_scope}  ({100*in_scope/total:.1f}% of total)' if total else f'  scope 内 contact:  {in_scope}')
    print(f'  out of scope:     {out_of_scope}')
    print(f'  ── scope 内分类 ──')
    if in_scope:
        print(f'  matched(可写):     {len(matched)}  ({100*len(matched)/in_scope:.1f}% of scope)')
        print(f'  ambiguous(歧义):   {len(ambig)}  ({100*len(ambig)/in_scope:.1f}% of scope)')
        print(f'  unmatched(无候选): {len(unmatched)}  ({100*len(unmatched)/in_scope:.1f}% of scope)')
    print(f'  ── 写库 ──')
    print(f'  已存在(跳过):       {skipped_existing}')
    print(f'  本次新插:          {inserted if not args.dry_run else "(dry-run)" + " " + str(len(to_insert))}')
    print(f'  日志目录:          {args.log_dir}/  (ambiguous_zhiqu_*.tsv / unmatched_zhiqu_*.tsv)')


if __name__ == '__main__':
    main()
