#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
企业微信「同账号 scoped 名称匹配」公共模块。

桥接事实（已验证 2026-06-18）：
- rf_wkt_we_com_contact.we_com_contact_user_id 是数字，等于本系统 data_scrm.cid（同一 corp 内的
  WeCom 外部联系人内部 id）。所以"名称 → we_com_contact_user_id"即"名称 → 本系统 cid"。

匹配口径：
- 仅在「添加人 nick_name 对应的 we_com_user_id」账号内，按名称命中外部好友。不跨账号。
- 名称同时比对昵称与真实姓名。

好友数据源是两张表的并集（2026-08-19 起，二者互补，缺一都会丢客户）：
- rf_wkt_we_com_contact：过滤 relation_type=2 外部 / type=1 好友 / del_flag=0
- lm_channel_contact：过滤 del_flag='0'(字符串) / channel_type='we_com_wkteam'(企微；
  wx_wkteam 是个人微信、account_id 为 wxid_*，跟致趣对不上) / 排除 user_id=account_id 的自指行
"""


def load_account_map(cur, adder_names):
    """添加人 nick_name -> we_com_user_id（仅未删除账号）。同名取第一条。"""
    if not adder_names:
        return {}
    names = list(adder_names)
    placeholders = ','.join(['%s'] * len(names))
    cur.execute(
        f"""
        SELECT nick_name, we_com_user_id
        FROM rf_wkt_we_com_account
        WHERE nick_name IN ({placeholders}) AND del_flag = 0
        """,
        names,
    )
    out = {}
    for row in cur.fetchall():
        out.setdefault(row['nick_name'], row['we_com_user_id'])
    return out


def _index_rows(cur, sql, params, index):
    """把查询结果按 (uid, 名称) 累加进索引；nick_name / real_name 都建索引。"""
    cur.execute(sql, params)
    for r in cur.fetchall():
        for field in (r['nick_name'], r['real_name']):
            if not field or not field.strip():
                continue
            index.setdefault((r['uid'], field.strip()), set()).add(r['contact_id'])


def load_scoped_index(cur, we_com_user_ids):
    """
    载入这些账号名下的外部好友，建索引：
      (账号 uid, 名称) -> set(cid)
    名称同时索引昵称与真实姓名。数据源为 rf_wkt_we_com_contact 与 lm_channel_contact 的并集，
    两表命中的 cid 合并进同一个 key（互补关系，不能只留一张）。
    """
    index = {}
    if not we_com_user_ids:
        return index
    uids = list(we_com_user_ids)
    placeholders = ','.join(['%s'] * len(uids))

    # 源 1：企微好友关系表
    _index_rows(
        cur,
        f"""
        SELECT we_com_user_id AS uid,
               we_com_contact_user_id AS contact_id,
               we_com_contact_nick_name AS nick_name,
               we_com_contact_real_name AS real_name
        FROM rf_wkt_we_com_contact
        WHERE we_com_user_id IN ({placeholders})
          AND we_com_contact_relation_type = 2
          AND we_com_contact_type = 1
          AND del_flag = 0
        """,
        uids,
        index,
    )

    # 源 2：渠道联系人表。del_flag 是字符串；只取企微渠道；排除助手自指行
    _index_rows(
        cur,
        f"""
        SELECT account_id AS uid,
               user_id AS contact_id,
               nickname AS nick_name,
               real_name AS real_name
        FROM lm_channel_contact
        WHERE account_id IN ({placeholders})
          AND del_flag = '0'
          AND channel_type = 'we_com_wkteam'
          AND user_id <> account_id
        """,
        uids,
        index,
    )
    return index


def match_within_scope(account_uid, name, scoped):
    """单条查询：返回该账号下名为 name 的外部好友 contact_id 列表（排序、去重）。"""
    if not account_uid or not name:
        return []
    return sorted(scoped.get((account_uid, name.strip()), set()))
