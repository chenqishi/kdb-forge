#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
文档QA挖掘任务控制脚本
基于原始的platform_knowledge_generate_from_raw_document.sh脚本改造
支持从远程文件系统（MinIO等）下载文件并生成QA
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('control_service/document_qa_segment_mining.py')
import os
import sys
import json
import argparse
import logging
import subprocess
import traceback
from pathlib import Path

# 添加项目根目录到sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
sys.path.append(project_root)

from off_task_tools.minio_downloader import MinioDownloader
from off_task_tools.task_status_updater import TaskStatusUpdater
from data_preprocess.document_clear_price_access import access_document_clear_price

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
        self.multimodal_config_path = os.path.join(
            self.config_dir, 'config_document_qasegment.json'
        )
        
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

        # ===== 新增（可选）业务上下文增强字段 =====
        # 缺省值保证：不传这些字段时，旧流程行为完全不变。
        self.business_context_text = task_info.get('business_context_text')
        self.knowledge_objective = task_info.get('knowledge_objective')
        self.quality_profile = task_info.get('quality_profile', 'business_task_knowledge')
        self.enable_context_enrichment = bool(task_info.get('enable_context_enrichment', False))
        self.enable_chat_query_context = bool(task_info.get('enable_chat_query_context', False))
        self.enable_web_context = bool(task_info.get('enable_web_context', False))  # 网络检索默认关闭
        self.context_cache_ttl_days = int(task_info.get('context_cache_ttl_days', 30))
        self.llm_backend = task_info.get('llm_backend', 'dify')  # 默认 dify，保持旧行为
        self.llm_model_name = task_info.get('llm_model_name')
        self.llm_provider = task_info.get('llm_provider')
        self.review_only = bool(task_info.get('review_only', False))
        
        # 中间文件路径
        self.file_mapping_path = os.path.join(self.data_dir, 'file_mapping.txt')
        self.content_mapping_path = os.path.join(self.data_dir, 'content_mapping.txt')
        self.translated_mapping_path = os.path.join(self.data_dir, 'translated_mapping.txt')
        self.qa_file_path = os.path.join(self.data_dir, 'all_clear_qa_file.txt')
        self.reclear_qa_file_path = os.path.join(self.data_dir, 'all_reclear_qa_file.txt')
        self.search_data_file_path = os.path.join(self.data_dir, 'all_reclear_qa_file_search_data.txt')
        self.segment_knowledge_file_path = os.path.join(self.data_dir, 'segment_knowledge.txt')
        self.segment_search_data_file_path = os.path.join(self.data_dir, 'segment_knowledge_search_data.txt')    
        self.multimodal_mapping_path = os.path.join(
            self.data_dir, 'content_mapping_multimodal.txt'
        )
        self.multimodal_data_info_path = os.path.join(self.data_dir, 'multimodal_data_info.json')
        self.multimodal_file_num = 5
        self._index_config_path = None

        # 业务上下文增强相关路径
        self.business_context_path = os.path.join(self.data_dir, 'business_context.json')
        self.business_context_cache_dir = task_info.get(
            'business_context_cache_dir',
            os.path.join(script_dir, 'data', 'business_context_cache')
        )
        self.quality_report_path = os.path.join(self.data_dir, 'generic_quality_report.json')
        
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
                os.path.join(self.script_dir, 'knowledge_clear_tool', 'wordtotext.py'),
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
    
    def stage_3_multimodal_process(self):
        """阶段3：多模态处理"""
        self.status_updater.update_task_stage(self.task_id, "multimodal_process")
        logging.info("开始阶段3：多模态处理")

        if not os.path.exists(self.content_mapping_path):
            logging.error(f"多模态处理失败：内容映射文件不存在: {self.content_mapping_path}")
            return False

        if not os.path.exists(self.multimodal_config_path):
            logging.error(f"多模态处理失败：配置文件不存在 {self.multimodal_config_path}")
            return False

        cmd = (
            f"python {self.script_dir}/data_preprocess/multimodal_process.py "
            f"batch_process_multimodal_data_file "
            f"--config_path={self.multimodal_config_path} "
            f"--data_map_file={self.content_mapping_path} "
            f"--field_num={self.multimodal_file_num} "
            f"--new_mapfile_path={self.multimodal_mapping_path} "
            f"--multimodal_data_info_path={self.multimodal_data_info_path} "
            f"--is_local=False"
        )

        if self._run_command(cmd, "multimodal_process"):
            if os.path.exists(self.multimodal_mapping_path):
                self.content_mapping_path = self.multimodal_mapping_path
                logging.info(f"多模态处理完成，映射文件更新为: {self.multimodal_mapping_path}")
                try:
                    with open(self.content_mapping_path, 'r', encoding='utf-8') as f:
                        updated_count = sum(1 for line in f if line.strip())
                    logging.info(f"多模态映射记录数: {updated_count}")
                except Exception as e:
                    logging.warning(f"统计多模态映射记录数失败: {e}")
            else:
                logging.info("多模态处理未生成新的映射文件，将继续使用原始内容映射文件")
            return True

        logging.error("多模态处理阶段失败")
        return False

    def stage_4_translate_documents(self):
        """阶段4：文本翻译（可选）"""
        if self.need_translate != 1:
            logging.info("跳过翻译阶段（need_translate != 1）")
            # 直接复制内容映射文件
            import shutil
            shutil.copy2(self.content_mapping_path, self.translated_mapping_path)
            return True
            
        self.status_updater.update_task_stage(self.task_id, "document_translate")
        logging.info("开始阶段4：文本翻译")
        
        cmd = f"python {self.script_dir}/knowledge_clear_tool/knowledge_translate_by_dify.py run_batch_translate_pdf_json_content {self.content_mapping_path}"
        
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
    
    def stage_4_5_build_business_context(self):
        """阶段4.5：构建业务上下文（仅 enable_context_enrichment=true 时执行）。

        不启用时为 no-op（不生成上下文文件、不改 prompt），保证旧任务行为不变。
        任一子来源（chat history / web）失败都会降级，不影响主流程。
        """
        if not self.enable_context_enrichment:
            logging.info("跳过业务上下文构建（enable_context_enrichment=false）")
            return True

        self.status_updater.update_task_stage(self.task_id, "build_business_context")
        logging.info("开始阶段4.5：构建业务上下文")
        try:
            sys.path.insert(0, self.script_dir)
            from knowledge_clear_tool.business_context_builder import build_business_context

            ctx = build_business_context(
                client=self.client,
                knowledge_objective=self.knowledge_objective,
                business_context_text=self.business_context_text,
                enable_context_enrichment=self.enable_context_enrichment,
                enable_chat_query_context=self.enable_chat_query_context,
                enable_web_context=self.enable_web_context,
                cache_dir=self.business_context_cache_dir,
                ttl_days=self.context_cache_ttl_days,
                task_info=self.task_info,
            )
            with open(self.business_context_path, 'w', encoding='utf-8') as f:
                json.dump(ctx, f, ensure_ascii=False, indent=2)
            logging.info(
                f"业务上下文已生成: {self.business_context_path}, sources={ctx.get('sources')}, "
                f"intents={len(ctx.get('query_intents', []))}"
            )
            return True
        except Exception as e:
            # 上下文构建是增强项，失败时降级为不增强，不中断任务
            logging.error(f"业务上下文构建失败，降级为不增强: {e}")
            traceback.print_exc()
            return True

    def _qa_context_cli_args(self):
        """构造 QA/segment 生成脚本的业务上下文/后端透传参数（仅在启用时附加）。"""
        if not self.enable_context_enrichment:
            return ""
        args = ""
        if os.path.exists(self.business_context_path):
            args += f" --business_context_path={self.business_context_path}"
        if self.quality_profile:
            args += f" --quality_profile={self.quality_profile}"
        if self.llm_backend:
            args += f" --llm_backend={self.llm_backend}"
        if self.llm_model_name:
            args += f" --llm_model_name={self.llm_model_name}"
        if self.llm_provider:
            args += f" --llm_provider={self.llm_provider}"
        return args

    def stage_5_generate_qa(self):
        """阶段5：QA生成"""
        self.status_updater.update_task_stage(self.task_id, "qa_generation")
        logging.info("开始阶段5：QA生成")

        # 确定输入文件
        input_file = self.translated_mapping_path if os.path.exists(self.translated_mapping_path) else self.content_mapping_path

        # 计算文件名字段位置（从0开始计数）
        # 映射格式：{platform}\t{file_name}\t{file_path}\tparse_save_dir\t{content_json_path}\t{multimodal_json_path}
        # file_name在第1列（索引1）
        file_name_field_num = 1
        data_file = self.qa_file_path
        log_file = self.log_dir + '/qa_generation.log'
        context_args = self._qa_context_cli_args()
        cmd = f"python {self.script_dir}/knowledge_clear_tool/knowledge_clear_by_dify_model_longcontent.py run_batch_clear_pdf_json_content {input_file} {self.task_id} {file_name_field_num} 1{context_args} 1>{data_file} 2>{log_file}"

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
    
    def stage_6_qa_quality(self):
        """阶段6：QA质量处理"""
        self.status_updater.update_task_stage(self.task_id, "qa_quality")
        logging.info("开始阶段6：QA质量处理")
        
        cmd = f"python {self.script_dir}/quality_tools/qa_quality_tools.py run_batch_re_clear_qa_info --input_file={self.qa_file_path} --output_file={self.reclear_qa_file_path} --process_field_num=-1"
        
        if self._run_command(cmd, "qa_quality"):
            logging.info("QA质量处理阶段完成")
            return True
        else:
            logging.error("QA质量处理阶段失败")
            return False
    
    def stage_6_5_generic_quality(self):
        """阶段6.5：通用质量后处理（仅 enable_context_enrichment=true 时执行）。

        对 stage_6 产出的 re_clear QA 文件（field -1 指向的 {high,mid,low} JSON）做：
          - 悬空指代 / 栏目式泛标题修复（repair_self_contained_knowledge_rows）；
          - boilerplate / 单薄 / 不可自包含过滤（filter_business_quality_rows）。
        被拒条目移出 high，并写入 self.quality_report_path，不静默修改。
        不启用时为 no-op，旧任务行为不变。
        """
        if not self.enable_context_enrichment:
            logging.info("跳过通用质量后处理（enable_context_enrichment=false）")
            return True
        if not os.path.exists(self.reclear_qa_file_path):
            logging.warning(f"通用质量后处理跳过：未找到 {self.reclear_qa_file_path}")
            return True

        self.status_updater.update_task_stage(self.task_id, "generic_quality")
        logging.info("开始阶段6.5：通用质量后处理")
        try:
            sys.path.insert(0, self.script_dir)
            from knowledge_clear_tool.generic_knowledge_quality import (
                repair_self_contained_knowledge_rows, filter_business_quality_rows,
            )

            business_context = None
            if os.path.exists(self.business_context_path):
                with open(self.business_context_path, 'r', encoding='utf-8') as f:
                    business_context = json.load(f)

            report = {"files": {}, "total_repaired": 0, "total_rejected": 0}
            with open(self.reclear_qa_file_path, 'r', encoding='utf-8') as f:
                mapping_lines = [l.strip() for l in f if l.strip()]

            for line in mapping_lines:
                fields = line.split('\t')
                qa_json_file = fields[-1]
                if not os.path.exists(qa_json_file):
                    continue
                with open(qa_json_file, 'r', encoding='utf-8') as jf:
                    qa_dict = json.load(jf)

                file_report = {}
                for level in ('high', 'mid', 'low'):
                    rows = qa_dict.get(level, []) or []
                    if not rows:
                        continue
                    # QA 字段为 q/a，映射为 title/content 做通用处理
                    repaired, rep_report = repair_self_contained_knowledge_rows(
                        rows, business_context=business_context,
                        source_title_field='from_file_name',
                        title_field='q', content_field='a',
                    )
                    kept, rejected = filter_business_quality_rows(
                        repaired, quality_profile=self.quality_profile,
                        title_field='q', content_field='a',
                    )
                    qa_dict[level] = kept
                    file_report[level] = {
                        'repaired': rep_report['repaired_count'],
                        'needs_review': rep_report['needs_review_count'],
                        'rejected': len(rejected),
                        'rejected_items': [
                            {'q': r.get('q', ''), 'reason': r.get('reject_reason', '')}
                            for r in rejected
                        ],
                    }
                    report['total_repaired'] += rep_report['repaired_count']
                    report['total_rejected'] += len(rejected)

                with open(qa_json_file, 'w', encoding='utf-8') as jf:
                    json.dump(qa_dict, jf, ensure_ascii=False, indent=2)
                report['files'][qa_json_file] = file_report

            with open(self.quality_report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            logging.info(
                f"通用质量后处理完成: 修复 {report['total_repaired']} 条, 拒绝 {report['total_rejected']} 条, "
                f"报告: {self.quality_report_path}"
            )
            return True
        except Exception as e:
            # 后处理失败不应中断主任务（已有 dify 质量过滤兜底）
            logging.error(f"通用质量后处理失败，降级跳过: {e}")
            traceback.print_exc()
            return True

    def stage_7_schema_transform(self):
        """阶段7：QA转ES Schema"""
        self.status_updater.update_task_stage(self.task_id, "schema_transform")
        logging.info("开始阶段7：ES Schema转换")
        
        cmd = f"python {self.script_dir}/commons/schema_trans.py batch_trans_qa_to_search_data --batch_file={self.reclear_qa_file_path} --output_file={self.search_data_file_path} --field_num=9 --platform_field_num=0"
        
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
        
        # 关查重：文档重跑走"先插后删"时，旧版本知识此刻仍然存活（del_flag=0），
        # 开查重会把新知识判成与旧版本重复而直接跳过插入（insert_data_to_search_index
        # 在 is_update_data=False 时 return (False,'数据重复')）——改写幅度越小越容易被吞，
        # 最后旧的删了、新的没进来，知识直接丢失。
        # 旧知识由调用方按文件名/标记精确软删，不依赖语义判重。
        cmd = (f"python {self.script_dir}/knowledge_interface_tools/search_index_data_interface.py "
               f"insert_data_to_search_index --data_file={self.search_data_file_path} "
               f"--config_path={index_config_path} --index_name_assign={self.index_name} "
               f"--check_duplicate=False")
        
        if self._run_command(cmd, "index_insert"):
            logging.info("QA插入ES阶段完成")
            return True

        logging.error("QA插入ES阶段失败")
        return False

    def stage_9_generate_segment(self):
        """阶段9：段落知识生成"""
        self.status_updater.update_task_stage(self.task_id, "segment_generation")
        logging.info("开始阶段9：段落知识生成")

        segment_input = self.translated_mapping_path
        if not os.path.exists(segment_input):
            logging.error(f"段落知识生成失败：输入文件不存在 {segment_input}")
            return False

        segment_flag = self.task_id or self.index_name or "segment"
        segment_output = self.segment_knowledge_file_path
        segment_log = os.path.join(self.log_dir, "segment_generation.log")
        context_args = self._qa_context_cli_args()
        cmd = (
            f"python {self.script_dir}/knowledge_generate/knowlege_segment_builder_by_dify.py "
            f"run_batch_get_segment_knowledge {segment_input} {segment_flag} 1 0 1 1{context_args} "
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
            f"trans_segment_to_search_data_for_file "
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

        # segment 没有 title，判重的 min(title_sim, content_sim) 恒为 -1，数值规则永不触发，
        # 结果全由主题级 LLM 决定，会把同一篇文档的不同页判成重复（见
        # insert_data_to_search_index 的 docstring）。所以这里必须关查重，
        # 旧 segment 由调用方按文件名精确清理，而不是靠语义判重。
        cmd = (
            f"python {self.script_dir}/knowledge_interface_tools/search_index_data_interface.py "
            f"insert_data_to_search_index --data_file={self.segment_search_data_file_path} "
            f"--config_path={index_config_path} --index_name_assign={self.index_name} "
            f"--check_duplicate=False"
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
            ("文件下载", self.stage_1_download_files),
            ("文件解析", self.stage_2_parse_documents),
            ("多模态处理", self.stage_3_multimodal_process),
            ("文本翻译", self.stage_4_translate_documents),
            ("构建业务上下文", self.stage_4_5_build_business_context),
            ("QA生成", self.stage_5_generate_qa),
            ("QA质量处理", self.stage_6_qa_quality),
            ("通用质量后处理", self.stage_6_5_generic_quality),
            ("QA Schema转换", self.stage_7_schema_transform),
            ("QA插入索引", self.stage_8_insert_index),
            ("段落知识生成", self.stage_9_generate_segment),
            ("段落知识Schema转换", self.stage_10_segment_schema_transform),
            ("段落知识插入ES", self.stage_11_insert_segment_index),
        ]

        # review_only=true：生成审核/中间文件，但跳过 ES 插入阶段
        if self.review_only:
            skip_insert = {"QA插入索引", "段落知识插入ES"}
            stages = [(name, func) for name, func in stages if name not in skip_insert]
            logging.info("review_only=true：本次跳过 QA/段落知识 ES 插入阶段，仅产出审核/中间文件")
        
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
