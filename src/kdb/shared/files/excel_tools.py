import pandas as pd
import difflib
import logging
import sys
from typing import List, Dict, Any, Tuple
import json
from PIL import Image
import io
import base64
import os
import re

def diff_excel(file1_path: str, file2_path: str, columns: Tuple[int, int], output_file: str = None) -> None:
    """
    比较两个Excel文件中指定列的差异
    
    Args:
        file1_path: 第一个Excel文件路径
        file2_path: 第二个Excel文件路径
        columns: 需要比较的列号元组 (file1的列号, file2的列号)
        output_file: 输出结果的Excel文件路径，如果不指定则只输出到终端
    """
    # 读取两个Excel文件
    excel1 = pd.ExcelFile(file1_path)
    excel2 = pd.ExcelFile(file2_path)
    
    # 获取两个文件共同的sheet名称
    common_sheets = set(excel1.sheet_names).intersection(set(excel2.sheet_names))
    
    # 用于存储差异结果的列表
    diff_results: List[Dict[str, Any]] = []
    
    # 用于统计总行数
    total_rows_file1 = 0
    total_rows_file2 = 0
    
    col1, col2 = columns
    
    for sheet_name in common_sheets:
        df1 = pd.read_excel(file1_path, sheet_name=sheet_name)
        df2 = pd.read_excel(file2_path, sheet_name=sheet_name)
        
        # 累加总行数
        total_rows_file1 += len(df1)
        total_rows_file2 += len(df2)
        
        # 检查列号是否有效
        if col1 >= len(df1.columns):
            print(f"警告：在Sheet 1中 {sheet_name}中列号无效")
            continue
        if col2 >= len(df2.columns):
            print(f"警告：在Sheet 2中 {sheet_name}中列号无效")
            continue
        
        print(f"\n比较Sheet: {sheet_name}")
        
        for row in range(min(len(df1), len(df2))):
            # 获取单元格内容
            cell1 = str(df1.iloc[row, col1]) if not pd.isna(df1.iloc[row, col1]) else ""
            cell2 = str(df2.iloc[row, col2]) if not pd.isna(df2.iloc[row, col2]) else ""
            
            # 获取两个文件的第一列内容
            first_col1 = str(df1.iloc[row, 0]) if not pd.isna(df1.iloc[row, 0]) else ""
            first_col2 = str(df2.iloc[row, 0]) if not pd.isna(df2.iloc[row, 0]) else ""
            
            # 如果内容不同，计算差异
            if cell1 != cell2:
                # 使用difflib计算具体的文本差异
                differ = difflib.Differ()
                diff = list(differ.compare(cell1.split(), cell2.split()))
                
                removed = []
                added = []
                
                for d in diff:
                    if d.startswith('- '):
                        removed.append(d[2:])
                    elif d.startswith('+ '):
                        added.append(d[2:])
                
                removed_str = ' '.join(removed)
                added_str = ' '.join(added)
                
                diff_line = f"少：{{{removed_str}}},多：{{{added_str}}}"
                print(f"{sheet_name}\t{row+1}\t{diff_line}")
                
                # 将差异结果添加到列表中，包含两个文件的第一列内容
                diff_results.append({
                    'Sheet名称': sheet_name,
                    '行号': row + 1,
                    '原始问题': first_col1,
                    '修改问题(部分可能不会改)': first_col2,
                    '原始内容': cell1,
                    '新内容': cell2,
                    '差异描述': diff_line
                })
        
        # 检查行数差异
        if len(df1) != len(df2):
            diff_msg = f"\n行数差异 - {sheet_name}:\n文件1行数: {len(df1)}\n文件2行数: {len(df2)}"
            print(diff_msg)
            diff_results.append({
                'Sheet名称': sheet_name,
                '行号': '',
                '原始问题': '',
                '修改问题(部分可能不会改)': '',
                '原始内容': '',
                '新内容': '',
                '差异描述': f"行数差异 - 文件1: {len(df1)}行, 文件2: {len(df2)}行"
            })
    
    # 输出总行数对比
    print("\n=== 总行数对比 ===")
    print(f"文件1总行数: {total_rows_file1}")
    print(f"文件2总行数: {total_rows_file2}")
    print(f"行数差异: {abs(total_rows_file1 - total_rows_file2)}")
    
    # 如果指定了输出文件，将结果写入Excel
    if output_file and diff_results:
        df_result = pd.DataFrame(diff_results)
        # 调整列的顺序
        columns_order = ['Sheet名称', '行号', '原始问题', '修改问题(部分可能不会改)', 
                        '原始内容', '新内容', '差异描述']
        df_result = df_result[columns_order]
        df_result.to_excel(output_file, index=False)
        print(f"\n差异结果已保存到: {output_file}")

def image_json_to_excel(image_json_file: str, output_file: str) -> None:
    """
    将图片JSON数据转存到Excel文件中，并将图片嵌入到单元格中
    
    Args:
        image_json_file: 包含图片数据的JSON文件路径
        output_file: 输出Excel文件路径
    """
    # 读取JSON文件并按平台分组数据
    platform_data = {}
    with open(image_json_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if not data.get('image_path'):
                    continue
                    
                platform = data.get('platform', 'all')
                if platform not in platform_data:
                    platform_data[platform] = []
                platform_data[platform].append(data)
            except json.JSONDecodeError:
                logging.warning(f"无法解析JSON行: {line}")
                continue
    
    # 创建Excel写入器
    with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        for platform, records in platform_data.items():
            df = pd.DataFrame(records)
            
            # 确保所需列存在
            required_columns = ['image_path', 'image_understanding_knowledge', 'platform', 'image_name']
            for col in required_columns:
                if col not in df.columns:
                    df[col] = ''
            
            # 只保留需要的列并添加image_data列
            df = df[required_columns]
            df['image_data'] = ''
            
            # 调整列的顺序，将image_data放在第一列
            columns_order = ['image_data', 'image_path', 'image_understanding_knowledge', 'platform', 'image_name']
            df = df[columns_order]
            
            # 创建工作表
            worksheet = workbook.add_worksheet(platform)
            
            # 写入数据
            df.to_excel(writer, sheet_name=platform, index=False)
            
            # 设置列宽和行高
            for col_idx, width in enumerate([40, 30, 30, 20, 30]):  # 调整列宽顺序
                worksheet.set_column(col_idx, col_idx, width)
            worksheet.set_default_row(150)
            
            # 插入图片到第一列
            for idx, row in df.iterrows():
                try:
                    img_path = row['image_path']
                    if not img_path or not os.path.exists(img_path):
                        continue
                    
                    with Image.open(img_path) as img:
                        max_width = 200
                        max_height = 150
                        width, height = img.size
                        scale = min(max_width/width, max_height/height)
                        
                        # 修改列索引为0，表示插入到第一列
                        worksheet.insert_image(
                            idx + 1,    # 行号（跳过标题行）
                            0,          # image_data列现在是第一列
                            img_path,
                            {
                                'x_scale': scale,
                                'y_scale': scale,
                                'positioning': 2,
                                'x_offset': 5,
                                'y_offset': 5
                            }
                        )
                except Exception as e:
                    logging.error(f"处理图片时出错 {img_path}: {str(e)}")
                    continue
    
    logging.info(f"Excel文件已生成: {output_file}")

def trans_qa_excel_to_json_with_tags(excel_file_path: str, output_file_path: str) -> None:
    """
    将带有标签的QA Excel转换为JSON格式
    
    Args:
        excel_file_path: 输入Excel文件路径
        output_file_path: 输出JSON文件路径
        
    Excel格式要求:
    - 3列: query, answer, tags
    - tags格式: "name1":"value1","name2":"value2",...
    """
    if not os.path.exists(excel_file_path):
        raise FileNotFoundError(f"Excel文件不存在: {excel_file_path}")
        
    # 读取Excel文件
    df = pd.read_excel(excel_file_path)
    
    # 打开输出文件
    with open(output_file_path, 'w', encoding='utf-8') as f:
        for _, row in df.iterrows():
            query = str(row['query']).strip()
            answer = str(row['answer']).strip()
            tags_str = str(row['tags']).strip()
            synonyms_query = str(row['synonyms_query']).strip()
            supply_info_query = str(row['supply_info_query']).strip()
            if synonyms_query and synonyms_query.lower() != 'nan':
                synonyms_query = synonyms_query.split(';')
                synonyms_query = [q.strip() for q in synonyms_query if q.strip()]
            else:
                synonyms_query = []
            if supply_info_query and supply_info_query.lower() != 'nan':
                supply_info_query = supply_info_query.split('\n')
                supply_info_query = [q.strip() for q in supply_info_query if q.strip()]
            else:
                supply_info_query = []
            
            # 解析tags字符串
            tag_infos = []
            if tags_str and tags_str.lower() != 'nan':
                # 分割多个tag
                tag_pairs = tags_str.split(',')
                for pair in tag_pairs:
                    if ':' in pair:
                        name, value = pair.split(':', 1)
                        # 去除引号和空格
                        name = name.strip().strip('"').strip("'")
                        value = value.strip().strip('"').strip("'")
                        tag_infos.append({
                            "name": name,
                            "value": value
                        })
            if query == "nan":
                continue
            # 构建qa_dict
            qa_dict = {
                'question': query,
                'synonyms_query': synonyms_query,
                'answer': answer,
                'title': query,
                'content': answer,
                'tag_infos': tag_infos
            }
            if supply_info_query:
                qa_dict['supply_info_query'] = supply_info_query
            # 写入JSON行
            f.write(json.dumps(qa_dict, ensure_ascii=False) + '\n')
    
    logging.info(f"已将Excel转换为JSON格式并保存到: {output_file_path}")

def add_url_column_to_excel(excel_file_path: str) -> None:
    """
    给定一个Excel文件，遍历所有sheet，只保留(audit_result=1 或 quality_level为high) 且 audit_result不等于0 的行，
    并从content列中抽取所有URL，放到content_has_url列。
    结果直接覆盖原文件。
    """
    xls = pd.ExcelFile(excel_file_path, engine='openpyxl')
    url_pattern = re.compile(r'(https?://[\w\-\.\?\,\'/\\\+&%\$#_=:\(\)~;]+)')

    sheet_dict = {}
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(excel_file_path, sheet_name=sheet_name, engine='openpyxl')
        # 只保留满足条件的行：(audit_result==1 或 quality_level==high) 且 audit_result!=0
        audit_result = df.get('audit_result', None)
        quality_level = df.get('quality_level', None)
        mask = ((audit_result == 1) | (quality_level == 'high')) & (audit_result != 0)
        df = df[mask].copy()
        if 'content' not in df.columns:
            logging.warning(f"{sheet_name} 没有 content 列，跳过")
            df['content_has_url'] = ''
            sheet_dict[sheet_name] = df
            continue
        def extract_urls(text):
            if pd.isna(text):
                return ''
            urls = url_pattern.findall(str(text))
            return '\n'.join(urls)
        df['content_has_url'] = df['content'].apply(extract_urls)
        sheet_dict[sheet_name] = df

    with pd.ExcelWriter(excel_file_path, engine='openpyxl', mode='w') as writer:
        for sheet_name, df in sheet_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    logging.info(f"已处理并保存: {excel_file_path}")

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')      
    import fire
    fire.Fire({
        'diff_excel': diff_excel,
        'image_json_to_excel': image_json_to_excel,
        'trans_qa_excel_to_json_with_tags': trans_qa_excel_to_json_with_tags,
        'add_url_column_to_excel': add_url_column_to_excel,
    })
    