#!/usr/bin/env python
# -*- coding:utf8 -*-
"""一次性拉取致趣全量外部联系人原始数据，落 JSON + Excel 供检查。

Usage:
    python data_control_tools/dump_zhiqu_contacts_raw.py [--client mercado] \
        [--page-size 100] [--out-dir data/zhiqu]
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('data_control_tools/dump_zhiqu_contacts_raw.py')
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))
from data_control_tools.zhiqu_contact_fetcher import build_clients


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', default='mercado')
    parser.add_argument('--page-size', type=int, default=100)
    parser.add_argument('--out-dir', default='data/zhiqu')
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    client = build_clients()[args.client]

    all_items = []
    page = 1
    total_page = None
    t0 = time.time()
    while True:
        data = client.list_contacts_page(page=page, page_size=args.page_size)
        items = data.get('list') or []
        page_meta = data.get('page') or {}
        if total_page is None:
            total_page = page_meta.get('totalPage')
            total = page_meta.get('total')
            print(f'[zhiqu][{args.client}] total={total} totalPage={total_page} page_size={args.page_size}')
        all_items.extend(items)
        if page % 20 == 0 or page == total_page:
            elapsed = time.time() - t0
            print(f'  page {page}/{total_page} accumulated={len(all_items)} elapsed={elapsed:.1f}s')
        if not items or total_page is None or page >= total_page:
            break
        page += 1

    print(f'fetched total: {len(all_items)}')

    json_path = os.path.join(args.out_dir, f'zhiqu_contacts_raw_{args.client}.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_items, f, ensure_ascii=False)
    print(f'wrote JSON: {json_path}  size={os.path.getsize(json_path)/1024/1024:.1f}MB')

    try:
        import openpyxl
        from openpyxl.utils.exceptions import IllegalCharacterError
        from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet('zhiqu_contacts')
        headers = ['id', 'wx_external_userid', 'plaintext_external_userid', 'name',
                   'WeComExternalContactMobile', 'email', 'open_id', 'unionid',
                   'owner_count', 'owner_names', 'owner_user_ids', 'owner_employee_ids',
                   'primary_owner_name']
        ws.append(headers)

        def _clean(v):
            if v is None:
                return ''
            s = str(v)
            return ILLEGAL_CHARACTERS_RE.sub('', s)

        for it in all_items:
            owners = it.get('user_owner') or []
            primary = next((o.get('name') for o in owners if o.get('is_primary') == 1), '')
            ws.append([
                it.get('id'),
                _clean(it.get('wx_external_userid')),
                _clean(it.get('plaintext_external_userid')),
                _clean(it.get('name')),
                _clean(it.get('WeComExternalContactMobile')),
                _clean(it.get('email')),
                _clean(it.get('open_id')),
                _clean(it.get('unionid')),
                len(owners),
                _clean(';'.join(o.get('name', '') for o in owners)),
                _clean(';'.join(o.get('employee_user_id', '') for o in owners)),
                _clean(';'.join(str(o.get('employee_id', '')) for o in owners)),
                _clean(primary),
            ])
        xlsx_path = os.path.join(args.out_dir, f'zhiqu_contacts_raw_{args.client}.xlsx')
        wb.save(xlsx_path)
        print(f'wrote XLSX: {xlsx_path}  size={os.path.getsize(xlsx_path)/1024/1024:.1f}MB')
    except Exception as e:
        print(f'xlsx 写出失败（JSON 已经保存好了）: {e}')

    # 统计：owner 名分布 / email 填充 / mobile 填充 / unionid 填充
    from collections import Counter
    owner_cnt = Counter()
    multi_owner = 0
    with_email = with_mobile = with_unionid = with_plaintext = 0
    for it in all_items:
        owners = it.get('user_owner') or []
        if len(owners) > 1:
            multi_owner += 1
        for o in owners:
            n = o.get('name', '')
            if n:
                owner_cnt[n] += 1
        if it.get('email'):
            with_email += 1
        if it.get('WeComExternalContactMobile'):
            with_mobile += 1
        if it.get('unionid'):
            with_unionid += 1
        if it.get('plaintext_external_userid'):
            with_plaintext += 1
    print()
    print(f'====== 字段填充率 (total={len(all_items)}) ======')
    print(f' email           : {with_email}  ({100*with_email/len(all_items):.1f}%)')
    print(f' mobile          : {with_mobile}  ({100*with_mobile/len(all_items):.1f}%)')
    print(f' unionid         : {with_unionid}  ({100*with_unionid/len(all_items):.1f}%)')
    print(f' plaintext_ext_id: {with_plaintext}  ({100*with_plaintext/len(all_items):.1f}%)')
    print(f' 多 owner        : {multi_owner}')
    print()
    print(f'====== owner 分布（top 30 / 共 {len(owner_cnt)} 个） ======')
    for n, v in owner_cnt.most_common(30):
        print(f'  {n}: {v}')


if __name__ == '__main__':
    main()
