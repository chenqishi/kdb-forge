import json
import sys
import logging
import time
from wechat_tools.wkteam_request_util import WxWkteamRequestUtil
import re

def get_chatroom_member(chatroom_id_file, wx_config):
    """
    获取chatroom_id_file中每个群id的详细成员列表，并输出格式为"{line}\t{member_result_json}"
    Args:
        chatroom_id_file: 包含群id的文件（每行一个群id，允许有其他列，群id为第一列）
        wx_config: 微信配置文件路径
    Returns:
        list: 每行输出结果的列表
    """
    # 初始化微信工具
    wx_util = WxWkteamRequestUtil()
    wx_util.init_config(wx_config)
    wx_util.auto_login()
    
    results = []
    with open(chatroom_id_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line.strip():
                continue
            chatroom_id = line.split('\t')[0]
            member_result = wx_util.getChatRoomMember(chatroom_id)
            member_result_json = json.dumps(member_result, ensure_ascii=False)
            time.sleep(30)
            results.append(f"{line}\t{member_result_json}")
    return results

def stat_member_id(member_file, output_file=None, error_file=None, excel_output_file=None):
    """
    对get_chatroom_member产出的文件进行供应商id统计分析。
    Args:
        member_file: get_chatroom_member产出的文件路径
        output_file: 统计结果输出文件路径（可选）
        error_file: 异常member输出文件路径（可选）
        excel_output_file: 统计结果excel输出文件路径（可选）
    Returns:
        list: 每个chatroom的统计结果
    """
    import openpyxl
    from openpyxl import Workbook
    results = []
    error_members = []
    excel_room_member_detail = []  # [(room_name, member_display_name, suid)]
    excel_room_stat = []           # [(room_name, 有id数, 无id数, id不重复数, 重复id数量, 不重复比率, 重复比率)]
    excel_noid_detail = []         # [(room_name, member_display_name)]
    def extract_suid(display_name):
        """抽取display_name中所有长度为5或6的纯数字id，支持前缀如302015路路-运营，返回list"""
        if not display_name:
            return []
        # 匹配所有5或6位纯数字（包括前缀）
        suids = [m for m in re.findall(r'(?<!\d)(\d{5,6})(?!\d)', display_name)]
        # 检查前缀
        if not suids:
            m = re.match(r'^(\d{5,6})', display_name)
            if m:
                suids.append(m.group(1))
        return suids

    with open(member_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line.strip():
                continue
            try:
                parts = line.split('\t')
                chatroom_id = parts[0]
                room_name = parts[1] if len(parts) > 1 else chatroom_id
                member_json = parts[-1]
                members = json.loads(member_json)
            except Exception as e:
                error_members.append({'line': line, 'error': f'解析失败: {str(e)}'})
                continue
            suid_count = {}
            suid_set = set()
            suid_counter = {}
            total = 0
            with_id = 0
            without_id = 0
            all_suid_count = 0
            for member in members:
                display_name = member.get('displayName') or member.get('nickName') or ''
                suid_list = extract_suid(display_name)
                excel_room_member_detail.append((room_name, display_name, ','.join(suid_list)))
                if suid_list:
                    for suid in suid_list:
                        suid_count[suid] = suid_count.get(suid, 0) + 1
                        suid_set.add(suid)
                        suid_counter[suid] = suid_counter.get(suid, 0) + 1
                        all_suid_count += 1
                    with_id += 1
                else:
                    error_members.append({'chatroom': chatroom_id, 'room_name': room_name, 'member': display_name})
                    excel_noid_detail.append((room_name, display_name))
                    without_id += 1
                total += 1
            unique_count = len(suid_set)
            #repeat_id_count = sum(1 for v in suid_counter.values() if v > 1)
            repeat_id_count = all_suid_count - unique_count
            not_repeat_rate = unique_count / with_id if with_id else 0
            repeat_rate = 1 - not_repeat_rate if with_id else 0
            result = {
                'chatroom': chatroom_id,
                'room_name': room_name,
                'total_member': total,
                'all_suid_count': all_suid_count,
                'with_id_member': with_id,
                'without_id_member': without_id,
                'unique_supplier_count': unique_count,
                'repeat_id_count': repeat_id_count,
                'not_repeat_rate': not_repeat_rate,
                'repeat_rate': repeat_rate,
                'suid_count': suid_count
            }
            results.append(result)
            excel_room_stat.append((room_name, total, with_id, without_id, all_suid_count, unique_count, repeat_id_count, not_repeat_rate, repeat_rate))
    # 输出统计结果
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    # 输出异常member
    if error_file:
        with open(error_file, 'w', encoding='utf-8') as f:
            for e in error_members:
                f.write(json.dumps(e, ensure_ascii=False) + '\n')
    # 输出excel
    if excel_output_file:
        wb = Workbook()
        # 1. 群成员详细数据
        ws1 = wb.active
        ws1.title = '群成员详细数据'
        ws1.append(['群名', '成员名称', 'id'])
        for row in excel_room_member_detail:
            ws1.append(list(row))
        # 2. 群统计数
        ws2 = wb.create_sheet('群统计数')
        ws2.append(['群名', '总人数', '含有id的成员数量', '不含id成员数量', 'id总数', 'id不重复数量', '重复id数量', '不重复比率', '重复比率'])
        for row in excel_room_stat:
            ws2.append(list(row))
        # 3. 没有id的成员详细情况
        ws3 = wb.create_sheet('没有id的成员详细情况')
        ws3.append(['群名', '成员名称'])
        for row in excel_noid_detail:
            ws3.append(list(row))
        wb.save(excel_output_file)
    #return results

def get_all_room(config_path, customer, user=None):
    """
    直接从数据库获取所有群聊room_id和room_name（is_group=1时other_user_id为群id，other_user_nick_name为群名）
    输出格式：{room_id}\t{room_name}
    """
    from commons.mysql_connector import MySQLConnector
    connector = MySQLConnector(config_path)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        sql = "SELECT other_user_id, other_user_nickname FROM data_chat_history WHERE customer = %s AND is_group = 1"
        params = [customer]
        if user is not None:
            sql += " AND user = %s"
            params.append(user)
        sql += " GROUP BY other_user_id, other_user_nickname"
        cursor.execute(sql, params)
        for row in cursor:
            room_id = row.get('other_user_id') or ''
            room_name = row.get('other_user_nickname') or ''
            print(f"{room_id}\t{room_name}")
    finally:
        connector.close_connection(conn, cursor)

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
