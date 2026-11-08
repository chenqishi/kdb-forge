from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
from kdb.shared.config.private_values import private_value as _private_value
import sys
import os

import logging
import json
import re
import traceback

from kdb.shared.clients.dify_tools import DifyWorkFlowRequest
from kdb.shared.text.text_utils import text_segment_by_limit
from kdb.mining.common.schema.review_content import merge_segment_content
from kdb.shared.config.global_config import GLOBAL_CONFIG

def is_chinese_text(text):
    """
    判断文本是否主要为中文
    
    :param text: 待检测文本
    :return: 是否为中文文本
    """
    # 统计中文字符数量
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    # 如果中文字符占比超过30%，认为是中文文本
    return len(chinese_chars) / len(text) > 0.3 if text else False

def translate_page_documents(pdf_json_file, dify_translate):
    """
    处理单个PDF文件的翻译
    
    :param pdf_json_file: PDF JSON文件路径
    :param dify_translate: Dify翻译模型实例
    :return: 翻译后的JSON数据
    """
    with open(pdf_json_file, 'r', encoding='utf-8') as f:
        data_json = json.load(f)
    
    # 获取整篇文档内容判断语言
    full_content = merge_segment_content(data_json, {'pages': [1, len(data_json)]}, need_add_page_num=False)
    is_chinese = is_chinese_text(full_content)
    
    if is_chinese:
        logging.info(f"文档 {pdf_json_file} 为中文文档，无需翻译")
        # 为所有文本段落添加is_translate标记
        for page_num in data_json:
            for item in data_json[page_num]:
                if item.get('type') == 'text':
                    item['is_translate'] = 0
        return data_json
    
    logging.info(f"文档 {pdf_json_file} 为非中文文档，开始翻译")
    # 翻译每个文本段落
    for page_num in data_json:
        for item in data_json[page_num]:
            if item.get('type') == 'text':
                original_text = item.get('text_content', '')
                if original_text.strip():
                    #translated_text = dify_translate.request_dify(original_text)
                    translated_text = translate_content_by_segment(original_text, dify_translate)                    
                    if translated_text:
                        item['ori_text_content'] = original_text
                        item['text_content'] = translated_text
                        item['is_translate'] = 1
                        logging.info(f"翻译成功: 原文: {original_text} -> 译文: {translated_text}")
                    else:
                        logging.error(f"翻译失败: {original_text}")
                        item['is_translate'] = 0
                else:
                    item['is_translate'] = 0
    
    return data_json

def translate_content_by_segment(content, dify_translate, sep='\n'):
    """
    处理单个文本内容的翻译,若过长则分段后合并
    """
    if len(content) < 6000:
        translated_text = dify_translate.request_dify(content)
        return translated_text
    else:
        segments, overlap_segments = text_segment_by_limit(content, len_limit=5000, sep=[sep], overlap_num=0)
        translated_texts = []
        for segment in segments:
            translated_text = dify_translate.request_dify(segment)
            translated_texts.append(translated_text)
        return sep.join(translated_texts)


def run_batch_translate_pdf_json_content(pdf_json_batch_file, field_num=-1):
    """
    批量处理PDF JSON文件的翻译
    
    :param pdf_json_batch_file: 包含多个PDF JSON文件路径的批处理文件
    :param flag: 用于生成输出文件名的标志
    :param from_file_name_field_num: 文件名字段的位置
    """
    api_base = GLOBAL_CONFIG['dify_api_base']
    dify_translate = DifyWorkFlowRequest(api_base=api_base, api_key=_private_value('22324b3b7458c583ac4203b1'), max_retries=3)

    with open(pdf_json_batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            pdf_json_file = fields[field_num]
            logging.info(f'开始处理文件: {pdf_json_file}')
            
            try:
                # 处理翻译并直接覆盖原文件
                translated_json = translate_page_documents(pdf_json_file, dify_translate)
                
                # 保存翻译结果到原文件
                with open(pdf_json_file, 'w', encoding='utf-8') as out_f:
                    json.dump(translated_json, out_f, ensure_ascii=False, indent=4)
                
                # 输出处理结果
                print('\t'.join(fields))
                
            except Exception as e:
                logging.error(f"处理文件 {pdf_json_file} 时发生错误: {str(e)}")
                continue

def translate_html_json(json_obj, dify_translate, process_field='formatted_text'):
    """
    处理单个HTML JSON对象的翻译
    
    :param json_obj: HTML JSON对象
    :param dify_translate: Dify翻译模型实例
    :return: 翻译后的JSON对象
    """
    original_text = json_obj.get(process_field, '')
    if not original_text.strip():
        json_obj['is_translate'] = 0
        return json_obj
    
    # 判断是否为中文文本
    if is_chinese_text(original_text):
        logging.info("文本为中文，无需翻译")
        json_obj['is_translate'] = 0
        return json_obj
    
    # 翻译非中文文本
    translated_text = translate_content_by_segment(original_text, dify_translate, sep='\n--------\n')
    if translated_text:
        json_obj["translated_text"] = translated_text
        json_obj['is_translate'] = 1
        logging.info(f"翻译成功: 原文: {original_text} -> 译文: {translated_text}")
    else:
        logging.error(f"翻译失败: {original_text}")
        json_obj['is_translate'] = 0
    
    return json_obj

def run_batch_translate_html_json_content(input_file, output_file, field_num, process_field='formatted_text'):
    """
    批量处理HTML JSON文件的翻译
    
    :param input_file: 输入文件路径，每行包含一个JSON对象
    :param output_file: 输出文件路径，每行包含一个JSON对象
    :param field_num: 要处理的字段位置
    """
    api_base = GLOBAL_CONFIG['dify_api_base']
    dify_translate = DifyWorkFlowRequest(api_base=api_base, api_key=_private_value('51368ad17f38ff0b97b9a1a0'), max_retries=3)
    
    # 读取并处理每一行
    with open(input_file, 'r', encoding='utf-8') as f, open(output_file, 'w', encoding='utf-8') as out_f:
        for line_num, line in enumerate(f, 1):
            try:
                fields = line.strip().split('\t')
                if len(fields) <= field_num:
                    logging.error(f"行 {line_num} 字段数量不足: {len(fields)} <= {field_num}")
                    out_f.write('\t'.join(fields) + '\n')
                    continue
                                
                # 解析JSON字段
                try:
                    data_json_file = fields[field_num]
                    json_obj = json.load(open(data_json_file, 'r', encoding='utf-8'))
                except json.JSONDecodeError as e:
                    logging.error(f"行 {line_num} {line}JSON解析错误: {str(e)}")                
                    continue
                
                # 翻译处理
                translated_json = translate_html_json(json_obj, dify_translate, process_field)
                
                # 更新字段
                trans_save_file = data_json_file.split('\.')[0] + '_trans.json'
                with open(trans_save_file, 'w', encoding='utf-8') as json_out_f:
                    json.dump(translated_json, json_out_f, ensure_ascii=False, indent=4)
                fields.append(trans_save_file)
                out_f.write('\t'.join(fields) + '\n')

                logging.info(f"成功处理第 {line_num} 行")
                
            except Exception as e:
                tb = traceback.format_exc()
                logging.error('tb[%s]', tb)
                logging.error(f"处理第 {line_num} {line}行时发生错误: {str(e)}")
                out_f.write('\t'.join(fields) + '\n')
                continue
    

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    import fire
    fire.Fire({
        'run_batch_translate_pdf_json_content': run_batch_translate_pdf_json_content,
        'run_batch_translate_html_json_content': run_batch_translate_html_json_content,
    })