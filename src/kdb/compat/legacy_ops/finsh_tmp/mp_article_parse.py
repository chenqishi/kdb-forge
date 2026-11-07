import json
import logging
import sys
import pandas as pd
from typing import Dict, List, Any

def parse_mp_article_info(input_file):
    """
    解析微信公众号文章信息文件，提取标题、文章ID/URL和缩略图URL
    
    Args:
        input_file (str): 输入文件路径
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if 'item' in data and len(data['item']) > 0:
                    for item in data['item']:
                        if 'content' in item and 'news_item' in item['content']:
                            for news in item['content']['news_item']:
                                title = news.get('title', '')
                                article_id = item.get('article_id', '')
                                url = news.get('url', '')
                                thumb_url = news.get('thumb_url', '')
                                
                                # 使用article_id如果存在，否则使用url
                                #id_or_url = article_id if article_id else url
                                id_and_url = f"{article_id}||{url}"
                                
                                print(f"{title}\t{id_and_url}\t{thumb_url}\tarticle_id:{article_id}")
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON line: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error processing line: {e}", file=sys.stderr)

def parse_mp_article_info_v2(input_file):
    """
    解析微信公众号文章信息文件，提取标题、media_id/URL和缩略图URL
    
    Args:
        input_file (str): 输入文件路径
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if 'item' in data and len(data['item']) > 0:
                    for item in data['item']:
                        if 'content' in item and 'news_item' in item['content']:
                            for news in item['content']['news_item']:
                                title = news.get('title', '')
                                media_id = item.get('media_id', '')
                                url = news.get('url', '')
                                thumb_url = news.get('thumb_url', '')
                                
                                # 使用media_id和url组合
                                id_and_url = f"{media_id}||{url}"
                                
                                print(f"{title}\t{id_and_url}\t{thumb_url}\tmedia_id:{media_id}")
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON line: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error processing line: {e}", file=sys.stderr)

def trans_mp_article_excel_to_json(input_file):
    """
    将Excel文件转换为JSON格式，按关键词分组
    
    Args:
        input_file (str): 输入的Excel文件路径
    """
    # 读取Excel文件
    df = pd.read_excel(input_file)
    
    # 筛选is_ok != -1的数据
    df = df[df['is_ok'] != -1]
    
    # 初始化结果字典
    result_dict = {}
    
    # 处理每一行数据
    for _, row in df.iterrows():
        # 获取并分割关键词
        keywords = [k.strip() for k in str(row['keywords']).split(',') if k.strip()]
        
        # 构建当前行的数据字典
        meta_list = []
        
        # 处理text字段
        if pd.notna(row['text']):            
            meta = {
                'type': 'text',
                'text': str(row['text'])
            }
            meta_list.append(meta)

        # 处理meida字段
        if pd.notna(row['meida']):
            media_urls = [url.strip() for url in str(row['meida']).split(',') if url.strip()]
            for id_url in media_urls:
                id, url = id_url.split('||')
                meta = {
                    'type': 'mpnews',
                    'media_id': id,
                    'url': url
                    }
                meta_list.append(meta)
        # 处理articleidanurl字段
        if pd.notna(row['articleidanurl']):
            article_urls = [url.strip() for url in str(row['articleidanurl']).split(',') if url.strip()]
            for id_url in article_urls:
                id, url = id_url.split('||')
                meta = {
                    'type': 'mpnewsarticle',
                    'article_id': id,
                    'url':url
                    }                
                meta_list.append(meta)

        
        # 处理image字段
        if pd.notna(row['image']):
            image_value = str(row['image'])
            meta = {}
            meta['type'] = 'image'
            if image_value.startswith('http'):
                meta['image_url'] = image_value
            else:
                meta['media_id'] = image_value
            meta_list.append(meta)
        
        # 将数据添加到每个关键词对应的列表中
        for keyword in keywords:
            if keyword not in result_dict:
                result_dict[keyword] = []
            result_dict[keyword].extend(meta_list)
    
    # 输出JSON结果
    for k, v in result_dict.items():
        print(f'{k}\tequal\t{json.dumps(v, ensure_ascii=False)}')
        
def gen_key_mp_article_json_map_file(data_file, output_file):
    """
    生成关键词和mp文章json的映射文件
    
    Args:
        data_file (str): 输入文件路径，格式为 k\t{idtype}:{id}
        output_file (str): 输出的JSON文件路径
    """
    result_dict = {}
    
    # 读取输入文件
    with open(data_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            parts = line.split('\t')
            if len(parts) != 3:
                logging.warning(f"Invalid line format: {line}")
                continue
                
            keyword, channel_type, id_info = parts
            if channel_type == 'wechat_mp':
                # 解析ID类型和ID值
                try:
                    id_type, id_value = id_info.split(':')
                    
                    # 构建元数据
                    meta = {}
                    if id_type == 'article_id':
                        meta = {
                            'type': 'mpnewsarticle',
                            'article_id': id_value,
                            'url': ''  # URL为空，因为输入数据中没有提供
                        }
                    elif id_type == 'media_id':
                        meta = {
                            'type': 'mpnews',
                            'media_id': id_value,
                            'url': ''  # URL为空，因为输入数据中没有提供
                        }
                    else:
                        logging.warning(f"Unknown ID type: {id_type}")
                        continue
                except ValueError:
                    logging.warning(f"Invalid id_info format: {id_info}")
                    continue
                        
            elif channel_type == 'wx':
                # 将元数据添加到结果字典中
                meta = id_info


            result_dict.setdefault(keyword, {})
            result_dict[keyword][channel_type] = meta

    # 写入输出文件
    with open(output_file, 'w', encoding='utf-8') as f:
        for keyword, meta in result_dict.items():
            #meta = meta_list[0]
            f.write(f"{keyword}\t{json.dumps(meta, ensure_ascii=False)}\n")

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')      
    import fire
    fire.Fire({
        'parse_mp_article_info': parse_mp_article_info,
        'parse_mp_article_info_v2': parse_mp_article_info_v2,
        'trans_mp_article_excel_to_json': trans_mp_article_excel_to_json,
        'gen_key_mp_article_json_map_file': gen_key_mp_article_json_map_file,
    })
