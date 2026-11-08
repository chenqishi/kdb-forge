from PIL import Image
from kdb.shared.files.excel_diff import diff_excel
import json
import logging
import os
import pandas as pd
import re
import sys

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
