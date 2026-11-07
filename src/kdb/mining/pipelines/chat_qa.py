#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
聊天QA挖掘任务控制脚本
基于原始的chatknowledge_process.sh脚本改造
支持从SQL数据库获取聊天数据并生成QA
"""
from kdb.shared.config.private_values import private_value as _private_value
import os
import sys
import json
import argparse
import logging
import subprocess
import shlex
import signal
import time
import traceback
import requests
from pathlib import Path

from kdb.shared.config.paths import SOURCE_ROOT, subprocess_env

from kdb.integrations.data_control.get_data_from_sql import ChatDataExtractor
from kdb.mining.tasks.task_status_updater import TaskStatusUpdater
from kdb.shared.config.legacy_config import GLOBAL_CONFIG
GLOBAL_BLACK_NICK_NAME = GLOBAL_CONFIG['chat_qa_mining_task_control_global_black_nick_name']
class ChatQAMiningTaskController:
    """聊天QA挖掘任务控制器"""
    
    def __init__(self, script_dir, task_id, task_info):
        """初始化控制器"""
        self.script_dir = script_dir
        self.task_id = task_id
        self.task_info = task_info
        
        # 配置路径
        self.config_dir = os.path.join(script_dir, 'config')
        self.mysql_config_path = os.path.join(self.config_dir, 'mysql_conn_config.json')
        
        # 工作目录
        self.data_dir = os.path.join(script_dir, 'data/off_task_data', task_id)
        self.log_dir = os.path.join(script_dir, 'log/off_task_log', task_id)
        
        # 确保目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 初始化工具
        self.data_extractor = ChatDataExtractor(self.mysql_config_path)
        self.status_updater = TaskStatusUpdater(self.mysql_config_path)
        
        # 任务配置
        self.client = task_info.get('client', '')
        self.user = task_info.get('user', '')
        self.index = task_info.get('index', None)  # 如果为None，则使用client
        self.app_id = task_info.get('app_id', '')
        self.start_time = task_info.get('start_time', '')
        self.end_time = task_info.get('end_time', '')
        self.black_nick_name = task_info.get('black_nick_name', None)
        self.black_nick_name = f"{self.black_nick_name}|{GLOBAL_BLACK_NICK_NAME}" if self.black_nick_name else GLOBAL_BLACK_NICK_NAME
        self.need_process_name = task_info.get('need_process_name', 'all')
        self.mining_type = task_info.get('mining_type', 'norm')
        self.scene_type = task_info.get('scene_type', 'group')  # 默认为群聊
        self.is_need_quality = task_info.get('is_need_quality', 1)  # 是否需要质量检测，默认为1
        self.index_name = task_info.get('index_name', '')
        task_category = task_info.get('category')
        if isinstance(task_category, dict):
            task_category_id = task_category.get('category_id') or task_category.get('categoryId')
            task_category_name = task_category.get('category_name') or task_category.get('categoryName')
        else:
            task_category_id = None
            task_category_name = task_category
        category_id = task_info.get('category_id') or task_info.get('categoryId') or task_category_id
        self.category_id = str(category_id) if category_id not in (None, '') else None
        self.category_name = (
            task_info.get('category_name') or task_info.get('categoryName') or task_category_name or None
        )
        
        # 处理全局黑名单
        
        
        # 中间文件路径
        self.data_file_path = os.path.join(self.data_dir, 'chat_data.txt')
        self.robot_data_map_file_path = os.path.join(self.data_dir, 'robot_data_map.txt')
        self.robot_room_type_config_path = os.path.join(self.data_dir, 'robot_room_type_config.txt')
        self.robot_room_process_record_path = os.path.join(self.data_dir, 'robot_room_process_record.txt')
        self.robot_room_white_name_path = os.path.join(self.data_dir, 'robot_room_white_name.txt')
        self.prompt_file_map_path = os.path.join(self.data_dir, 'prompt_file_map.txt')
        self.qa_file_path = os.path.join(self.data_dir, 'chatknowledege_extract_qa_batch.txt')
        self.qa_quality_file_path = os.path.join(self.data_dir, 'chatknowledege_extract_qa_quality_batch.txt')
        self.search_data_file_path = os.path.join(self.data_dir, 'chatknowledege_extract_qa_quality_batch_search_data.txt')
        self.llm_stats_file_path = os.path.join(self.data_dir, 'llm_call_stats.json')
        self.review_stats_file_path = os.path.join(self.data_dir, 'qa_review_stats.json')
        self.insert_result_file_path = os.path.join(self.data_dir, 'qa_insert_result.json')
        self.task_timeout_seconds = self._positive_int(
            task_info.get('task_timeout_seconds') or
            os.environ.get('CHAT_QA_TASK_TIMEOUT_SECONDS'),
            6 * 60 * 60
        )
        self.task_started_monotonic = None
    
        # 设置日志
        self._setup_logging()

    @staticmethod
    def _positive_int(raw_value, default):
        if raw_value in (None, ''):
            return default
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            logging.warning("任务超时配置 %r 非法，使用默认值 %s", raw_value, default)
            return default
        if value <= 0:
            logging.warning("任务超时配置 %r 必须大于 0，使用默认值 %s", raw_value, default)
            return default
        return value

    def _remaining_task_timeout_seconds(self):
        timeout_seconds = getattr(self, 'task_timeout_seconds', None)
        started_at = getattr(self, 'task_started_monotonic', None)
        if not timeout_seconds or started_at is None:
            return None
        return timeout_seconds - (time.monotonic() - started_at)
    
    def _generate_prompt_file(self):
        """生成prompt文件"""
        try:
            # 1. 请求获取config
            config_url = GLOBAL_CONFIG['app_config_get_url']
            config_url = config_url.format(app_id=self.app_id, client=self.client)
            #config_url = f"https://www.lufitglobalselling.com:8888/api/rufit-ai/intranet/ai/config/getRoleConfigList?appId={self.app_id}&client={self.client}"
            logging.info(f"请求配置URL: {config_url}")
            
            response = requests.get(config_url, timeout=30)
            response.raise_for_status()
            config_data = response.json()
            
            logging.info(f"获取配置成功: {config_data}")
            
            # 2. 获取peer, teacher, management的nickname组成colleague_names
            colleague_names = []
            if 'data' in config_data and isinstance(config_data['data'], list):
                for item in config_data['data']:
                    if isinstance(item, dict):
                        config_key = item.get('configKey', '')
                        config_value = item.get('configValue', '')
                        
                        if config_key in ['peer', 'teacher', 'management']:
                            if isinstance(config_value, list):
                                # 处理JSON格式的配置值
                                for user_info in config_value:
                                    if isinstance(user_info, dict):
                                        nickname = user_info.get('userName', '')
                                        if nickname:
                                            colleague_names.append(nickname)

                            elif isinstance(config_value, dict):
                                nickname = config_value.get('userName', '')
                                if nickname:
                                    colleague_names.append(nickname)

                            elif isinstance(config_value, str) and config_value.strip():
                                # 处理字符串格式的配置值
                                colleague_names.append(config_value.strip())
            
            colleague_names_str = ','.join(colleague_names)
            logging.info(f"同事名称: {colleague_names_str}")
            
            # 3. 获取chat_qa_mining_prompt，若没有则使用default prompt
            chat_qa_mining_prompt = None
            if 'data' in config_data and isinstance(config_data['data'], list):
                for item in config_data['data']:
                    if isinstance(item, dict) and item.get('configKey') == 'chat_qa_mining_prompt':
                        chat_qa_mining_prompt = item.get('configValue', '')
                        break
            
            # 默认prompt
            if not chat_qa_mining_prompt:
                return self._create_default_prompt(colleague_names_str)
            
            logging.info(f"使用prompt模板: {chat_qa_mining_prompt[:200]}...")
            
            # 4. 将{colleague}替换成colleague_names
            if "{colleague_names_str}" in chat_qa_mining_prompt:
                final_prompt = chat_qa_mining_prompt.format(colleague=colleague_names_str)
            else:
                final_prompt = chat_qa_mining_prompt
            
            # 5. 写入prompt_file
            prompt_file_path = os.path.join(self.data_dir, 'chat_qa_mining_prompt.txt')
            with open(prompt_file_path, 'w', encoding='utf-8') as f:
                f.write(final_prompt)
            
            logging.info(f"prompt文件生成成功: {prompt_file_path}")
            return prompt_file_path
            
        except requests.exceptions.RequestException as e:
            logging.error(f"请求配置失败: {e}")
            # 使用默认prompt
            return self._create_default_prompt("")
        except Exception as e:
            logging.error(f"生成prompt文件失败: {e}")
            traceback.print_exc()
            # 使用默认prompt
            return self._create_default_prompt("")
    
    def _create_default_prompt(self, colleague_names_str):
        """创建默认prompt文件"""
        try:
            if self.client.find('individual') != -1 and not colleague_names_str:
                default_prompt = """
  ## 任务
从我提供的客户与客服的真实对话记录中，提取出所有的有效的问答。把完整的客户的问题和客服回答摘抄下来，做成问答库

## 处理步骤及逻辑
1. 根据上下文分析哪句话是客户的提问，哪句话是对客户的回答。
2. 找到问题的答案
- 对每一个客户的问题，找到随后对应的客服的回答内容，把所有的回答完整地摘抄下来
- 如果对同一问题有多个回答且有矛盾的，则以时间最新的回答为准。
- 如果多个答案之间没有冲突，则将答案拼接在一起。
4. 输出结果：按照问题、答案、时间和说话对象的格式输出整理后的信息。并以"\n###\n"进行分隔。

# 示例
## 示例输入：
[2024-11-10 10:00:00, 小李]: 现在电商平台促销活动有哪些？
------
[2024-11-10 10:05:00, 小王]: 淘宝双11，京东618。
------
[2024-11-10 10:15:01, 小张]: 拼多多也有百亿补贴。
------
[2024-11-10 10:20:03, 小王]: 今年的淘宝双11活动力度特别大。
------
[2024-11-10 10:30:04, 小李]: 有哪些平台有满减活动？
------
[2024-11-10 10:35:06, 小王]: 京东和苏宁。
------
[2024-11-10 10:40:09, 小张]: 天猫也有。

## 示例输出：
问题: 现在电商平台促销活动有哪些？
答案: 淘宝双11, 京东618, 拼多多百亿补贴
来源: [小王], [小张]
###
问题: 今年的淘宝双11活动力度如何？
答案: 活动力度特别大
来源: [小王]
###
问题: 有哪些平台有满减活动？
答案: 天猫, 京东, 苏宁
来源: [小王], [小张]                
                """

            elif not colleague_names_str:
                default_prompt = """你是一个专业的客服知识提取助手。请根据以下聊天记录，提取出有价值的问答对。

    请从聊天记录中提取出以下类型的问答对：
    1. 客户常见问题及解答
    2. 产品相关信息问答
    3. 服务流程相关问答
    4. 技术问题及解决方案

    要求：
    - 问答对要准确、完整
    - 语言要专业、易懂
    - 每个问答对要独立成段
    - 用###分隔不同的问答对

    格式示例：
    ### 问题：客户询问产品价格
    答案：我们的产品价格根据配置不同而有所差异，具体价格请咨询销售团队。

    ### 问题：如何申请售后服务
    答案：您可以通过以下方式申请售后服务：1. 拨打客服热线 2. 发送邮件到售后邮箱 3. 在线提交工单"""

            else:
                default_prompt = """
#角色
你是一个公司的业务知识整理助手，需要从一些列对话中找出有用正确的qa知识。{colleague}是你的同事，他们的发言会包含答案。其他人都是你的客户，客户的发言会包含问题。

# 任务
## 现在给你一段群聊沟通记录，你需要按时间顺序从前往后观察沟通记录，然后从沟通记录中抽一个或多个问答知识。保持问题和答案的逻辑对应，最后输出问题和答案。
## 问题要从你的客户的表述中抽取出来代表性的那种问题。
## 答案要从你的同事的表述中抽取出来具有复用性的答案。

# 要求
1. 务必使用沟通记录的原话作为问题和答案，不要改写，不要扩写，保持原话的描述！
2. 你的同事们的回答，例如{colleague}等，他们的回答都是正确的答案。其他人的发言属于问题。
3. 一个沟通记录中可能有多个问题和答案，那就抽取多个问题和答案。问题就是Q，答案就是A。 并以"\n###\n"进行分隔
5. 务必确保问题的主语清晰明确，不含指代词，例如这，那，以上之类的。例如，沟通记录中如果同一个人连续发送两句，需要你考虑整合成一句完整的问句。例如，"这两个站点怎么入驻？"需要结合上下文分析具体是指代哪两个站点，进行完善，去掉指代。
6. 沟通记录中可能含有XML格式标注的脏数据，如果遇到可以忽视。
7. 出现开玩笑等闲聊的内容可以视为脏数据忽略，只抽取和跨境电商平台经营或者注册申请审核等等相关的信息。
8. 出现具体的业务内容可以视为脏数据忽略，因为他们不具有通用性，例如某客户的具体邮箱，电话，或者公司名字。
9. 其他情况，如果根据以上标准都抽取不来合适的Q和A，则不抽取，而是输出"all null"
10. 只有{colleague}的回答可以作为答案。

#输出格式
输出结果：按照问题、答案、时间和说话对象的格式输出整理后的信息。并以"\n###\n"进行分隔
示例输入：
[2024-11-10 10:00:00, 小李]: 现在电商平台促销活动有哪些？
------
[2024-11-10 10:05:00, {first_colleague}]: 淘宝双11，京东618。
------
[2024-11-10 10:15:01, 小张]: 拼多多也有百亿补贴。
------
[2024-11-10 10:20:03, {first_colleague}]: 今年的淘宝双11活动力度特别大。
------
[2024-11-10 10:30:04, 小李]: 有哪些平台有满减活动？
------
[2024-11-10 10:35:06, 小王]: 京东和苏宁。
------
[2024-11-10 10:40:09, 小张]: 天猫也有。
示例输出：
问题: 现在电商平台促销活动有哪些？
答案: 淘宝双11, 京东618
来源: [{first_colleague}]
###
问题: 今年的淘宝双11活动力度如何？
答案: 活动力度特别大
来源: [{first_colleague}]                
"""

            
            # 将{colleague}替换成colleague_names_str
            first_colleague = colleague_names_str.split(',')[0]
            final_prompt = default_prompt.format(colleague=colleague_names_str, first_colleague=first_colleague)
            logging.info(f"生成prompt: {final_prompt}")
            prompt_file_path = os.path.join(self.data_dir, 'chat_qa_mining_prompt.txt')
            with open(prompt_file_path, 'w', encoding='utf-8') as f:
                f.write(final_prompt)
            
            logging.info(f"默认prompt文件生成成功: {prompt_file_path}")
            return prompt_file_path
            
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"创建默认prompt文件失败: {e}")
            logging.error(f"错误堆栈: {tb}")
            
            return None
    
    def _setup_logging(self):
        """设置日志"""
        # 清除现有的handler，避免重复配置
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # 配置日志输出到标准输出，这样会被任务日志文件捕获
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)  # 确保输出到stdout
            ],
            force=True  # 强制重新配置
        )
    
    def _run_command(self, cmd, stage_name):
        """运行命令并记录日志"""
        log_file = os.path.join(self.log_dir, f'{stage_name}.log')
        llm_env_file = os.path.join(self.config_dir, 'chatknowledge_llm_env.sh')
        if os.path.exists(llm_env_file):
            cmd = f"set -a; . {shlex.quote(llm_env_file)}; set +a; {cmd}"
        cmd = f"export PYTHONPATH={shlex.quote(str(SOURCE_ROOT))}:$PYTHONPATH; {cmd}"
        logging.info(f"执行阶段: {stage_name}")
        logging.info(f"工作目录: {self.script_dir}")
        logging.info("=" * 80)
        logging.info(f"执行命令: {cmd}")
        logging.info("=" * 80)
        
        try:
            remaining_timeout = self._remaining_task_timeout_seconds()
            if remaining_timeout is not None and remaining_timeout <= 0:
                logging.error(
                    "任务已超过总时限 %s 秒，拒绝启动阶段 %s",
                    self.task_timeout_seconds,
                    stage_name
                )
                return False
            with open(log_file, 'w', encoding='utf-8') as f:
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=self.script_dir,
                    env=subprocess_env(),
                    start_new_session=True,
                )
                try:
                    process.wait(timeout=remaining_timeout)
                except subprocess.TimeoutExpired:
                    logging.error("终止超时阶段 %s 的进程组 pid=%s", stage_name, process.pid)
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    raise
            
            # 读取命令输出日志，打印一些关键信息
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_content = f.read(500)
                    if log_content.strip():
                        logging.info(f"阶段 {stage_name} 命令输出（前500字符）:")
                        logging.info(log_content[:500])
                    else:
                        logging.warning(f"阶段 {stage_name} 命令没有输出")
            
            if process.returncode == 0:
                logging.info(f"阶段 {stage_name} 执行成功，返回码: {process.returncode}")
                return True
            else:
                logging.error(f"阶段 {stage_name} 执行失败，返回码: {process.returncode}")
                # 如果有错误日志，显示更多信息
                if os.path.exists(log_file):
                    with open(log_file, 'rb') as f:
                        f.seek(max(os.path.getsize(log_file) - 4000, 0))
                        error_content = f.read(4000).decode('utf-8', errors='replace')
                        if error_content.strip():
                            logging.error(f"错误详情: {error_content[-1000:]}")  # 显示最后1000字符
                return False
                
        except subprocess.TimeoutExpired:
            logging.error(
                "阶段 %s 超时；任务总时限为 %s 秒",
                stage_name,
                getattr(self, 'task_timeout_seconds', '未配置')
            )
            return False
        except Exception as e:
            logging.error(f"执行阶段 {stage_name} 时发生异常: {e}")
            traceback.print_exc()
            return False
    
    def stage_1_extract_data_from_sql(self):
        """阶段1：从SQL数据库提取聊天数据"""
        self.status_updater.update_task_stage(self.task_id, "data_extraction")
        logging.info("开始阶段1：从SQL数据库提取聊天数据")
        
        try:
            # 从SQL数据库提取数据
            data_content, config_content = self.data_extractor.extract_chat_data(
                client=self.client,
                user=self.user,
                index=self.index,
                app_id=self.app_id,
                start_time=self.start_time,
                end_time=self.end_time,
                black_nick_name=self.black_nick_name,
                need_process_name=self.need_process_name,
                mining_type=self.mining_type,
                scene_type=self.scene_type
            )
            
            if data_content is None or config_content is None:
                logging.error("从SQL数据库提取数据失败")
                return False
            
            # 保存数据文件
            with open(self.data_file_path, 'w', encoding='utf-8') as f:
                f.write(data_content)
            
            # 保存配置文件
            with open(self.robot_room_type_config_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            
            # 创建robot_data_map_file，格式为robot_name\tclient\tdata_file
            robot_data_map_content = f"{self.user}\t{self.client}\t1\t{self.data_file_path}"
            with open(self.robot_data_map_file_path, 'w', encoding='utf-8') as f:
                f.write(robot_data_map_content)
            
            # 创建空的处理记录文件和白名单文件
            with open(self.robot_room_process_record_path, 'w', encoding='utf-8') as f:
                f.write("")
            
            with open(self.robot_room_white_name_path, 'w', encoding='utf-8') as f:
                f.write("")
            
            # 生成prompt文件
            prompt_file_path = self._generate_prompt_file()
            if not prompt_file_path:
                logging.error("生成prompt文件失败")
                return False
            
            # 使用任务私有prompt映射，避免并发任务覆盖全局config/prompt_file_map.txt。
            with open(self.prompt_file_map_path, 'w', encoding='utf-8') as f:
                f.write(f"{self.client}\t{prompt_file_path}")
            
            # 统计数据量
            data_lines = data_content.strip().split('\n') if data_content.strip() else []
            logging.info(f"数据提取阶段完成，共提取 {len(data_lines)} 条聊天记录")
            logging.info(f"robot_data_map_file: {robot_data_map_content}")
            logging.info(f"prompt文件生成完成: {prompt_file_path}")
            return True
            
        except Exception as e:
            logging.error(f"数据提取阶段发生异常: {e}")
            traceback.print_exc()
            return False
    
    def stage_2_generate_qa(self):
        """阶段2：生成QA"""
        self.status_updater.update_task_stage(self.task_id, "qa_generation")
        logging.info("开始阶段2：生成QA")
        
        try:
            # 构建命令，使用robot_data_map_file
            cmd = f"""{shlex.quote(sys.executable)} -m kdb.mining.generation.chatknowledge.gen_knowledge_from_chat run_batch_robot_chat_data \
                --data_file={self.robot_data_map_file_path} \
                --output_dir={self.data_dir} \
                --data_file_field_num=3 \
                --robot_room_type_config_file={self.robot_room_type_config_path} \
                --robot_process_record_file={self.robot_room_process_record_path} \
                --robot_white_list_file={self.robot_room_white_name_path} \
                --filter_group_name=all \
                --prompt_file_map={self.prompt_file_map_path} \
                --llm_stats_file={self.llm_stats_file_path} \
                --flag={self.task_id}"""
            
            # 修改命令，将stdout重定向到qa_file_path文件
            cmd_with_output = f"{cmd} > {self.qa_file_path}"
            
            if self._run_command(cmd_with_output, "qa_generation"):
                # 检查输出文件是否存在
                if os.path.exists(self.qa_file_path):
                    logging.info(f"QA生成阶段完成，输出文件: {self.qa_file_path}")
                    return True
                else:
                    logging.error("QA生成阶段失败：未找到输出文件")
                    return False
            else:
                logging.error("QA生成阶段失败")
                return False
            
        except Exception as e:
            logging.error(f"QA生成阶段发生异常: {e}")
            traceback.print_exc()
            return False
    
    def stage_3_qa_quality(self):
        """阶段3：独立模型质量审核（失败关闭，不会误入库）。"""
        self.status_updater.update_task_stage(self.task_id, "qa_quality")
        logging.info("开始阶段3：QA独立质量审核")
        
        cmd = f"""{shlex.quote(sys.executable)} -m kdb.mining.quality.chat_qa_extract.reviewer review_batch \
                --batch_file={shlex.quote(self.qa_file_path)} \
                --output_batch_file={shlex.quote(self.qa_quality_file_path)} \
                --process_field_num=4 \
                --client={shlex.quote(self.client)} \
                --stats_file={shlex.quote(self.review_stats_file_path)}"""
        
        if self._run_command(cmd, "qa_quality"):
            logging.info("QA质量处理阶段完成")
            return True
        else:
            logging.error("QA质量处理阶段失败")
            return False
    
    def stage_4_schema_transform(self):
        """阶段4：ES Schema转换"""
        self.status_updater.update_task_stage(self.task_id, "schema_transform")
        logging.info("开始阶段4：ES Schema转换")
        
        cmd = f"""{shlex.quote(sys.executable)} -m kdb.mining.transformations.schema_trans batch_trans_qa_to_search_data \
            --batch_file={self.qa_quality_file_path} \
            --output_file={self.search_data_file_path} \
            --field_num=5 \
            --platform_field_num=1 \
            --from_type=chat_auto \
            --task-id={self.task_id}"""

        # 兼容 webhook/手工任务传入的 category。Payoneer Olive 会用平台名作为类目名。
        if self.category_id:
            cmd += f" --category_id={shlex.quote(self.category_id)}"
        if self.category_name:
            cmd += f" --category_name={shlex.quote(str(self.category_name))}"
        
        if self._run_command(cmd, "schema_transform"):
            logging.info("ES Schema转换阶段完成")
            return True
        else:
            logging.error("ES Schema转换阶段失败")
            return False

    def _normalize_scope_name(self, value):
        return str(value or '').strip().lower()

    def _iter_search_data_scope_errors(self, target_index_name):
        """
        校验待写ES文件的client/platform归属，防止A客户数据写入B客户索引。
        空结果文件视为正常；只有实际待写数据才校验。
        """
        expected_client = self._normalize_scope_name(self.client)
        target_index = self._normalize_scope_name(target_index_name)
        allow_cross_client_index = str(
            self.task_info.get('allow_cross_client_index', '')
        ).strip().lower() in {'1', 'true', 'yes'}

        if not os.path.exists(self.search_data_file_path):
            yield f"search_data_file_not_found: {self.search_data_file_path}"
            return

        if expected_client and target_index and target_index != expected_client and not allow_cross_client_index:
            yield f"target_index_mismatch: target_index={target_index_name}, expected_client={self.client}"

        with open(self.search_data_file_path, 'r', encoding='utf-8') as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception as e:
                    yield f"invalid_json line={line_no}: {e}"
                    continue

                ext_info = data.get('ext_info') if isinstance(data.get('ext_info'), dict) else {}
                scope_values = {
                    'platform': data.get('platform'),
                    'client': data.get('client'),
                    'ext_info.client': ext_info.get('client'),
                }
                for field_name, raw_value in scope_values.items():
                    value = self._normalize_scope_name(raw_value)
                    if value and expected_client and value != expected_client:
                        yield (
                            f"scope_mismatch line={line_no} field={field_name} "
                            f"value={raw_value} expected_client={self.client}"
                        )

    def _validate_search_data_client_scope(self, target_index_name):
        errors = list(self._iter_search_data_scope_errors(target_index_name))
        if errors:
            logging.error("ES写入前client归属校验失败，阻断写入: %s", errors[:20])
            return False
        logging.info("ES写入前client归属校验通过: client=%s, target_index=%s", self.client, target_index_name)
        return True
    
    def stage_5_insert_index(self):
        """阶段5：ES插入索引"""
        self.status_updater.update_task_stage(self.task_id, "index_insert")
        logging.info("开始阶段5：ES插入索引")
        
        # 生成索引配置文件路径
        index_config_path = os.path.join(self.config_dir, f'{self.client}_config.json')
        if not os.path.exists(index_config_path):
            logging.warning(f"索引配置文件不存在: {index_config_path}，尝试使用默认配置")
            # 可以尝试使用通用配置文件
            default_configs = [
                os.path.join(self.config_dir, 'config_for_search_index.json'),
                os.path.join(self.config_dir, 'index_config.json')
            ]
            for config in default_configs:
                if os.path.exists(config):
                    index_config_path = config
                    break
            else:
                logging.error("找不到可用的索引配置文件")
                return False
        
        target_index_name = self.index_name or self.index or self.client
        logging.info(f"ES目标索引: {target_index_name}")
        if not self._validate_search_data_client_scope(target_index_name):
            return False
        cmd = f"""{shlex.quote(sys.executable)} -m kdb.retrieval.application.search_index_data_interface insert_data_to_search_index \
            --data_file={self.search_data_file_path} \
            --config_path={index_config_path} \
            --index_name_assign={target_index_name} \
            --is_only_title=true \
            --allowed_quality_levels=high \
            --required_review_decision=accept \
            --result_file={shlex.quote(self.insert_result_file_path)}"""
        
        if self._run_command(cmd, "index_insert"):
            logging.info("ES插入索引阶段完成")
            return True
        else:
            logging.error("ES插入索引阶段失败")
            return False
    
    def predict_credits(self):
        """预测任务成本（阶段开始前）"""
        logging.info("开始预测任务成本...")
        try:
            # 当前无逻辑，直接在SQL填-1
            self.status_updater.update_predict_credits(self.task_id, -1)
            logging.info("任务预测成本已设置为 -1")
            return True
        except Exception as e:
            logging.error(f"预测任务成本失败: {e}")
            traceback.print_exc()
            return False
    
    def calculate_credits(self):
        """计算任务实际成本（阶段结束后）"""
        logging.info("开始计算任务实际成本...")
        
        try:
            # 检查数据文件是否存在
            if not os.path.exists(self.data_file_path):
                logging.warning(f"数据文件不存在: {self.data_file_path}")
                # 如果文件不存在，成本为0
                actual_credits = 0
            else:
                # 读取数据文件，统计消息条数（非空行数）
                with open(self.data_file_path, 'r', encoding='utf-8') as f:
                    message_count = sum(1 for line in f if line.strip())
                
                # 实际成本 = 消息条数
                actual_credits = message_count
            
            # 更新数据库中的实际成本
            self.status_updater.update_actual_credits(self.task_id, actual_credits)
            
            logging.info(f"任务实际成本计算完成: 消息条数={actual_credits}, 实际成本={actual_credits}")
            return True
            
        except Exception as e:
            logging.error(f"计算任务实际成本时发生异常: {e}")
            traceback.print_exc()
            return False
    
    def count_qa_results(self):
        """统计候选、审核、查重和真实入库口径。"""
        logging.info("开始统计任务结果...")

        llm_call_stats = {}
        llm_stats_file_path = getattr(self, 'llm_stats_file_path', '')
        if llm_stats_file_path and os.path.exists(llm_stats_file_path):
            try:
                with open(llm_stats_file_path, 'r', encoding='utf-8') as f:
                    llm_call_stats = (json.load(f).get('totals') or {})
            except Exception as e:
                logging.warning("读取 LLM 调用统计失败: %s", e)

        review_stats = {}
        if os.path.exists(self.review_stats_file_path):
            try:
                with open(self.review_stats_file_path, 'r', encoding='utf-8') as f:
                    review_stats = json.load(f)
            except Exception as e:
                logging.warning("读取 QA 审核统计失败: %s", e)

        insert_stats = {}
        if os.path.exists(self.insert_result_file_path):
            try:
                with open(self.insert_result_file_path, 'r', encoding='utf-8') as f:
                    insert_stats = json.load(f)
            except Exception as e:
                logging.warning("读取 QA 入库统计失败: %s", e)
        
        if not os.path.exists(self.search_data_file_path):
            logging.warning(f"统计文件不存在: {self.search_data_file_path}")
            return {
                "qa_num": int(insert_stats.get('insert_success_num') or 0),
                "metrics_complete": bool(insert_stats),
                "llm_call_stats": llm_call_stats,
                "review_stats": review_stats,
                "insert_stats": insert_stats,
            }
        
        try:
            total_count = 0
            quality_counts = {'high': 0, 'mid': 0, 'low': 0}
            decision_counts = {'accept': 0, 'review': 0, 'reject': 0}
            
            with open(self.search_data_file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        total_count += 1
                        quality_level = data.get('quality_level', '')
                        if quality_level in quality_counts:
                            quality_counts[quality_level] += 1
                        review_decision = data.get('review_decision') or data.get('ext_info', {}).get('review_decision')
                        if review_decision in decision_counts:
                            decision_counts[review_decision] += 1
                            
                    except json.JSONDecodeError as e:
                        logging.warning(f"第{line_num}行JSON解析失败: {e}")
                        continue
            
            insert_success_num = int(insert_stats.get('insert_success_num') or 0)
            result = {
                # 保留 qa_num 给旧消费方，但修正语义为“真实成功入库数”。
                "qa_num": insert_success_num,
                "metrics_complete": bool(insert_stats),
                "extracted_candidate_num": int(review_stats.get('extracted_candidate_num') or total_count),
                "high_candidate_num": quality_counts['high'],
                "mid_candidate_num": quality_counts['mid'],
                "low_candidate_num": quality_counts['low'],
                "review_accept_num": decision_counts['accept'],
                "review_pending_num": decision_counts['review'],
                "review_reject_num": decision_counts['reject'],
                "insert_attempt_num": int(insert_stats.get('insert_attempt_num') or 0),
                "insert_success_num": insert_success_num,
                "duplicate_skip_num": int(insert_stats.get('duplicate_skip_num') or 0),
                "gate_skip_num": int(insert_stats.get('gate_skip_num') or 0),
                "insert_failure_num": int(insert_stats.get('insert_failure_num') or 0),
                "llm_call_stats": llm_call_stats,
                "review_stats": review_stats,
                "insert_stats": insert_stats,
            }
            logging.info("统计完成: candidate=%s accept=%s inserted=%s duplicate_skip=%s gate_skip=%s",
                         total_count, decision_counts['accept'], insert_success_num,
                         result['duplicate_skip_num'], result['gate_skip_num'])
            return result
            
        except Exception as e:
            logging.error(f"统计任务结果时发生异常: {e}")
            traceback.print_exc()
            return {
                "qa_num": int(insert_stats.get('insert_success_num') or 0),
                "metrics_complete": False,
                "llm_call_stats": llm_call_stats,
                "review_stats": review_stats,
                "insert_stats": insert_stats,
            }

    def run_all_stages(self):
        """运行所有阶段"""
        logging.info(f"开始执行任务: {self.task_id}")
        self.task_started_monotonic = time.monotonic()
        
        # 阶段开始前，预测成本
        logging.info("=" * 100)
        logging.info("阶段开始前：预测任务成本")
        logging.info("=" * 100)
        self.predict_credits()
        
        stages = [
            ("数据提取", self.stage_1_extract_data_from_sql),
            ("QA生成", self.stage_2_generate_qa),
            ("QA质量处理", self.stage_3_qa_quality),
            ("ES Schema转换", self.stage_4_schema_transform),
            ("ES插入索引", self.stage_5_insert_index),
        ]
        
        try:
            for stage_name, stage_func in stages:
                remaining_timeout = self._remaining_task_timeout_seconds()
                if remaining_timeout is not None and remaining_timeout <= 0:
                    logging.error(
                        "任务超过总时限 %s 秒，终止于阶段 %s 之前",
                        self.task_timeout_seconds,
                        stage_name
                    )
                    self.status_updater.update_task_run_status(self.task_id, 1, "timeout")
                    return False
                logging.info("=" * 100)
                logging.info(f"开始执行阶段: {stage_name}")
                logging.info("=" * 100)
                success = stage_func()
                
                if not success:
                    logging.error("=" * 100)
                    logging.error(f"阶段 {stage_name} 执行失败，任务终止")
                    logging.error("=" * 100)
                    self.status_updater.update_task_run_status(self.task_id, 1, "error")
                    return False
                
                logging.info("=" * 100)
                logging.info(f"阶段 {stage_name} 执行完成")
                logging.info("=" * 100)
            
            # 所有阶段完成后，计算实际成本
            logging.info("=" * 100)
            logging.info("阶段结束后：计算任务实际成本")
            logging.info("=" * 100)
            self.calculate_credits()
            
            # 所有阶段完成，统计任务结果
            logging.info("=" * 100)
            logging.info("开始统计任务结果...")
            logging.info("=" * 100)
            
            task_result = self.count_qa_results()
            task_result_json = json.dumps(task_result, ensure_ascii=False)
            
            # 更新任务结果到数据库
            result_update_success = self.status_updater.update_task_result(self.task_id, task_result_json)
            if result_update_success:
                logging.info(f"任务结果更新成功: {task_result_json}")
            else:
                logging.warning("任务结果更新失败，但任务执行成功")
            
            # 更新任务状态为完成
            logging.info("所有阶段执行完成，任务成功")
            self.status_updater.update_task_run_status(self.task_id, 3, "completed")
            return True
            
        except Exception as e:
            logging.error(f"执行任务时发生异常: {e}")
            traceback.print_exc()
            self.status_updater.update_task_run_status(self.task_id, -1, "error")
            return False

def main():
    """主函数"""
    # 先配置基础日志，确保早期日志能够输出
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True
    )
    
    parser = argparse.ArgumentParser(description='聊天QA挖掘任务控制脚本')
    parser.add_argument('--script-dir', required=True, help='脚本根目录路径')
    parser.add_argument('--task-id', required=True, help='任务ID')
    parser.add_argument('--task-info', required=True, help='任务信息JSON字符串')
    
    args = parser.parse_args()
    
    logging.info("=== 聊天QA挖掘任务脚本启动 ===")
    logging.info(f"脚本目录: {args.script_dir}")
    logging.info(f"任务ID: {args.task_id}")
    logging.info(f"任务信息: {args.task_info}")
    
    try:
        # 解析任务信息
        task_info = json.loads(args.task_info)
        logging.info("任务信息解析成功")
        
        # 创建任务控制器
        logging.info("正在创建任务控制器...")
        controller = ChatQAMiningTaskController(
            args.script_dir,
            args.task_id,
            task_info
        )
        logging.info("任务控制器创建成功")
        
        # 运行所有阶段
        logging.info("开始运行所有阶段...")
        success = controller.run_all_stages()
        
        if success:
            logging.info("=== 任务执行成功完成 ===")
        else:
            logging.error("=== 任务执行失败 ===")
        
        sys.exit(0 if success else 1)
        
    except json.JSONDecodeError as e:
        logging.error(f"任务信息JSON解析失败: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"脚本执行发生异常: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
