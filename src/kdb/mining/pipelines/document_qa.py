#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
文档QA挖掘任务控制脚本
基于原始的platform_knowledge_generate_from_raw_document.sh脚本改造
支持从远程文件系统（MinIO等）下载文件并生成QA
"""
import os
import sys
import json
import argparse
import logging
import subprocess
import shlex
import traceback
from pathlib import Path

from kdb.shared.config.paths import SOURCE_ROOT, subprocess_env

from kdb.mining.tasks.minio_downloader import MinioDownloader
from kdb.mining.tasks.task_status_updater import TaskStatusUpdater
from kdb.mining.parsing.document_clear_price_access import access_document_clear_price

class DocumentQAMiningTaskController:
    """文档QA挖掘任务控制器"""
    
    def __init__(self, script_dir, task_id, task_info):
        """初始化控制器"""
        self.script_dir = script_dir
        self.task_id = task_id
        self.task_info = task_info
        
        # 配置路径
        self.config_dir = os.path.join(script_dir, 'config')
        self.mysql_config_path = os.path.join(self.config_dir, 'mysql_conn_config.json')
        self.minio_config_path = os.path.join(self.config_dir, 'minio_config.json')
        
        # 工作目录
        self.data_dir = os.path.join(script_dir, 'data/off_task_data', task_id)
        self.log_dir = os.path.join(script_dir, 'log/off_task_log', task_id)
        
        # 确保目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 初始化工具
        self.downloader = MinioDownloader(self.minio_config_path)
        self.status_updater = TaskStatusUpdater(self.mysql_config_path)
        
        # 任务配置
        self.files = task_info.get('files', [])
        self.index_name = task_info.get('index_name', '')
        self.need_translate = task_info.get('need_translate', 0)
        self.client = task_info.get('client', self.index_name)
        # 确保 category_id 是字符串类型（避免纯数字被解析为 int）
        category_id = task_info.get('category_id')
        self.category_id = str(category_id) if category_id is not None else None
        self.category_name = task_info.get('category_name')
        
        # 中间文件路径
        self.file_mapping_path = os.path.join(self.data_dir, 'file_mapping.txt')
        self.content_mapping_path = os.path.join(self.data_dir, 'content_mapping.txt')
        self.translated_mapping_path = os.path.join(self.data_dir, 'translated_mapping.txt')
        self.qa_file_path = os.path.join(self.data_dir, 'all_clear_qa_file.txt')
        self.reclear_qa_file_path = os.path.join(self.data_dir, 'all_reclear_qa_file.txt')
        self.search_data_file_path = os.path.join(self.data_dir, 'all_reclear_qa_file_search_data.txt')
        
        # 设置日志
        self._setup_logging()
    
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
        """运行命令并记录日志。cmd 可以是字符串（shell=True）或参数列表（shell=False）。"""
        log_file = os.path.join(self.log_dir, f'{stage_name}.log')
        logging.info(f"执行阶段: {stage_name}")
        logging.info(f"工作目录: {self.script_dir}")
        logging.info("=" * 80)
        logging.info(f"执行命令: {cmd}")
        logging.info("=" * 80)

        use_shell = isinstance(cmd, str)

        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                result = subprocess.run(
                    cmd,
                    shell=use_shell,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=self.script_dir,
                    env=subprocess_env(),
                )
            
            # 读取命令输出日志，打印一些关键信息
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_content = f.read(500)
                    if log_content.strip():
                        logging.info(f"阶段 {stage_name} 命令输出（前500字符）:")
                        logging.info(log_content[:500])
                    else:
                        logging.warning(f"阶段 {stage_name} 命令没有输出")
            
            if result.returncode == 0:
                logging.info(f"阶段 {stage_name} 执行成功，返回码: {result.returncode}")
                return True
            else:
                logging.error(f"阶段 {stage_name} 执行失败，返回码: {result.returncode}")
                # 如果有错误日志，显示更多信息
                if os.path.exists(log_file):
                    with open(log_file, 'rb') as f:
                        f.seek(max(os.path.getsize(log_file) - 4000, 0))
                        error_content = f.read(4000).decode('utf-8', errors='replace')
                        if error_content.strip():
                            logging.error(f"错误详情: {error_content[-1000:]}")  # 显示最后1000字符
                return False
                
        except Exception as e:
            logging.error(f"执行阶段 {stage_name} 时发生异常: {e}")
            traceback.print_exc()
            return False
    
    def stage_1_download_files(self):
        """阶段1：文件下载"""
        self.status_updater.update_task_stage(self.task_id, "file_download")
        logging.info("开始阶段1：文件下载")
        
        try:
            downloaded_files = []
            
            for file_info in self.files:
                file_name = file_info.get('name', '')
                file_ext = file_info.get('ext', '')
                store_method = file_info.get('store_method', '')
                address = file_info.get('address', '')
                
                if not file_name or not address:
                    logging.warning(f"文件信息不完整，跳过: {file_info}")
                    continue
                
                # 生成本地文件路径
                local_filename = f"{file_name}.{file_ext}" if file_ext else file_name
                local_path = os.path.join(self.data_dir, 'downloaded_files', local_filename)
                
                # 下载文件
                logging.info(f"开始下载文件: {file_name}")
                logging.info(f"存储方式: {store_method}, 地址: {address}")
                logging.info(f"本地路径: {local_path}")
                
                success = self.downloader.download_file(file_info, local_path)
                
                if success and os.path.exists(local_path):
                    # 记录文件映射：{platform}\t{file_name}\t{file_ext}\t{file_path}
                    mapping_line = f"{self.client}\t{file_name}\t{file_ext}\t{local_path}"
                    downloaded_files.append(mapping_line)
                    logging.info(f"文件下载成功: {file_name} -> {local_path}")
                else:
                    logging.error(f"文件下载失败: {file_name}")
                    return False
            
            # 保存文件映射
            with open(self.file_mapping_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(downloaded_files))
            
            logging.info(f"文件下载阶段完成，共下载 {len(downloaded_files)} 个文件")
            return True
            
        except Exception as e:
            logging.error(f"文件下载阶段发生异常: {e}")
            traceback.print_exc()
            return False
    
    def stage_2_parse_documents(self):
        """阶段2：文件解析"""
        self.status_updater.update_task_stage(self.task_id, "document_parse")
        logging.info("开始阶段2：文件解析")
        
        try:
            # 使用batch_map_files_trans函数进行批量文件解析
            # 该函数接受文件映射文件作为输入，输出内容映射文件
            # 文件映射格式：{platform}\t{file_name}\t{file_ext}\t{file_path}
            # file_path位于第3列（从0开始计数）
            file_path_field = 3
            cmd = [
                sys.executable,
                '-m', 'kdb.mining.generation.processing.wordtotext',
                'batch_map_files_trans',
                f'--wait_process_file={self.file_mapping_path}',
                f'--output_file={self.content_mapping_path}',
                f'--file_path_field={file_path_field}',
            ]
            
            if self._run_command(cmd, "document_parse"):
                # 检查输出文件是否存在
                if os.path.exists(self.content_mapping_path):
                    # 统计解析的文件数量
                    with open(self.content_mapping_path, 'r', encoding='utf-8') as f:
                        parsed_count = sum(1 for line in f if line.strip())
                    
                    logging.info(f"文件解析阶段完成，共解析 {parsed_count} 个文件")
                    return True
                else:
                    logging.error("文档解析失败：输出文件不存在")
                    return False
            else:
                logging.error("文档解析阶段失败")
                return False
            
        except Exception as e:
            logging.error(f"文件解析阶段发生异常: {e}")
            traceback.print_exc()
            return False
    
    def stage_3_translate_documents(self):
        """阶段3：文本翻译（可选）"""
        if self.need_translate != 1:
            logging.info("跳过翻译阶段（need_translate != 1）")
            # 直接复制内容映射文件
            import shutil
            shutil.copy2(self.content_mapping_path, self.translated_mapping_path)
            return True
            
        self.status_updater.update_task_stage(self.task_id, "document_translate")
        logging.info("开始阶段3：文本翻译")
        
        cmd = f"{shlex.quote(sys.executable)} -m kdb.mining.generation.processing.knowledge_translate_by_dify run_batch_translate_pdf_json_content {self.content_mapping_path}"
        
        if self._run_command(cmd, "translate"):
            # 翻译成功，检查可能的输出文件位置
            possible_outputs = [
                os.path.join(self.data_dir, 'translated_content_mapping.txt'),
                f"{self.content_mapping_path}_translated.txt",
                os.path.join(self.script_dir, 'data', f'{self.task_id}_translated.txt')
            ]
            
            output_found = False
            for translated_output in possible_outputs:
                if os.path.exists(translated_output):
                    import shutil
                    shutil.move(translated_output, self.translated_mapping_path)
                    logging.info(f"翻译文件移动成功: {translated_output} -> {self.translated_mapping_path}")
                    output_found = True
                    break
            
            if not output_found:
                # 如果没有生成翻译文件，使用原文件
                import shutil
                shutil.copy2(self.content_mapping_path, self.translated_mapping_path)
                logging.info("未找到翻译输出文件，使用原始内容映射文件")
            
            logging.info("文本翻译阶段完成")
            return True
        else:
            logging.error("文本翻译阶段失败")
            return False
    
    def stage_4_generate_qa(self):
        """阶段4：QA生成"""
        self.status_updater.update_task_stage(self.task_id, "qa_generation")
        logging.info("开始阶段4：QA生成")
        
        # 确定输入文件
        input_file = self.translated_mapping_path if os.path.exists(self.translated_mapping_path) else self.content_mapping_path
        
        # 计算文件名字段位置（从0开始计数）
        # 映射格式：{platform}\t{file_name}\t{file_path}\t{content_json_path}
        # file_name在第1列（索引1）
        file_name_field_num = 1
        data_file = self.qa_file_path
        log_file = self.log_dir + '/qa_generation.log'
        cmd = f"{shlex.quote(sys.executable)} -m kdb.mining.generation.processing.knowledge_clear_by_dify_model_longcontent run_batch_clear_pdf_json_content {input_file} {self.task_id} {file_name_field_num} 1>{data_file} 2>{log_file}"
        
        if self._run_command(cmd, "qa_generation"):
            # 检查可能的输出文件位置
            possible_outputs = [
                os.path.join(self.data_dir, 'all_clear_qa_file.txt'),
                os.path.join(self.script_dir, 'data', 'all_clear_qa_file.txt'),
                os.path.join(self.script_dir, f'data/all_clear_qa_file_{self.task_id}.txt')
            ]
            
            output_found = False
            for expected_output in possible_outputs:
                if os.path.exists(expected_output):
                    import shutil
                    if expected_output != self.qa_file_path:
                        shutil.move(expected_output, self.qa_file_path)
                    logging.info(f"QA生成阶段完成，输出文件: {expected_output}")
                    output_found = True
                    break
            
            if output_found:
                return True
            else:
                logging.error("QA生成阶段失败：未找到输出文件")
                return False
        else:
            logging.error("QA生成阶段失败")
            return False
    
    def stage_5_qa_quality(self):
        """阶段5：QA质量处理"""
        self.status_updater.update_task_stage(self.task_id, "qa_quality")
        logging.info("开始阶段5：QA质量处理")
        
        cmd = f"{shlex.quote(sys.executable)} -m kdb.mining.quality.qa_quality_tools run_batch_re_clear_qa_info --input_file={self.qa_file_path} --output_file={self.reclear_qa_file_path} --process_field_num=-1"
        
        if self._run_command(cmd, "qa_quality"):
            logging.info("QA质量处理阶段完成")
            return True
        else:
            logging.error("QA质量处理阶段失败")
            return False
    
    def stage_6_schema_transform(self):
        """阶段6：ES Schema转换"""
        self.status_updater.update_task_stage(self.task_id, "schema_transform")
        logging.info("开始阶段6：ES Schema转换")
        
        cmd = f"{shlex.quote(sys.executable)} -m kdb.mining.transformations.schema_trans batch_trans_qa_to_search_data --batch_file={self.reclear_qa_file_path} --output_file={self.search_data_file_path} --field_num=9 --platform_field_num=0"
        
        # 添加task_id参数
        if self.task_id:
            cmd += f" --task_id={self.task_id}"
        
        # 添加类目参数（如果存在）
        if self.category_id:
            cmd += f" --category_id={self.category_id}"
        if self.category_name:
            cmd += f" --category_name='{self.category_name}'"
        
        if self._run_command(cmd, "schema_transform"):
            logging.info("ES Schema转换阶段完成")
            return True
        else:
            logging.error("ES Schema转换阶段失败")
            return False
    
    def stage_7_insert_index(self):
        """阶段7：ES插入索引"""
        self.status_updater.update_task_stage(self.task_id, "index_insert")
        logging.info("开始阶段7：ES插入索引")
        
        # 生成索引配置文件路径
        index_config_path = os.path.join(self.config_dir, f'{self.index_name}_config.json')
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
        
        cmd = f"{shlex.quote(sys.executable)} -m kdb.retrieval.application.search_index_data_interface insert_data_to_search_index --data_file={self.search_data_file_path} --config_path={index_config_path} --index_name_assign={self.index_name}"
        
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
            # 检查文件映射文件是否存在
            if not os.path.exists(self.file_mapping_path):
                logging.warning(f"文件映射文件不存在: {self.file_mapping_path}")
                return False
            
            # 读取文件映射，获取所有下载的文件路径
            downloaded_file_paths = []
            with open(self.file_mapping_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    # 文件映射格式：{platform}\t{file_name}\t{file_ext}\t{file_path}
                    parts = line.split('\t')
                    if len(parts) >= 4:
                        file_path = parts[3]  # file_path在第3列（索引3）
                        if os.path.exists(file_path):
                            downloaded_file_paths.append(file_path)
                        else:
                            logging.warning(f"文件不存在，跳过: {file_path}")
            
            if not downloaded_file_paths:
                logging.warning("没有找到已下载的文件")
                return False
            
            logging.info(f"找到 {len(downloaded_file_paths)} 个已下载的文件，开始计算成本...")
            
            # 计算每个文件的成本并累加
            total_credits = 0.0
            total_chars = 0
            total_tokens = 0
            total_images = 0
            image_size_limit = 1024  # 默认1KB
            
            for file_path in downloaded_file_paths:
                try:
                    logging.info(f"正在计算文件成本: {file_path}")
                    # 调用access_document_clear_price，设置re_parse=False避免重复解析
                    stats = access_document_clear_price(file_path, image_size_limit, re_parse=False)
                    
                    if stats and 'error' not in stats:
                        total_credits += stats.get('credits', 0)
                        total_chars += stats.get('char_count', 0)
                        total_tokens += stats.get('token_count', 0)
                        total_images += stats.get('image_count', 0)
                        logging.info(f"文件 {os.path.basename(file_path)} 成本计算完成: "
                                   f"积分={stats.get('credits', 0):.2f}, "
                                   f"字符数={stats.get('char_count', 0)}, "
                                   f"Token数={stats.get('token_count', 0)}, "
                                   f"图片数={stats.get('image_count', 0)}")
                    else:
                        error_msg = stats.get('error', '未知错误') if stats else '统计失败'
                        logging.warning(f"文件 {os.path.basename(file_path)} 成本计算失败: {error_msg}")
                        
                except Exception as e:
                    logging.error(f"计算文件 {file_path} 成本时发生异常: {e}")
                    traceback.print_exc()
                    continue
            
            # 更新数据库中的实际成本
            actual_credits = round(total_credits, 2)
            self.status_updater.update_actual_credits(self.task_id, actual_credits)
            
            logging.info(f"任务实际成本计算完成: 总积分={actual_credits:.2f}, "
                       f"总字符数={total_chars}, 总Token数={total_tokens}, "
                       f"总图片数={total_images}")
            return True
            
        except Exception as e:
            logging.error(f"计算任务实际成本时发生异常: {e}")
            traceback.print_exc()
            return False
    
    def count_qa_results(self):
        """统计stage_6中生成的高质量QA数据数量"""
        logging.info("开始统计任务结果...")
        
        if not os.path.exists(self.search_data_file_path):
            logging.warning(f"统计文件不存在: {self.search_data_file_path}")
            return {"qa_num": 0}
        
        try:
            qa_count = 0
            total_count = 0
            
            with open(self.search_data_file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        total_count += 1
                        
                        # 检查是否为高质量QA数据
                        quality_level = data.get('quality_level', '')
                        data_type = data.get('data_type', '')
                        
                        if quality_level == 'high' and data_type == 'qa':
                            qa_count += 1
                            
                    except json.JSONDecodeError as e:
                        logging.warning(f"第{line_num}行JSON解析失败: {e}")
                        continue
            
            result = {"qa_num": qa_count}
            logging.info(f"统计完成: 总数据量={total_count}, 高质量QA数量={qa_count}")
            return result
            
        except Exception as e:
            logging.error(f"统计任务结果时发生异常: {e}")
            traceback.print_exc()
            return {"qa_num": 0}

    def run_all_stages(self):
        """运行所有阶段"""
        logging.info(f"开始执行任务: {self.task_id}")
        
        # 阶段开始前，预测成本
        logging.info("=" * 100)
        logging.info("阶段开始前：预测任务成本")
        logging.info("=" * 100)
        self.predict_credits()
        
        stages = [
            ("文件下载", self.stage_1_download_files),
            ("文件解析", self.stage_2_parse_documents),
            ("文本翻译", self.stage_3_translate_documents),
            ("QA生成", self.stage_4_generate_qa),
            ("QA质量处理", self.stage_5_qa_quality),
            ("ES Schema转换", self.stage_6_schema_transform),
            ("ES插入索引", self.stage_7_insert_index),
        ]
        
        try:
            for stage_name, stage_func in stages:
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
    
    parser = argparse.ArgumentParser(description='文档QA挖掘任务控制脚本')
    parser.add_argument('--script-dir', required=True, help='脚本根目录路径')
    parser.add_argument('--task-id', required=True, help='任务ID')
    parser.add_argument('--task-info', required=True, help='任务信息JSON字符串')
    
    args = parser.parse_args()
    
    logging.info("=== 文档QA挖掘任务脚本启动 ===")
    logging.info(f"脚本目录: {args.script_dir}")
    logging.info(f"任务ID: {args.task_id}")
    logging.info(f"任务信息: {args.task_info}")
    
    try:
        # 解析任务信息
        task_info = json.loads(args.task_info)
        logging.info("任务信息解析成功")
        
        # 创建任务控制器
        logging.info("正在创建任务控制器...")
        controller = DocumentQAMiningTaskController(
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