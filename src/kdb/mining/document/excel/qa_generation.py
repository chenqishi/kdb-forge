import pandas as pd
import os
import logging
import sys
import json
from typing import List
from typing import Tuple
from typing import Dict
from typing import Optional
import re

def process_audit_excel(excel_path: str) -> List[Tuple[str, str]]:
    """
    处理审核Excel文件，根据不同的sheet格式提取问答对
    
    Args:
        excel_path: Excel文件路径
        
    Returns:
        List[Tuple[str, str]]: 问答对列表，每个元素为(question, answer)元组
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel文件不存在: {excel_path}")
        
    result_qa_pairs = []
    
    # 读取所有sheet
    excel_file = pd.ExcelFile(excel_path)
    
    for sheet_name in excel_file.sheet_names:
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        
        # 如果数据从第二行开始，重置列名
        if isinstance(df.columns[0], (int, float)):
            df.columns = df.iloc[0]
            df = df.iloc[1:].reset_index(drop=True)
            
        # 处理两列的情况
        if len(df.columns) == 2:
            for _, row in df.iterrows():
                q, a = row.iloc[0], row.iloc[1]
                if pd.notna(q) and pd.notna(a):
                    result_qa_pairs.append((sheet_name, str(q).strip(), str(a).strip()))
                    
        # 处理三列的情况
        elif len(df.columns) >= 3:
            for _, row in df.iterrows():
                col1, col2, col3 = row.iloc[0], row.iloc[1], row.iloc[2]
                
                # 跳过包含删除关键词的行
                if pd.notna(col2) and isinstance(col2, str) and \
                   any(keyword in col2 for keyword in ["删除", "可以删", "重复"]):
                    continue
                    
                # 确定问题列
                q = str(col2).strip() if pd.notna(col2) else str(col1).strip()
                a = str(col3).strip()
                
                if pd.notna(q) and pd.notna(a):
                    result_qa_pairs.append((sheet_name, str(q).strip(), str(a).strip()))
    for sheet_name, q, a in result_qa_pairs:
        qa_dict = {'question': q, 'answer': a, 'title':q, 'content':a}
        print(sheet_name + '\t' + json.dumps(qa_dict, ensure_ascii=False))
    #return result_qa_pairs

def load_sheet_url_map(map_file: str) -> Dict[str, str]:
    """
    加载sheet名称和URL的映射关系
    
    Args:
        map_file: 映射文件路径
        
    Returns:
        Dict[str, str]: sheet名称到URL的映射字典
    """
    sheet_url_map = {}
    with open(map_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                sheet_name, url = line.split('\t')
                sheet_url_map[sheet_name] = url
    return sheet_url_map



def process_qa(q: str, a: str, sheet_name: str, sheet_url: str) -> Tuple[str, str, Optional[str]]:
    modified = None
    has_url = False
    if re.search(r'\d+页', a):        # 检查是否包含URL
        urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', a)
        a = a.replace('本教程', '链接')
        if not urls:
            modified = f"{a}\n链接：{sheet_url}"
            logging.info(f"Sheet {sheet_name} 答案{a}中未包含链接，已添加链接")
        elif urls[0] != sheet_url:
            has_url = True
            logging.info(f"Sheet {sheet_name} 答案中包含的链接与映射不一致")
            modified = a.replace(urls[0], sheet_url)
        else:
            has_url = True
    else:
        has_url = True
    return q, a, modified, has_url

def process_audit_excel_add_url(excel_path: str, sheet_url_map_file: str, output_excel: str) -> None:
    """
    处理审核Excel文件，添加或修正URL链接
    
    Args:
        excel_path: Excel文件路径
        sheet_url_map_file: sheet名称到URL映射文件路径
        output_excel: 输出Excel文件路径
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel文件不存在: {excel_path}")
        
    sheet_url_map = load_sheet_url_map(sheet_url_map_file)
    result_qa_pairs = []
    modified_contents = []
    
    # 读取所有sheet
    excel_file = pd.ExcelFile(excel_path)
            
    for sheet_name in excel_file.sheet_names:
        if sheet_name not in sheet_url_map:
            logging.warning(f"Sheet {sheet_name} 在URL映射文件中未找到对应链接，将直接使用原答案")
            sheet_url = None
        else:
            sheet_url = sheet_url_map[sheet_name]
            
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        
        # 如果数据从第二行开始，重置列名
        if isinstance(df.columns[0], (int, float)):
            df.columns = df.iloc[0]
            df = df.iloc[1:].reset_index(drop=True)

        # 处理两列的情况
        if len(df.columns) == 2:
            for _, row in df.iterrows():
                q, a = str(row.iloc[0]).strip(), str(row.iloc[1]).strip()
                if pd.notna(q) and pd.notna(a):
                    if sheet_url is None:
                        # 当没有对应的URL时，直接将答案视为包含URL的情况
                        result_qa_pairs.append((sheet_name, q, a, True))
                        modified_contents.append(None)
                    else:
                        q, a, modified, has_url = process_qa(q, a, sheet_name, sheet_url)
                        result_qa_pairs.append((sheet_name, q, a, has_url))
                        modified_contents.append(modified)
                    
        # 处理三列的情况
        elif len(df.columns) >= 3:
            for _, row in df.iterrows():
                col1, col2, col3 = row.iloc[0], row.iloc[1], row.iloc[2]
                
                # 跳过包含删除关键词的行
                if pd.notna(col2) and isinstance(col2, str) and \
                   any(keyword in col2 for keyword in ["删除", "可以删", "重复"]):
                    continue
                    
                # 确定问题列
                q = str(col2).strip() if pd.notna(col2) else str(col1).strip()
                a = str(col3).strip()
                
                if pd.notna(q) and pd.notna(a):
                    if sheet_url is None:
                        # 当没有对应的URL时，直接将答案视为包含URL的情况
                        result_qa_pairs.append((sheet_name, q, a, True))
                        modified_contents.append(None)
                    else:
                        q, a, modified, has_url = process_qa(q, a, sheet_name, sheet_url)
                        result_qa_pairs.append((sheet_name, q, a, has_url))
                        modified_contents.append(modified)

    # 输出到Excel
    output_data = []
    for (sheet_name, q, a, has_url), modified in zip(result_qa_pairs, modified_contents):
        if has_url:
            qa_dict = {'question': q, 'answer': a, 'title':q, 'content':a}
        else:
            qa_dict = {'question': q, 'answer': modified, 'title':q, 'content':modified}
        print(sheet_name + '\t' + json.dumps(qa_dict, ensure_ascii=False))
        output_data.append([q, a, modified if modified else ''])
    
    # 创建输出DataFrame并保存
    output_df = pd.DataFrame(output_data, columns=['问题', '答案', '修改后内容'])
    output_df.to_excel(output_excel, index=False)


def process_audit_excel_mluti_query_forletin(excel_path: str, sheet_url_map_file: str, output_excel: str) -> None:
    """
    处理包含同义问题的审核Excel文件
    
    Args:
        excel_path: Excel文件路径
        sheet_url_map_file: sheet名称到URL映射文件路径
        output_excel: 输出Excel文件路径
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel文件不存在: {excel_path}")
        
    sheet_url_map = load_sheet_url_map(sheet_url_map_file)
    result_qa_pairs = []
    modified_contents = []
    
    # 读取所有sheet
    excel_file = pd.ExcelFile(excel_path)
            
    for sheet_name in excel_file.sheet_names:
        if sheet_name not in sheet_url_map:
            logging.warning(f"Sheet {sheet_name} 在URL映射文件中未找到对应链接，将直接使用原答案")
            sheet_url = None
        else:
            sheet_url = sheet_url_map[sheet_name]
            
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        
        # 如果数据从第二行开始，重置列名
        if isinstance(df.columns[0], (int, float)):
            df.columns = df.iloc[0]
            df = df.iloc[1:].reset_index(drop=True)

        for _, row in df.iterrows():
            q = str(row.iloc[0]).strip()
            synonyms = str(row.iloc[1]).strip().split('\n') if pd.notna(row.iloc[1]) else []
            a = str(row.iloc[2]).strip()
            
            # 如果主问题为空，使用同义问题列表的第一个作为主问题
            if not q or pd.isna(q) or q == "nan":
                if synonyms:
                    q = synonyms[0]
                    synonyms = synonyms[1:]  # 更新同义问题列表，移除第一个问题
                else:
                    continue  # 如果两者都为空，跳过该行
            
            if pd.notna(q) and pd.notna(a):
                if sheet_url is None:
                    result_qa_pairs.append((sheet_name, q, synonyms, a, True))
                    modified_contents.append(None)
                else:
                    q, a, modified, has_url = process_qa(q, a, sheet_name, sheet_url)
                    result_qa_pairs.append((sheet_name, q, synonyms, a, has_url))
                    modified_contents.append(modified)

    # 输出到Excel和标准输出
    output_data = []
    for (sheet_name, q, synonyms, a, has_url), modified in zip(result_qa_pairs, modified_contents):
        if has_url:
            qa_dict = {
                'question': q, 
                'synonyms_query': synonyms,
                'answer': a, 
                'title': q, 
                'content': a
            }
        else:
            qa_dict = {
                'question': q,
                'synonyms_query': synonyms,
                'answer': modified,
                'title': q,
                'content': modified
            }
        print(sheet_name + '\t' + json.dumps(qa_dict, ensure_ascii=False))
        output_data.append([q, '\n'.join(synonyms), a, modified if modified else ''])
    
    # 创建输出DataFrame并保存
    output_df = pd.DataFrame(output_data, columns=['问题', '同义问题', '答案', '修改后内容'])
    output_df.to_excel(output_excel, index=False)

def process_audit_image_excel_to_segment(excel_path: str, output_file: str) -> None:
    """
    处理包含图片的Excel文件，将每行数据转换为json格式的segment_info
    
    Args:
        excel_path: Excel文件路径
        output_file: 输出文件路径
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel文件不存在: {excel_path}")
        
    # 读取所有sheet
    excel_file = pd.ExcelFile(excel_path)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            
            # 确保必要的列存在
            required_columns = ['image_path', 'image_understanding_knowledge', 'platform', 'image_name']
            if not all(col in df.columns for col in required_columns):
                logging.warning(f"Sheet {sheet_name} 缺少必要的列，跳过处理")
                continue
            
            # 处理每一行数据
            for _, row in df.iterrows():
                # 跳过空行
                if pd.isna(row['image_understanding_knowledge']) or pd.isna(row['platform']):
                    continue
                
                # 构建a字典
                a = {
                    'platform': row['platform'],
                    'image_name': row['image_name'] if pd.notna(row['image_name']) else ''
                }
                
                # 构建segment_info
                segment_info = {
                    'q': row['image_understanding_knowledge'],
                    'a': json.dumps(a, ensure_ascii=False),
                    'platform': row['platform'],
                    'document_name': sheet_name,
                    'indexes': [
                        row['platform'],
                        row['image_name'] if pd.notna(row['image_name']) else ''
                    ]
                }
                
                # 写入文件
                f.write(f"{sheet_name}\t{json.dumps(segment_info, ensure_ascii=False)}\n")

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')  
    import fire
    fire.Fire({
        'process_audit_excel': process_audit_excel,
        'process_audit_excel_add_url': process_audit_excel_add_url,
        'process_audit_excel_mluti_query_forletin': process_audit_excel_mluti_query_forletin,
        'process_audit_image_excel_to_segment': process_audit_image_excel_to_segment,
    })
