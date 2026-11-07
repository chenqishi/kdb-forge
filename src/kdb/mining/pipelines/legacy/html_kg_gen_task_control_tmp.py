#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
HTML知识生成任务控制脚本
基于原始的platform_knowledge_generate_from_html.sh脚本改造
支持从task_info生成HTML知识
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('control_service/html_kg_gen_task_control_tmp.py')
import os
import sys
import json
import argparse
import logging
import subprocess
import traceback
import shlex
from pathlib import Path

# 添加项目根目录到sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
sys.path.append(project_root)

from off_task_tools.minio_downloader import MinioDownloader
from off_task_tools.task_status_updater import TaskStatusUpdater
from category_sys_manager.category_sys_util import (
    get_category_tree, 
    build_category_path_map, 
    build_category_id_to_path_map
)


class HtmlKgGenTaskController:
    """HTML知识生成任务控制器"""
    
    def __init__(self, script_dir, task_id, task_info):
        """初始化控制器"""
        self.script_dir = script_dir
        self.task_id = task_id
        self.task_info = task_info
        
        # 配置路径
        self.config_dir = os.path.join(script_dir, 'config')
        self.mysql_config_path = os.path.join(self.config_dir, 'mysql_conn_config.json')
        self.minio_config_path = os.path.join(self.config_dir, 'minio_config.json')
        self.multimodal_config_path = os.path.join(
            self.config_dir, 'config_document_qasegment.json'
        )
        
        # 工作目录
        self.data_dir = os.path.join(script_dir, 'data/off_task_data', task_id)
        self.log_dir = os.path.join(script_dir, 'log/off_task_log', task_id)
        
        # 确保目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 设置日志（需要先设置，预处理时会用到）
        self._setup_logging()
        
        # 初始化工具
        self.downloader = MinioDownloader(self.minio_config_path)
        self.status_updater = TaskStatusUpdater(self.mysql_config_path)
        
        # 预处理task_info，补齐类目信息
        self._preprocess_task_info()
        
        # 任务配置
        self.url_infos = task_info.get('url_infos', [])
        self.client = task_info.get('client', '')
        self.index_name = task_info.get('index_name', self.client)
        self.is_use_firecrawl = task_info.get('is_use_firecrawl', True)
        self.is_need_translated = task_info.get('is_need_translated', False)
        # 确保 category_id 是字符串类型（避免纯数字被解析为 int）
        category_id = task_info.get('category_id')
        self.category_id = str(category_id) if category_id is not None else None
        self.category_name = task_info.get('category_name')
        
        # 中间文件路径
        self.crawler_result_file = os.path.join(self.data_dir, f'crawler_result_{task_id}.json')
        self.processed_result_file = os.path.join(self.data_dir, f'crawler_and_process_results_{task_id}.txt')
        self.multimodal_result_file = os.path.join(self.data_dir, f'crawler_and_process_results_multimodal_{task_id}.txt')
        self.translated_result_file = os.path.join(self.data_dir, f'web_crawler_translated_{task_id}.txt')
        self.qa_result_file = os.path.join(self.data_dir, f'web_crawler_clear_qa_{task_id}.txt')
        self.reclear_qa_file_path = os.path.join(self.data_dir, f'web_crawler_reclear_qa_{task_id}.txt')
        self.search_data_file_path = os.path.join(self.data_dir, f'web_crawler_reclear_qa_{task_id}_search_data.txt')
        self.segment_knowledge_file_path = os.path.join(self.data_dir, f'segment_knowledge_{task_id}.txt')
        self.segment_search_data_file_path = os.path.join(self.data_dir, f'segment_knowledge_{task_id}_search_data.txt')
        
        # 多模态资源信息映射文件
        self.multimodal_data_info_path = os.path.join(self.data_dir, f'multimodal_data_info_{task_id}.json')
        
        self._index_config_path = None
    
    def _preprocess_task_info(self):
        """
        预处理task_info，补齐类目信息
        确保task_info和url_infos中都同时拥有category_name和category_id
        """
        client = self.task_info.get('client')
        if not client:
            # 没有client信息，无法查询类目树
            return
        
        try:
            # 获取类目树
            category_tree = get_category_tree(client)
            if not category_tree:
                logging.warning(f"无法获取客户端 {client} 的类目树，跳过类目信息补齐")
                return
            
            # 构建双向映射
            name_to_id_map = build_category_path_map(category_tree)
            id_to_name_map = build_category_id_to_path_map(category_tree)
            
            # 处理task_info顶层的类目信息
            self._fill_category_info(self.task_info, name_to_id_map, id_to_name_map)
            
            # 处理url_infos中的每个url的类目信息
            url_infos = self.task_info.get('url_infos', [])
            for url_info in url_infos:
                self._fill_category_info(url_info, name_to_id_map, id_to_name_map)
            
            logging.info("类目信息补齐完成")
            
        except Exception as e:
            logging.warning(f"预处理类目信息时发生异常: {e}")
            traceback.print_exc()
    
    def _fill_category_info(self, info_dict, name_to_id_map, id_to_name_map):
        """
        补齐单个字典中的类目信息
        
        Args:
            info_dict: 包含类目信息的字典（task_info或url_info）
            name_to_id_map: 类目名称到ID的映射
            id_to_name_map: 类目ID到名称的映射
        """
        category_name = info_dict.get('category_name')
        category_id = info_dict.get('category_id')
        
        # 如果两个都有，不需要处理
        if category_name and category_id:
            return
        
        # 只有category_name，需要查找category_id
        if category_name and not category_id:
            found_id = name_to_id_map.get(category_name)
            if found_id:
                info_dict['category_id'] = found_id
                logging.info(f"根据类目名称 '{category_name}' 补齐了类目ID: {found_id}")
            else:
                logging.warning(f"找不到类目名称 '{category_name}' 对应的ID")
        
        # 只有category_id，需要查找category_name
        elif category_id and not category_name:
            # 确保category_id是字符串
            category_id_str = str(category_id)
            found_name = id_to_name_map.get(category_id_str)
            if found_name:
                info_dict['category_name'] = found_name
                logging.info(f"根据类目ID '{category_id_str}' 补齐了类目名称: {found_name}")
            else:
                logging.warning(f"找不到类目ID '{category_id_str}' 对应的名称")
    
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
    
    def _get_index_config_path(self):
        """获取索引配置文件路径"""
        if self._index_config_path:
            return self._index_config_path
        
        index_config_path = os.path.join(self.config_dir, f'{self.index_name}_config.json')
        if not os.path.exists(index_config_path):
            logging.warning(f"索引配置文件不存在: {index_config_path}，尝试使用默认配置")
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
                return None
        
        self._index_config_path = index_config_path
        return self._index_config_path
    
    def _run_command(self, cmd, stage_name):
        """运行命令并记录日志"""
        log_file = os.path.join(self.log_dir, f'{stage_name}.log')
        logging.info(f"执行阶段: {stage_name}")
        logging.info(f"工作目录: {self.script_dir}")
        logging.info("=" * 80)
        logging.info(f"执行命令: {cmd}")
        logging.info("=" * 80)
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                result = subprocess.run(
                    cmd, 
                    shell=True, 
                    stdout=f, 
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=self.script_dir
                )
            
            # 读取命令输出日志，打印一些关键信息
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_content = f.read()
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
                    with open(log_file, 'r', encoding='utf-8') as f:
                        error_content = f.read()
                        if error_content.strip():
                            logging.error(f"错误详情: {error_content[-1000:]}")  # 显示最后1000字符
                return False
                
        except Exception as e:
            logging.error(f"执行阶段 {stage_name} 时发生异常: {e}")
            traceback.print_exc()
            return False
    
    def stage_1_crawl_urls(self):
        """阶段1：爬取URL"""
        self.status_updater.update_task_stage(self.task_id, "url_crawl")
        logging.info("开始阶段1：爬取URL")
        
        try:
            task_info_json = json.dumps(self.task_info, ensure_ascii=False)

            # 构建命令
            cmd = (
                f"python {self.script_dir}/knowledge_crawler_tool/web_crawl/web_batch_crawler.py "
                f"run_crawl_task_info "
                f"--task_id={self.task_id} "
                f"--task_info='{task_info_json}' "
                f"--output_file={self.crawler_result_file}"
            )
            
            if self._run_command(cmd, "url_crawl"):
                if os.path.exists(self.crawler_result_file):
                    # 统计爬取的结果数量
                    with open(self.crawler_result_file, 'r', encoding='utf-8') as f:
                        crawled_count = sum(1 for line in f if line.strip())
                    logging.info(f"URL爬取阶段完成，共爬取 {crawled_count} 个结果")
                    return True
                else:
                    logging.error("URL爬取失败：输出文件不存在")
                    return False
            else:
                logging.error("URL爬取阶段失败")
                return False
                
        except Exception as e:
            logging.error(f"URL爬取阶段发生异常: {e}")
            traceback.print_exc()
            return False
    
    def stage_2_process_crawled_content(self):
        """阶段2：处理已爬取的内容"""
        self.status_updater.update_task_stage(self.task_id, "content_process")
        logging.info("开始阶段2：处理已爬取的内容")
        
        if not os.path.exists(self.crawler_result_file):
            logging.error(f"处理已爬取内容失败：输入文件不存在: {self.crawler_result_file}")
            return False
        
        try:
            # 构建命令
            cmd = (
                f"python {self.script_dir}/knowledge_crawler_tool/web_crawl/web_batch_crawler.py "
                f"process_crawled_content_json_format "
                f"--input_file={self.crawler_result_file} "
                f"--output_dir={self.data_dir} "
                f"--flag={self.task_id}"
            )
            
            if self._run_command(cmd, "content_process"):
                if os.path.exists(self.processed_result_file):
                    # 统计处理的结果数量
                    with open(self.processed_result_file, 'r', encoding='utf-8') as f:
                        processed_count = sum(1 for line in f if line.strip())
                    logging.info(f"内容处理阶段完成，共处理 {processed_count} 个结果")
                    return True
                else:
                    logging.error("内容处理失败：输出文件不存在")
                    return False
            else:
                logging.error("内容处理阶段失败")
                return False
                
        except Exception as e:
            logging.error(f"内容处理阶段发生异常: {e}")
            traceback.print_exc()
            return False
    
    def stage_3_multimodal_process(self):
        """阶段3：多模态处理"""
        self.status_updater.update_task_stage(self.task_id, "multimodal_process")
        logging.info("开始阶段3：多模态处理")

        if not os.path.exists(self.processed_result_file):
            logging.error(f"多模态处理失败：输入文件不存在: {self.processed_result_file}")
            return False

        if not os.path.exists(self.multimodal_config_path):
            logging.error(f"多模态处理失败：配置文件不存在 {self.multimodal_config_path}")
            return False

        # 根据 is_use_firecrawl 选择 process_key
        process_key = 'firecrawl_content' if self.is_use_firecrawl else 'formatted_text'

        cmd = (
            f"python {self.script_dir}/data_preprocess/multimodal_process.py "
            f"batch_process_html_file "
            f"--config_path={self.multimodal_config_path} "
            f"--data_map_file={self.processed_result_file} "
            f"--field_num=-1 "
            f"--process_key={process_key} "
            f"--new_mapfile_path={self.multimodal_result_file} "
            f"--multimodal_data_info_path={self.multimodal_data_info_path} "
            f"--is_local=False"
        )

        if self._run_command(cmd, "multimodal_process"):
            if os.path.exists(self.multimodal_result_file):
                self.processed_result_file = self.multimodal_result_file
                logging.info(f"多模态处理完成，映射文件更新为: {self.multimodal_result_file}")
                try:
                    with open(self.processed_result_file, 'r', encoding='utf-8') as f:
                        updated_count = sum(1 for line in f if line.strip())
                    logging.info(f"多模态映射记录数: {updated_count}")
                    #exit(1)
                except Exception as e:
                    logging.warning(f"统计多模态映射记录数失败: {e}")
            else:
                logging.info("多模态处理未生成新的映射文件，将继续使用原始内容映射文件")
            return True

        logging.error("多模态处理阶段失败")
        return False

    def stage_4_translate_documents(self):
        """阶段4：文本翻译（可选）"""
        if not self.is_need_translated:
            logging.info("跳过翻译阶段（is_need_translated != True）")
            # 直接复制内容映射文件
            import shutil
            shutil.copy2(self.processed_result_file, self.translated_result_file)
            return True
            
        self.status_updater.update_task_stage(self.task_id, "document_translate")
        logging.info("开始阶段4：文本翻译")
        
        # 翻译阶段使用 transfer_url_content 作为 process_field
        cmd = (
            f"python {self.script_dir}/knowledge_clear_tool/knowledge_translate_by_dify.py "
            f"run_batch_translate_html_json_content "
            f"--input_file={self.processed_result_file} "
            f"--output_file={self.translated_result_file} "
            f"--field_num=-1 "
            f"--process_field=content_with_multimodal_unsderstanding"
        )
        
        if self._run_command(cmd, "translate"):
            if os.path.exists(self.translated_result_file):
                logging.info("文本翻译阶段完成")
                return True
            else:
                logging.error("文本翻译失败：输出文件不存在")
                return False
        else:
            logging.error("文本翻译阶段失败")
            return False
    
    def stage_5_generate_qa(self):
        """阶段5：QA生成"""
        self.status_updater.update_task_stage(self.task_id, "qa_generation")
        logging.info("开始阶段5：QA生成")
        
        # 确定输入文件
        input_file = self.translated_result_file if os.path.exists(self.translated_result_file) else self.processed_result_file
        
        # 根据 is_need_translated 选择 process_field
        process_field = 'translated_text' if self.is_need_translated else 'content_with_multimodal_unsderstanding'
        
        cmd = (
            f"python {self.script_dir}/knowledge_clear_tool/knowledge_html_clear_by_dify.py "
            f"run_batch_clear_html_content "
            f"--input_file={input_file} "
            f"--output_file={self.qa_result_file} "
            f"--process_field_num=-1 "
            f"--process_field={process_field}"
        )
        
        if self._run_command(cmd, "qa_generation"):
            if os.path.exists(self.qa_result_file):
                logging.info("QA生成阶段完成")
                return True
            else:
                logging.error("QA生成失败：输出文件不存在")
                return False
        else:
            logging.error("QA生成阶段失败")
            return False
    
    def stage_6_qa_quality(self):
        """阶段6：QA质量处理"""
        self.status_updater.update_task_stage(self.task_id, "qa_quality")
        logging.info("开始阶段6：QA质量处理")
        
        cmd = (
            f"python {self.script_dir}/quality_tools/qa_quality_tools.py "
            f"run_batch_re_clear_qa_info "
            f"--input_file={self.qa_result_file} "
            f"--output_file={self.reclear_qa_file_path} "
            f"--process_field_num=-1"
        )
        
        if self._run_command(cmd, "qa_quality"):
            logging.info("QA质量处理阶段完成")
            return True
        else:
            logging.error("QA质量处理阶段失败")
            return False
    
    def stage_7_schema_transform(self):
        """阶段7：QA转ES Schema"""
        self.status_updater.update_task_stage(self.task_id, "schema_transform")
        logging.info("开始阶段7：ES Schema转换")
        
        cmd = (
            f"python {self.script_dir}/commons/schema_trans.py "
            f"batch_trans_qa_to_search_data "
            f"--batch_file={self.reclear_qa_file_path} "
            f"--output_file={self.search_data_file_path} "
            f"--field_num=-1 "
            f"--platform_field_num=0"
        )
        
        # 添加task_id参数
        if self.task_id:
            cmd += f" --task_id={self.task_id}"
        
        # 添加类目参数（如果存在）
        if self.category_id:
            cmd += f" --category_id={self.category_id}"
        if self.category_name:
            cmd += f" --category_name='{self.category_name}'"
        
        # 添加多模态映射路径（如果存在）
        if os.path.exists(self.multimodal_data_info_path):
            cmd += f" --multimodal_mapping_path={self.multimodal_data_info_path}"
            logging.info(f"使用多模态映射文件: {self.multimodal_data_info_path}")
        else:
            logging.info("未找到多模态映射文件，跳过多模态内容处理")
        
        if self._run_command(cmd, "schema_transform"):
            logging.info("ES Schema转换阶段完成")
            return True
        else:
            logging.error("ES Schema转换阶段失败")
            return False
    
    def stage_8_insert_index(self):
        """阶段8：QA插入ES"""
        self.status_updater.update_task_stage(self.task_id, "index_insert")
        logging.info("开始阶段8：ES插入索引")
        
        # 生成索引配置文件路径
        index_config_path = self._get_index_config_path()
        if not index_config_path:
            logging.error("找不到可用的索引配置文件")
            return False
        
        cmd = (
            f"python {self.script_dir}/knowledge_interface_tools/search_index_data_interface.py "
            f"insert_data_to_search_index "
            f"--data_file={self.search_data_file_path} "
            f"--config_path={index_config_path} "
            f"--index_name_assign={self.index_name}"
        )
        
        if self._run_command(cmd, "index_insert"):
            logging.info("QA插入ES阶段完成")
            return True

        logging.error("QA插入ES阶段失败")
        return False

    def stage_9_generate_segment(self):
        """阶段9：段落知识生成"""
        self.status_updater.update_task_stage(self.task_id, "segment_generation")
        logging.info("开始阶段9：段落知识生成")

        segment_input = self.translated_result_file
        if not os.path.exists(segment_input):
            logging.error(f"段落知识生成失败：输入文件不存在 {segment_input}")
            return False

        # 根据 is_need_translated 选择 process_field_key，与 stage_5 类似
        process_field_key = 'translated_text' if self.is_need_translated else 'content_with_multimodal_unsderstanding'

        segment_output = self.segment_knowledge_file_path
        segment_log = os.path.join(self.log_dir, "segment_generation.log")
        
        cmd = (
            f"python {self.script_dir}/knowledge_generate/knowlege_segment_builder_by_dify.py "
            f"run_batch_get_segment_knowledge_html_json "
            f"--html_json_batch_file={segment_input} "
            f"--flag={self.task_id} "
            f"--filed_num=-1 "
            f"--platform_field_num=0 "            
            f"--process_field_key={process_field_key} "
            f"1>{segment_output} 2>{segment_log}"
        )

        if self._run_command(cmd, "segment_generation"):
            if os.path.exists(segment_output) and os.path.getsize(segment_output) > 0:
                logging.info(f"段落知识生成完成，输出文件: {segment_output}")
                return True
            logging.error("段落知识生成失败：未找到输出文件或文件为空")
            return False

        logging.error("段落知识生成阶段失败")
        return False

    def stage_10_segment_schema_transform(self):
        """阶段10：段落知识转ES Schema"""
        self.status_updater.update_task_stage(self.task_id, "segment_schema_transform")
        logging.info("开始阶段10：段落知识转ES Schema")

        if not os.path.exists(self.segment_knowledge_file_path):
            logging.error(f"段落知识转ES Schema失败：输入文件不存在 {self.segment_knowledge_file_path}")
            return False

        cmd = (
            f"python {self.script_dir}/commons/schema_trans.py "
            f"trans_html_segment_to_search_data_for_file "
            f"--input_file={self.segment_knowledge_file_path} "
            f"--output_file={self.segment_search_data_file_path} "
            f"--field_num=0"
        )
        
        # 添加task_id参数
        if self.task_id:
            cmd += f" --task_id={self.task_id}"
        
        # 添加类目参数（如果存在）
        if self.category_id:
            cmd += f" --category_id={self.category_id}"
        if self.category_name:
            cmd += f" --category_name='{self.category_name}'"
        
        # 添加多模态映射路径（如果存在）
        if os.path.exists(self.multimodal_data_info_path):
            cmd += f" --multimodal_mapping_path={self.multimodal_data_info_path}"
            logging.info(f"使用多模态映射文件: {self.multimodal_data_info_path}")
        else:
            logging.info("未找到多模态映射文件，跳过多模态内容处理")

        if self._run_command(cmd, "segment_schema_transform"):
            if os.path.exists(self.segment_search_data_file_path):
                logging.info("段落知识ES Schema转换完成")
                return True
            logging.error("段落知识ES Schema转换失败：未找到输出文件")
            return False

        logging.error("段落知识ES Schema转换阶段失败")
        return False

    def stage_11_insert_segment_index(self):
        """阶段11：段落知识插入ES"""
        self.status_updater.update_task_stage(self.task_id, "segment_index_insert")
        logging.info("开始阶段11：段落知识插入ES")

        if not os.path.exists(self.segment_search_data_file_path):
            logging.error(f"段落知识插入ES失败：输入文件不存在 {self.segment_search_data_file_path}")
            return False

        index_config_path = self._get_index_config_path()
        if not index_config_path:
            return False

        cmd = (
            f"python {self.script_dir}/knowledge_interface_tools/search_index_data_interface.py "
            f"insert_data_to_search_index --data_file={self.segment_search_data_file_path} "
            f"--index_name_assign={self.index_name} "
            f"--config_path={index_config_path}"
        )

        if self._run_command(cmd, "segment_index_insert"):
            logging.info("段落知识插入ES完成")
            return True

        logging.error("段落知识插入ES阶段失败")
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
            # 检查爬取结果文件是否存在
            if not os.path.exists(self.crawler_result_file):
                logging.warning(f"爬取结果文件不存在: {self.crawler_result_file}")
                # 如果文件不存在，使用url_infos的数量作为备选
                url_count = len(self.url_infos) if self.url_infos else 0
                logging.info(f"使用url_infos数量作为备选: {url_count}")
            else:
                # 读取爬取结果文件，统计实际爬取的URL数量（与stage_1_crawl_urls中的计算方法一致）
                with open(self.crawler_result_file, 'r', encoding='utf-8') as f:
                    url_count = sum(1 for line in f if line.strip())
            
            # 计算实际成本：URL数量 * 5
            actual_credits = url_count * 5
            
            # 更新数据库中的实际成本
            self.status_updater.update_actual_credits(self.task_id, actual_credits)
            
            logging.info(f"任务实际成本计算完成: 爬取URL数量={url_count}, 实际成本={actual_credits}")
            return True
            
        except Exception as e:
            logging.error(f"计算任务实际成本时发生异常: {e}")
            traceback.print_exc()
            return False
    
    def count_qa_results(self):
        """统计阶段7中生成的高质量QA数据数量"""
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
            ("多模态处理", self.stage_3_multimodal_process),
            ("文本翻译", self.stage_4_translate_documents),
            ("QA生成", self.stage_5_generate_qa),
            ("QA质量处理", self.stage_6_qa_quality),
            ("QA Schema转换", self.stage_7_schema_transform),
            ("QA插入索引", self.stage_8_insert_index),
            ("段落知识生成", self.stage_9_generate_segment),
            ("段落知识Schema转换", self.stage_10_segment_schema_transform),
            ("段落知识插入ES", self.stage_11_insert_segment_index),
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
    
    parser = argparse.ArgumentParser(description='HTML知识生成任务控制脚本')
    parser.add_argument('--script-dir', required=True, help='脚本根目录路径')
    parser.add_argument('--task-id', required=True, help='任务ID')
    parser.add_argument(
        '--task-info', 
        required=True, 
        help=(
            '任务信息JSON字符串。示例: '
            '{"url_infos": [{"url": "https://example.com/page1", "content_type": "normal", '
            '"crawler_degree": 2, "keywords": "product,detail,info", "keep_attr_name": "id,class", '
            '"limit_page_numbs": 10}], "client": "example_platform", "index_name": "example_index", '
            '"is_use_firecrawl": false, "is_need_translated": false}'
        )
    )
    
    args = parser.parse_args()
    
    logging.info("=== HTML知识生成任务脚本启动 ===")
    logging.info(f"脚本目录: {args.script_dir}")
    logging.info(f"任务ID: {args.task_id}")
    logging.info(f"任务信息: {args.task_info}")
    
    try:
        # 解析任务信息
        task_info = json.loads(args.task_info)
        logging.info("任务信息解析成功")
        
        # 创建任务控制器
        logging.info("正在创建任务控制器...")
        controller = HtmlKgGenTaskController(
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
