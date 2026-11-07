#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-10-19
"""
import json
import os
import re
import logging
import requests
import fire
import sys
import traceback

class KnowledgeCleaner:
    def __init__(self, api_base=None, api_key=None):
        self.api_base = api_base
        self.api_key = api_key

    def request_dify(self, title, topic_road, content):
        headers = {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json'
        }
        
        payload = {
            'inputs': {
                'title': title,
                'topic': topic_road
            },
            "query": content,
            "response_mode": "blocking",
            "user": "qutian"
        }
        
        try:
            logging.info(f"正在调用Dify API，请求内容: {payload}")
            response = requests.post(f"{self.api_base}/chat-messages", headers=headers, json=payload, timeout=600)  # 设置超时时间为10分钟
            
            
            if response.status_code != 200:
                logging.error(f"API返回非200状态码: {response.status_code}")
                logging.error(f"响应内容: {response.text}, api_key: {self.api_key}, req params: {payload}")
                return None
            logging.info(f"Dify API响应: {response.text}")
            result = response.json()
            return result.get('answer', '')
        except requests.exceptions.Timeout:
            logging.error("请求超时（10分钟）")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"请求异常: {str(e)}")
            logging.error(f"请求URL: {self.api_base}/chat-messages")
            logging.error(f"请求头: {headers}")
            logging.error(f"请求体: {payload}")
            return None
        except Exception as e:
            tb = traceback.format_exc()
            logging.error('tb[%s]', tb)
            logging.error(f"调用Dify API时发生错误: {str(e)}")
            return None

    def process_and_save(self, map_file, answer_save_file):
        processed_files = set()
        
        # 如果answer_save_file已存在，先读取已处理的文件
        if os.path.exists(answer_save_file):
            with open(answer_save_file, 'r', encoding='utf-8') as f:
                for line in f:
                    data = json.loads(line)
                    processed_files.add(data.get('file_path', ''))

        with open(map_file, 'r', encoding='utf-8') as f, open(answer_save_file, 'a', encoding='utf-8') as out_f:
            for line in f:
                crawl_file = line.strip()
                if crawl_file in processed_files:
                    logging.info(f"文件 {crawl_file} 已处理，跳过")
                    continue

                try:
                    with open(crawl_file, 'r', encoding='utf-8') as cf:
                        data = json.load(cf)
                    
                    title = data.get('title', '')
                    content = data.get('content', '')
                    topic_road = '|'.join(set(data.get('topic_road', [])))
                    
                    answer = self.request_dify(title, topic_road, content)
                    
                    if answer:
                        data['answer'] = answer
                        data['file_path'] = crawl_file  # 添加文件路径以便后续识别
                        write_line = json.dumps(data, ensure_ascii=False)
                        out_f.write(write_line + '\n')
                        processed_files.add(crawl_file)
                    else:
                        logging.error(f"处理文件 {crawl_file} 时未获得有效响应")
                
                except Exception as e:
                    logging.error(f"处理文件 {crawl_file} 时发生错误: {str(e)}")

    def parse_response(self, answer_save_file, output_file):
        with open(answer_save_file, 'r', encoding='utf-8') as f, open(output_file, 'w', encoding='utf-8') as out_f:
            for line in f:
                data = json.loads(line)
                answer = data.get('answer', '')
                title = data.get('title', '')
                topic_road = '|'.join(set(data.get('topic_road', [])))
                
                # 提取标题翻译和文档主题翻译
                title_translation = re.search(r'标题翻译:(.*?)(?=\n|$)', answer)
                topic_road_translation = re.search(r'文档主题翻译:(.*?)(?=\n|$)', answer)
                
                if title_translation:
                    title = title_translation.group(1).strip()
                if topic_road_translation:
                    topic_road = topic_road_translation.group(1).strip()
                
                # 移除标题翻译和文档主题翻译
                answer = re.sub(r'标题翻译:.*?\n?', '', answer)
                answer = re.sub(r'文档主题翻译:.*?\n?', '', answer)
                
                segments = re.split(r'(?=主题:)', answer)
                for segment in segments:
                    if segment.strip():
                        lines = segment.split('\n', 1)
                        if len(lines) == 2 and lines[0].startswith('主题:'):
                            topic = lines[0].replace('主题:', '').strip()
                            text = lines[1].replace('段落:', '').strip()
                            text = text.replace('\n', '\\n')
                            out_f.write(f"{topic}\t{text}\t{title}\t{topic_road}\n")

def clear_pdf_json_content(pdf_json_file, output_file):
    """
    """

    data_json = json.load(open(pdf_json_file, 'r', encoding='utf-8'))
    document_content = ''
    for page_num, page_values in data_json.items():
        page_num = int(page_num)
        one_page_content = ''
        for one_value in page_values:
            if one_value.get('type') == 'text':
                one_segment_content = one_value.get('text_content', '')
                one_page_content = one_page_content + '\n' + one_segment_content if one_page_content else one_segment_content
        
            
        if one_page_content:
            document_content = document_content + '\n' + one_page_content if document_content else one_page_content
            with open(output_file, 'a', encoding='utf-8') as out_f:
                out_f.write(f'第{page_num}页内容如下:\n')
                out_f.write(f"{one_page_content}\n")
    return document_content

def run_batch_clear_pdf_json_content(pdf_json_batch_file):
    with open(pdf_json_batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            pdf_json_file = fields[-1]
            logging.info(f'开始处理文件: {pdf_json_file}')
            file_path = pdf_json_file.replace('.json', '.txt')
            output_file =  file_path
            document_content = clear_pdf_json_content(pdf_json_file, output_file)
            fields.append(file_path)
            print('\t'.join(fields))
    

def request(api_base, api_key, map_file, answer_save_file):
    cleaner = KnowledgeCleaner(api_base, api_key)
    cleaner.process_and_save(map_file, answer_save_file)

def parse(answer_save_file, output_file):
    cleaner = KnowledgeCleaner()
    cleaner.parse_response(answer_save_file, output_file)

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')  
    fire.Fire({
        'request': request,
        'parse': parse, 
        'run_batch_clear_pdf_json_content': run_batch_clear_pdf_json_content,
    })
