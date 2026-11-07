from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
通过"名称"关联，找出好友 External ID 与其企业微信 ID 的映射（数据库只读）。

背景 / 已验证事实：
- 输入 Excel 列：External ID(好友 wm 开头外部联系人ID) / 名称(好友昵称) / 添加人(企业微信账号名)。
- rf_wkt_we_com_contact 中并不存储 wm 开头的 External ID，外部好友的
  we_com_contact_user_id 是数字ID，因此 External ID 无法直接 join，只能用"名称"关联。

匹配口径（关键）：
- **只在"添加人"本账号的好友里按名称匹配，不跨账号**。
  添加人 nick_name -> rf_wkt_we_com_account.we_com_user_id；再在该账号的外部好友里按名称命中。
- **添加人账号不存在的整组直接移出分析**（如 小魏 在 account 表中不存在），单独放 excluded，
  不计入分母（既不算已关联也不算未关联）。
- 外部好友过滤：relation_type=2(外部) AND type=1(好友) AND del_flag=0。
- 名称同时比对 we_com_contact_nick_name 与 we_com_contact_real_name；命中的
  we_com_contact_user_id 去重。同账号内同名重复会命中多个ID，全部列出。
"""
import os
import sys

import openpyxl

from kdb.shared.clients.mysql_connector import MySQLConnector
from kdb.integrations.data_control.wecom_name_matcher import load_account_map, load_scoped_index

BASE = str(_PROJECT_ROOT)
DEFAULT_CONFIG = os.path.join(BASE, 'config/mysql_conn_config.json')
DEFAULT_XLSX = os.path.join(BASE, 'data/meikeduo/external_id/external_id_sample.xlsx')
DEFAULT_OUT = os.path.join(BASE, 'data/meikeduo/external_id/external_id_wecom_map.xlsx')

CHAT_LOOKBACK_DAYS = 90  # 多关联消歧：只看近 3 个月(90天)对话


def load_excel(xlsx_path):
    """读取输入 Excel，返回 list[dict(external_id,name,adder)]。"""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb['Sheet1']
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        rows.append({
            'external_id': str(r[0]).strip(),
            'name': ('' if r[1] is None else str(r[1])).strip(),
            'adder': ('' if r[2] is None else str(r[2])).strip(),
        })
    return rows


def build_mapping(rows, account_map, scoped):
    """
    仅同账号匹配。返回 (results, excluded)：
    - results: 添加人账号存在的行，含 external_id/name/adder/account_uid/wecom_ids/match_count/status
    - excluded: 添加人账号不存在的行（整组移出），不计入分母
    """
    results, excluded = [], []
    for r in rows:
        account_uid = account_map.get(r['adder'])
        if account_uid is None:
            excluded.append({'external_id': r['external_id'], 'name': r['name'], 'adder': r['adder']})
            continue
        ids = sorted(scoped.get((account_uid, r['name']), set()))
        results.append({
            'external_id': r['external_id'],
            'name': r['name'],
            'adder': r['adder'],
            'account_uid': account_uid,
            'wecom_ids': ids,
            'match_count': len(ids),
            'status': 'matched' if ids else 'name_not_found',
        })
    return results, excluded


def _pct(n, d):
    return round(n * 100.0 / d, 1) if d else 0.0


def compute_stats(results, excluded):
    """统计 + 比例。分母 base = 添加人账号存在的行数（已移除缺失账号组）。"""
    base = len(results)
    matched = [r for r in results if r['match_count'] >= 1]
    dist = {}
    for r in matched:
        dist[r['match_count']] = dist.get(r['match_count'], 0) + 1
    # 分桶：1 / 2 / 3 / >3
    buckets = {'1': 0, '2': 0, '3': 0, '>3': 0}
    for r in matched:
        c = r['match_count']
        buckets['1' if c == 1 else '2' if c == 2 else '3' if c == 3 else '>3'] += 1
    return {
        'analysis_base': base,                       # 分析基数（不含缺失账号组）
        'excluded_account_missing': len(excluded),   # 因添加人账号缺失被移出的行数
        'matched': len(matched),
        'matched_pct': _pct(len(matched), base),     # 关联率（占分析基数）
        'unmatched': base - len(matched),
        'unmatched_pct': _pct(base - len(matched), base),
        'match_count_distribution': dist,            # {命中企业微信ID个数: external_id 数}
        # 各桶占已关联数比例 / 占分析基数比例
        'match_count_pct': {k: _pct(v, len(matched)) for k, v in dist.items()},
        'match_count_pct_base': {k: _pct(v, base) for k, v in dist.items()},
        'match_count_buckets': buckets,              # 分桶 1/2/3/>3 -> external_id 数
        'match_count_buckets_pct': {k: _pct(v, len(matched)) for k, v in buckets.items()},
        'match_count_buckets_pct_base': {k: _pct(v, base) for k, v in buckets.items()},
    }


def load_chat_activity(cur, contact_user_ids, days=CHAT_LOOKBACK_DAYS):
    """
    近 days 天内，按 from_user_id(好友为消息来源)聚合对话活跃度。
    返回 dict{from_user_id: {msg_count, session_count, last_time, to_users}}。
    仅含有记录的 id；无记录的 id 不在返回里。
    """
    from datetime import datetime, timedelta
    activity = {}
    ids = list(contact_user_ids)
    if not ids:
        return activity
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    for i in range(0, len(ids), 1000):
        chunk = ids[i:i + 1000]
        ph = ','.join(['%s'] * len(chunk))
        cur.execute(f"""
            SELECT from_user_id AS fid, COUNT(*) AS msg_count,
                   COUNT(DISTINCT session_id) AS session_count,
                   MAX(create_time) AS last_time,
                   GROUP_CONCAT(DISTINCT to_user_id) AS to_users
            FROM data_chat_history
            WHERE from_user_id IN ({ph})
              AND create_time >= %s
              AND del_flag = 0
            GROUP BY from_user_id
        """, chunk + [cutoff])
        for r in cur.fetchall():
            activity[r['fid']] = {
                'msg_count': r['msg_count'],
                'session_count': r['session_count'],
                'last_time': r['last_time'],
                'to_users': r['to_users'] or '',
            }
    return activity, cutoff


def disambiguate_multi_by_chat(multi_results, activity):
    """
    对多关联(match_count>1)的 external_id，用近 N 天对话活跃度消歧。
    分类(按"有对话的候选数"):
      0  -> indistinguishable(都无对话,视为一样)
      1  -> resolvable(唯一有对话,可区分,给出建议归属ID)
      >=2-> multi_active(多个有对话,确为不同的人)
    返回 (detail_rows, summary)。
    """
    detail, summary = [], {'indistinguishable': 0, 'resolvable': 0, 'multi_active': 0}
    for r in multi_results:
        active_ids = [cid for cid in r['wecom_ids'] if cid in activity]
        if len(active_ids) == 0:
            category = 'indistinguishable'
        elif len(active_ids) == 1:
            category = 'resolvable'
        else:
            category = 'multi_active'
        summary[category] += 1
        resolved = active_ids[0] if category == 'resolvable' else ''
        for cid in r['wecom_ids']:
            a = activity.get(cid)
            detail.append({
                'external_id': r['external_id'], 'name': r['name'], 'adder': r['adder'],
                'candidate_id': cid,
                'msg_count': a['msg_count'] if a else 0,
                'session_count': a['session_count'] if a else 0,
                'last_time': str(a['last_time']) if a else '',
                'to_users': a['to_users'] if a else '',
                'has_chat': '是' if a else '否',
                'category': category,
                'resolved_id': resolved,
            })
    return detail, summary


def build_final_summary(stats, indist_summary):
    """
    最终漏斗（以分析基数 base 为分母，14 条缺失账号已另计）。
    口径：一个 external_id 只要存在"无法区分的人"(同 external_id 下 ≥2 个候选的近90天
    chat_history 相等/均为空) 就算"无法区分"，否则算"可区分/可确定"。
      name_only   = 仅靠原始名称即唯一(match_count==1)，单候选必可区分
      by_chat     = 多关联中无"无法区分的人"(借 chat 可区分)  = 多关联总数 - 含无法区分的
      determined  = name_only + by_chat
      undistinguishable = 多关联中存在"无法区分的人"
      name_not_found    = 名称未匹配(无候选)
      remaining = undistinguishable + name_not_found
    """
    base = stats['analysis_base']
    name_only = stats['match_count_buckets']['1']
    total_multi = indist_summary['multi_external_id']
    undistinguishable = indist_summary['ext_with_indistinguishable']
    by_chat = total_multi - undistinguishable
    name_not_found = stats['unmatched']
    determined = name_only + by_chat
    remaining = undistinguishable + name_not_found
    return {
        'base': base,
        'excluded_account_missing': stats['excluded_account_missing'],
        'name_only': name_only,
        'by_chat': by_chat,
        'determined': determined,
        'undistinguishable': undistinguishable,
        'name_not_found': name_not_found,
        'remaining': remaining,
    }


def count_indistinguishable(multi_results, activity):
    """
    对每个多关联 external_id，按"聊天记录指纹"给候选人分组：
      指纹 = 'EMPTY'(近90天无对话) 或 唯一(有对话,各自独立) 。
    指纹独一无二的候选 => 分得清；指纹被 >=2 个候选共享(实际为"都无对话"那批) => 无法分清。
    返回 (rows, summary)：
      rows: 每个多关联 external_id 一行（候选总数/可分清/无法分清）
      summary: 汇总（候选总数、可分清、无法分清、仍含无法分清的 external_id 数）
    """
    rows = []
    tot_cand = tot_indist = ext_with_indist = 0
    for r in multi_results:
        groups = {}
        for cid in r['wecom_ids']:
            sig = 'EMPTY' if cid not in activity else 'ID:' + cid
            groups.setdefault(sig, []).append(cid)
        indist = sum(len(v) for v in groups.values() if len(v) >= 2)
        total = len(r['wecom_ids'])
        rows.append({
            'external_id': r['external_id'], 'name': r['name'], 'adder': r['adder'],
            'candidate_total': total,
            'distinguishable': total - indist,
            'indistinguishable': indist,
        })
        tot_cand += total
        tot_indist += indist
        if indist > 0:
            ext_with_indist += 1
    rows.sort(key=lambda x: -x['indistinguishable'])
    summary = {
        'multi_external_id': len(multi_results),
        'candidate_total': tot_cand,
        'distinguishable': tot_cand - tot_indist,
        'indistinguishable': tot_indist,
        'ext_with_indistinguishable': ext_with_indist,
    }
    return rows, summary


def compute_per_account_stats(results, excluded, account_map):
    """
    每个企业微信账号(添加人)各自的关联统计。
    返回 list[dict]，按 Excel 好友数降序。账号缺失的(如 小魏)也列出并标记。
    """
    agg = {}  # adder -> dict
    for r in results:
        a = agg.setdefault(r['adder'], {
            'adder': r['adder'], 'account_uid': r['account_uid'],
            'account_exists': True, 'total': 0, 'matched': 0, 'unmatched': 0})
        a['total'] += 1
        if r['match_count'] >= 1:
            a['matched'] += 1
        else:
            a['unmatched'] += 1
    for r in excluded:
        a = agg.setdefault(r['adder'], {
            'adder': r['adder'], 'account_uid': '', 'account_exists': False,
            'total': 0, 'matched': 0, 'unmatched': 0})
        a['total'] += 1  # 账号缺失，全部视为无法关联

    out = []
    for a in agg.values():
        a['match_rate'] = _pct(a['matched'], a['total'])
        out.append(a)
    out.sort(key=lambda x: -x['total'])
    return out


def write_output(results, excluded, stats, per_account, disambig_detail, disambig_summary,
                 indist_rows, indist_summary, final, out_path):
    wb = openpyxl.Workbook()
    ws0 = wb.active
    ws0.title = 'final_summary'
    b = final['base']
    ws0.append(['最终结果（分析基数, 已移除缺失账号组）', '数量', '占基数比例'])
    ws0.append(['分析基数', b, '100.0%'])
    ws0.append(['① 仅用原始名称即可确定(唯一匹配)', final['name_only'], f"{_pct(final['name_only'], b)}%"])
    ws0.append(['② 预期加上对话文档可增加区分(候选聊天记录各不相同)', final['by_chat'], f"{_pct(final['by_chat'], b)}%"])
    ws0.append(['= 累计可区分(①+②, ②为预期)', final['determined'], f"{_pct(final['determined'], b)}%"])
    ws0.append(['③ external_id下多个同名, 且对话记录不存在(无法区分)', final['undistinguishable'], f"{_pct(final['undistinguishable'], b)}%"])
    ws0.append(['④ 名称未匹配(无候选)', final['name_not_found'], f"{_pct(final['name_not_found'], b)}%"])
    ws0.append(['= 剩余未确定 (③+④)', final['remaining'], f"{_pct(final['remaining'], b)}%"])
    ws0.append([])
    ws0.append(['(另) 因添加人账号缺失被移出, 不计入基数', final['excluded_account_missing'], ''])

    ws = wb.create_sheet('mapping')
    ws.append(['External ID', '名称', '添加人', '添加人账号we_com_user_id',
               '匹配到的企业微信ID(分号分隔)', '匹配个数', '状态'])
    for r in results:
        ws.append([r['external_id'], r['name'], r['adder'], r['account_uid'],
                   ';'.join(r['wecom_ids']), r['match_count'], r['status']])

    ws2 = wb.create_sheet('stats')
    ws2.append(['指标', '数值', '比例'])
    ws2.append(['分析基数(已移除缺失账号组)', stats['analysis_base'], '100.0%'])
    ws2.append(['已关联(>=1个)', stats['matched'], f"{stats['matched_pct']}%"])
    ws2.append(['未关联(名称在本账号内未匹配)', stats['unmatched'], f"{stats['unmatched_pct']}%"])
    ws2.append(['(另)因添加人账号缺失被移出', stats['excluded_account_missing'], '—'])
    ws2.append([])
    ws2.append(['关联数量分布(分桶)', 'external_id 数', '占已关联比例', '占分析基数比例'])
    for k in ('1', '2', '3', '>3'):
        ws2.append([f'关联 {k} 个', stats['match_count_buckets'][k],
                    f"{stats['match_count_buckets_pct'][k]}%", f"{stats['match_count_buckets_pct_base'][k]}%"])
    ws2.append([])
    ws2.append(['关联企业微信ID个数(明细)', 'external_id 数', '占已关联比例', '占分析基数比例'])
    for k in sorted(stats['match_count_distribution']):
        ws2.append([k, stats['match_count_distribution'][k],
                    f"{stats['match_count_pct'][k]}%", f"{stats['match_count_pct_base'][k]}%"])

    ws3 = wb.create_sheet('per_account_stats')
    ws3.append(['添加人(企业微信账号)', 'we_com_user_id', '账号是否存在',
                '好友总数', '已关联', '未关联', '关联率'])
    for a in per_account:
        ws3.append([a['adder'], a['account_uid'], '是' if a['account_exists'] else '否(整组移出)',
                    a['total'], a['matched'], a['unmatched'], f"{a['match_rate']}%"])

    ws4 = wb.create_sheet('unmatched')
    ws4.append(['External ID', '名称', '添加人', '添加人账号we_com_user_id'])
    for r in results:
        if r['match_count'] == 0:
            ws4.append([r['external_id'], r['name'], r['adder'], r['account_uid']])

    ws5 = wb.create_sheet('excluded_account_missing')
    ws5.append(['External ID', '名称', '添加人(账号在account表中不存在)'])
    for r in excluded:
        ws5.append([r['external_id'], r['name'], r['adder']])

    # 多关联消歧：汇总
    total_multi = sum(disambig_summary.values())
    label = {'resolvable': '唯一有对话(可区分)', 'multi_active': '>=2个有对话(确为不同的人)',
             'indistinguishable': '都无对话(视为一样)'}
    ws6 = wb.create_sheet('multi_disambig_summary')
    ws6.append([f'多关联 external_id 消歧(近{CHAT_LOOKBACK_DAYS}天对话)', 'external_id 数', '占多关联比例'])
    ws6.append(['多关联 external_id 总数', total_multi, '100.0%'])
    for k in ('resolvable', 'multi_active', 'indistinguishable'):
        ws6.append([label[k], disambig_summary[k], f"{_pct(disambig_summary[k], total_multi)}%"])

    # 多关联消歧：明细（一行一个候选ID）
    ws7 = wb.create_sheet('multi_disambig_detail')
    ws7.append(['External ID', '名称', '添加人', '候选企业微信ID', f'近{CHAT_LOOKBACK_DAYS}天消息数',
                '会话数', '最近消息时间', '对话对方账号(to_user_id)', '该候选是否有对话', '分类', '建议归属ID'])
    for d in disambig_detail:
        ws7.append([d['external_id'], d['name'], d['adder'], d['candidate_id'], d['msg_count'],
                    d['session_count'], d['last_time'], d['to_users'], d['has_chat'],
                    label[d['category']], d['resolved_id']])

    # 多关联：每个 external_id 还剩多少人无法分清
    ws8 = wb.create_sheet('indistinguishable_count')
    ws8.append([f'按近{CHAT_LOOKBACK_DAYS}天聊天记录指纹：指纹唯一=分得清；>=2个相同(均无对话)=无法分清'])
    ws8.append(['External ID', '名称', '添加人', '候选总人数', '可分清人数', '无法分清人数'])
    for r in indist_rows:
        ws8.append([r['external_id'], r['name'], r['adder'],
                    r['candidate_total'], r['distinguishable'], r['indistinguishable']])
    ws8.append([])
    ws8.append(['合计', '', '', indist_summary['candidate_total'],
                indist_summary['distinguishable'], indist_summary['indistinguishable']])
    ws8.append(['仍含"无法分清"的 external_id 数', indist_summary['ext_with_indistinguishable']])

    wb.save(out_path)


def print_stats(stats):
    print('========== 统计（仅同账号匹配，已移除缺失账号组）==========')
    b = stats['analysis_base']
    print(f"分析基数(已移除缺失账号组):  {b}  (100.0%)")
    print(f"已关联(>=1个):               {stats['matched']}  ({stats['matched_pct']}%)")
    print(f"未关联(本账号内未匹配):       {stats['unmatched']}  ({stats['unmatched_pct']}%)")
    print(f"(另)因添加人账号缺失被移出:   {stats['excluded_account_missing']} 行  —不计入分母")
    print('关联数量分布(分桶):')
    print(f"  {'':>10}{'数量':>6}{'占已关联':>10}{'占分析基数':>12}")
    for k in ('1', '2', '3', '>3'):
        v = stats['match_count_buckets'][k]
        print(f"  关联 {k:>3} 个:{v:>6}{stats['match_count_buckets_pct'][k]:>9}%"
              f"{stats['match_count_buckets_pct_base'][k]:>11}%")


def print_per_account(per_account):
    print('\n========== 每个企业微信账号关联统计 ==========')
    print(f"{'添加人':<22}{'好友总数':>8}{'已关联':>8}{'未关联':>8}{'关联率':>9}  账号")
    for a in per_account:
        exists = '存在' if a['account_exists'] else '缺失(移出)'
        print(f"{a['adder']:<22}{a['total']:>8}{a['matched']:>8}{a['unmatched']:>8}"
              f"{a['match_rate']:>8}%  {exists}")


def print_unmatched_sample(results, n=25):
    unmatched = [r for r in results if r['match_count'] == 0]
    # 按添加人均匀抽样，保证各账号都有代表
    by_adder = {}
    for r in unmatched:
        by_adder.setdefault(r['adder'], []).append(r)
    sample = []
    i = 0
    while len(sample) < n and any(i < len(v) for v in by_adder.values()):
        for v in by_adder.values():
            if i < len(v) and len(sample) < n:
                sample.append(v[i])
        i += 1
    print(f'\n========== 未关联样例（共 {len(unmatched)} 条，抽样 {len(sample)} 条）==========')
    print(f"{'名称':<24}{'添加人':<22} External ID")
    for r in sample:
        print(f"{r['name']:<24}{r['adder']:<22} {r['external_id']}")


def main():
    config = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG
    xlsx = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_XLSX
    out = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_OUT

    rows = load_excel(xlsx)
    adder_names = {r['adder'] for r in rows if r['adder']}

    conn = MySQLConnector(config)
    c = conn.get_connection()
    cur = c.cursor(dictionary=True)
    try:
        account_map = load_account_map(cur, adder_names)
        missing_accounts = sorted(adder_names - set(account_map))
        scoped = load_scoped_index(cur, set(account_map.values()))

        results, excluded = build_mapping(rows, account_map, scoped)
        # 多关联消歧：拉取候选好友近 N 天对话活跃度
        multi_results = [r for r in results if r['match_count'] > 1]
        multi_ids = {cid for r in multi_results for cid in r['wecom_ids']}
        activity, cutoff = load_chat_activity(cur, multi_ids)
    finally:
        conn.close_connection(c, cur)

    stats = compute_stats(results, excluded)
    per_account = compute_per_account_stats(results, excluded, account_map)
    disambig_detail, disambig_summary = disambiguate_multi_by_chat(multi_results, activity)
    indist_rows, indist_summary = count_indistinguishable(multi_results, activity)
    final = build_final_summary(stats, indist_summary)

    print(f'Excel 记录: {len(rows)}  去重添加人: {len(adder_names)}  匹配到账号: {len(account_map)}')
    if missing_accounts:
        print(f'account 表中找不到的添加人(整组移出): {missing_accounts}')
    print_stats(stats)
    print_per_account(per_account)
    print_disambig(multi_results, disambig_summary, cutoff)
    print_indistinguishable(indist_rows, indist_summary)
    print_final_summary(final)
    print_unmatched_sample(results)

    write_output(results, excluded, stats, per_account, disambig_detail, disambig_summary,
                 indist_rows, indist_summary, final, out)
    print(f'\n映射已写出: {out}')


def print_final_summary(f):
    b = f['base']
    print('\n========== 最终结果（分析基数 %d, 已移除缺失账号组 %d 条）==========' % (b, f['excluded_account_missing']))
    print(f"① 仅用原始名称可确定:                {f['name_only']:>4}  ({_pct(f['name_only'], b)}%)")
    print(f"② 预期加上对话文档可增加区分:        {f['by_chat']:>4}  ({_pct(f['by_chat'], b)}%)")
    print(f"= 累计可区分(①+②, ②为预期):         {f['determined']:>4}  ({_pct(f['determined'], b)}%)")
    print(f"③ external_id下多个同名且对话记录不存在: {f['undistinguishable']:>4}  ({_pct(f['undistinguishable'], b)}%)")
    print(f"④ 名称未匹配(无候选):                {f['name_not_found']:>4}  ({_pct(f['name_not_found'], b)}%)")
    print(f"= 剩余未确定 (③+④):                 {f['remaining']:>4}  ({_pct(f['remaining'], b)}%)")


def print_disambig(multi_results, summary, cutoff):
    total = len(multi_results)
    print(f'\n========== 多关联消歧（近{CHAT_LOOKBACK_DAYS}天对话, 起点 {cutoff}）==========')
    print(f"多关联 external_id 总数: {total}")
    rows = [('唯一有对话(可区分,可定位归属ID)', summary['resolvable']),
            ('>=2个有对话(确为不同的人)', summary['multi_active']),
            ('都无对话(视为一样)', summary['indistinguishable'])]
    for label, v in rows:
        print(f"  {label}: {v}  ({_pct(v, total)}%)")


def print_indistinguishable(rows, summary):
    print(f'\n========== 多关联：还剩多少人无法分清（近{CHAT_LOOKBACK_DAYS}天聊天记录）==========')
    print(f"多关联 external_id: {summary['multi_external_id']}   候选总人数: {summary['candidate_total']}")
    print(f"可分清人数:   {summary['distinguishable']}")
    print(f"无法分清人数: {summary['indistinguishable']}  "
          f"(分布在 {summary['ext_with_indistinguishable']} 个 external_id 下)")
    top = [r for r in rows if r['indistinguishable'] > 0]
    print(f"含无法分清的 external_id 明细（共 {len(top)} 个）:")
    print(f"  {'名称':<20}{'添加人':<22}{'候选':>5}{'可分清':>7}{'无法分清':>9}")
    for r in top:
        print(f"  {r['name']:<20}{r['adder']:<22}{r['candidate_total']:>5}"
              f"{r['distinguishable']:>7}{r['indistinguishable']:>9}")


if __name__ == '__main__':
    main()
