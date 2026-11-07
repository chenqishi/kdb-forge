#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
从SQL数据库获取聊天数据并转换为gen_knowledge_from_chat.py所需的格式
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('data_control_tools/get_data_from_sql.py')
import os
import sys
import json
import logging
import argparse
from datetime import datetime

# 添加项目根目录到sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
sys.path.append(project_root)

from commons.mysql_connector import MySQLConnector
from mysql.connector import Error

class ChatDataExtractor:
    """聊天数据提取器"""
    
    def __init__(self, mysql_config_path):
        """初始化提取器"""
        self.mysql_connector = MySQLConnector(mysql_config_path)
        
    def extract_chat_data(self, client, user, index, app_id, start_time, end_time, 
                         black_nick_name=None, need_process_name='all', mining_type='norm', 
                         scene_type='group'):
        """
        从数据库提取聊天数据
        
        Args:
            client: 客户名称
            user: 用户标识
            index: 索引名称（如果为None则使用client）
            app_id: 应用ID
            start_time: 开始时间
            end_time: 结束时间
            black_nick_name: 黑名单昵称（可选）
            need_process_name: 需要处理的名称（默认为all）
            mining_type: 挖掘类型（默认为norm）
            scene_type: 场景类型，可选值：'group'（群聊，默认）、'single'（单聊）、'group,single'（两者都选）
        
        Returns:
            tuple: (data_file_content, robot_room_type_config_content)
        """
        connection = self.mysql_connector.get_connection()
        if connection is None:
            logging.error("无法获取数据库连接")
            return None, None
        
        try:
            cursor = connection.cursor(dictionary=True)
            
            # 构建SQL查询
            sql = """
            SELECT 
                user,
                customer,
                session_id,
                msg_id,
                send_type,
                send_content,
                from_user_id,
                from_user_nickname,
                to_user_id,
                to_user_nickname,
                other_user_id,
                other_user_nickname,
                is_group,
                group_id,
                is_at,
                actual_user_id,
                actual_user_nickname,
                self_display_name,
                reply_type,
                reply_content,
                method_name,
                type,
                create_time,
                latest_time
            FROM data_chat_history 
            WHERE customer = %s 
            AND app_id = %s 
            AND create_time >= %s 
            AND create_time <= %s
            AND IFNULL(del_flag, 0) != 1
            """
            
            # 初始化参数列表
            params = [client, app_id, start_time, end_time]
            
            # 如果指定了黑名单昵称，添加过滤条件
            if black_nick_name:
                black_names = black_nick_name.split('|')
                black_conditions = []
                for name in black_names:
                    if name.strip():
                        black_conditions.append(f"from_user_nickname NOT LIKE %s")
                        params.append(f"%{name.strip()}%")
                if black_conditions:
                    sql += " AND (" + " AND ".join(black_conditions) + ")"
            
            # 根据scene_type添加群聊/单聊过滤条件
            scene_types = [s.strip().lower() for s in scene_type.split(',')]
            has_group = 'group' in scene_types
            has_single = 'single' in scene_types
            
            if has_group and not has_single:
                # 只选择群聊
                sql += " AND is_group = 1"
            elif has_single and not has_group:
                # 只选择单聊
                sql += " AND (is_group = 0 OR is_group IS NULL)"
            # 如果两者都选（has_group and has_single），则不添加过滤条件
            
            sql += " ORDER BY create_time ASC"
            
            logging.info(f"执行SQL查询: {sql}")
            logging.info(f"查询参数: {params}")
            
            cursor.execute(sql, params)
            results = cursor.fetchall()
            
            logging.info(f"查询到 {len(results)} 条聊天记录")
            
            # 转换为gen_knowledge_from_chat.py所需的格式
            data_file_content = self._convert_to_data_file_format(results, client, user)
            # 如果index为None，使用client作为index
            actual_index = index if index is not None else client
            robot_room_type_config_content = self._create_robot_room_type_config(
                user, need_process_name, actual_index, mining_type, black_nick_name
            )
            
            return data_file_content, robot_room_type_config_content
            
        except Error as e:
            logging.error(f"数据库查询失败: {e}")
            return None, None
        finally:
            self.mysql_connector.close_connection(connection, cursor)
    
    def _convert_to_data_file_format(self, results, client, user):
        """
        将数据库结果转换为gen_knowledge_from_chat.py的data_file格式
        
        格式：send_name\tmessage_time\tmessage_info_json
        """
        data_lines = []
        
        for row in results:
            try:
                # 构建消息信息
                message_info = {
                    'type': 'all',  # 默认为all类型
                    'send_name': row['from_user_nickname'] or row['from_user_id'],
                    'conent': row['send_content'],  # 注意：原代码中确实是conent，不是content
                    'original_info': {
                        'msg_id': row['msg_id'],
                        'is_group': bool(row['is_group']),
                        'from_user_id': row['from_user_id'],
                        'from_user_nickname': row['from_user_nickname'],
                        'other_user_id': row['other_user_id'],
                        'other_user_nickname': row['other_user_nickname'],
                        'ctype': row['send_type'],
                        'group_id': row['group_id'],
                        'is_at': bool(row['is_at']),
                        'actual_user_id': row['actual_user_id'],
                        'actual_user_nickname': row['actual_user_nickname'],
                        'self_display_name': row['self_display_name']
                    }
                }
                
                # 如果有回复内容，添加回复信息
                if row['reply_content']:
                    message_info['reply'] = {
                        'conent': row['reply_content'],  # 注意：原代码中确实是conent
                        'type': row['reply_type']
                    }
                
                # 格式化时间
                message_time = row['create_time'].strftime('%Y-%m-%d %H:%M:%S')
                
                # 构建数据行
                data_line = f"{message_info['send_name']}\t{message_time}\t{json.dumps(message_info, ensure_ascii=False)}"
                data_lines.append(data_line)
                
            except Exception as e:
                logging.warning(f"处理记录时出错: {e}, 记录: {row}")
                continue
        
        return '\n'.join(data_lines)
    
    def _create_robot_room_type_config(self, user, need_process_name, index, mining_type, black_nick_name):
        """
        创建robot_room_type_config_file内容
        
        格式：user\tneed_process_name\tindex\tmining_type\tblack_nick_name
        """
        black_nick_name_str = black_nick_name if black_nick_name else ""
        return f"{user}\t{need_process_name}\t{index}\t{mining_type}\t{black_nick_name_str}"

def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='从SQL数据库提取聊天数据')
    parser.add_argument('--mysql-config', required=True, help='MySQL配置文件路径')
    parser.add_argument('--client', required=True, help='客户名称')
    parser.add_argument('--user', required=True, help='用户标识')
    parser.add_argument('--index', help='索引名称（如果缺失则为client）')
    parser.add_argument('--app-id', required=True, help='应用ID')
    parser.add_argument('--start-time', required=True, help='开始时间 (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--end-time', required=True, help='结束时间 (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--black-nick-name', help='黑名单昵称')
    parser.add_argument('--need-process-name', default='all', help='需要处理的名称（默认为all）')
    parser.add_argument('--mining-type', default='norm', help='挖掘类型（默认为norm）')
    parser.add_argument('--scene-type', default='group', help='场景类型：group（群聊，默认）、single（单聊）、group,single（两者都选）')
    parser.add_argument('--output-data-file', required=True, help='输出数据文件路径')
    parser.add_argument('--output-config-file', required=True, help='输出配置文件路径')
    
    args = parser.parse_args()
    
    logging.info("开始从SQL数据库提取聊天数据...")
    logging.info(f"客户: {args.client}")
    logging.info(f"用户: {args.user}")
    logging.info(f"索引: {args.index if args.index else args.client}")
    logging.info(f"应用ID: {args.app_id}")
    logging.info(f"时间范围: {args.start_time} - {args.end_time}")
    
    # 创建提取器
    extractor = ChatDataExtractor(args.mysql_config)
    
    # 提取数据
    data_content, config_content = extractor.extract_chat_data(
        client=args.client,
        user=args.user,
        index=args.index,
        app_id=args.app_id,
        start_time=args.start_time,
        end_time=args.end_time,
        black_nick_name=args.black_nick_name,
        need_process_name=args.need_process_name,
        mining_type=args.mining_type,
        scene_type=args.scene_type
    )
    
    if data_content is None or config_content is None:
        logging.error("数据提取失败")
        sys.exit(1)
    
    # 保存数据文件
    try:
        os.makedirs(os.path.dirname(args.output_data_file), exist_ok=True)
        with open(args.output_data_file, 'w', encoding='utf-8') as f:
            f.write(data_content)
        logging.info(f"数据文件保存成功: {args.output_data_file}")
    except Exception as e:
        logging.error(f"保存数据文件失败: {e}")
        sys.exit(1)
    
    # 保存配置文件
    try:
        os.makedirs(os.path.dirname(args.output_config_file), exist_ok=True)
        with open(args.output_config_file, 'w', encoding='utf-8') as f:
            f.write(config_content)
        logging.info(f"配置文件保存成功: {args.output_config_file}")
    except Exception as e:
        logging.error(f"保存配置文件失败: {e}")
        sys.exit(1)
    
    logging.info("数据提取完成")

if __name__ == '__main__':
    main()
