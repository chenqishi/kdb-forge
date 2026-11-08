from kdb.mining.common.schema.review_content import trans_page_content_to_text
from kdb.mining.common.schema.page_export import write_page_content
from kdb.shared.files.names import get_index_file_name
from openpyxl import Workbook
from openpyxl import load_workbook
import json
import logging
import os
import re
import sys
import traceback

def load_white_name_permission_dict(white_name_file):
    """
    加载白名单文件
    """
    white_name_dict = dict()
    with open(white_name_file, 'r', encoding='utf-8') as f:
        for line in f:
            columns = line.strip().split('\t')
            platform = columns[0]
            writers = set(columns[1].split('|'))
            if len(columns) > 2:
                permissions = set(columns[2].split('|'))
            else:
                permissions = set(['high'])
            white_name_dict[platform] = {'writers': writers, 'permissions': permissions}
    return white_name_dict


def json_to_excel(json_data, wb, platform=None):
    for item in json_data:
        sheet_name = get_index_file_name(item['from_file_name'])
        logging.info(f'from_file_name: {item["from_file_name"]}, sheet_name: {sheet_name}')
        if sheet_name not in wb.sheetnames:
            ws = wb.create_sheet(sheet_name)
            if platform:
                ws.append(["platform", "问题", "答案"])
            else:
                ws.append(["问题", "答案"])
        else:
            ws = wb[sheet_name]
        if platform:
            ws.append([platform, item['q'], item['a']])
        else:
            ws.append([item['q'], item['a']])


def json_to_excel_has_quality(json_data, wb, platform=None):
    """
    带有质量标签的json数据转换为excel
    """
    for k, json_list in json_data.items():
        for item in json_list:
            # 修改sheet名称的生成方式
            base_name = get_index_file_name(item['from_file_name'])
            suffix = f'_{k}'
            max_base_length = 31 - len(suffix)  # 预留suffix的长度
            
            # 如果base_name过长，从中间截取
            if len(base_name) > max_base_length:
                half_length = max_base_length // 2
                base_name = base_name[:half_length] + '...' + base_name[-half_length:]
            
            sheet_name = f'{base_name}{suffix}'
            sheet_name = re.sub(r'[^\w\s-]', '', sheet_name)  # 替换非字母数字的字符为下划线
            
            logging.info(f'sheet_name: {sheet_name}')
            
            if sheet_name not in wb.sheetnames:
                ws = wb.create_sheet(sheet_name)
                if platform:
                    ws.append(["平台", "问题", "答案", '组号', 'quality_tag'])
                else:
                    ws.append(["问题", "答案", '组号', 'quality_tag'])
            else:
                ws = wb[sheet_name]
            if platform:
                ws.append([platform, item['q'], item['a'], item['group'], '|'.join(item['quality_info'])])
            else:
                ws.append([item['q'], item['a'], item['group'], '|'.join(item['quality_info'])])


def json_to_excel_mid_quality(json_data, wb, platform=None):
    """
    带有mid质量标签的json数据转换为excel
    """
    for item in json_data:
        # 修改sheet名称的生成方式
        base_name = get_index_file_name(item['from_file_name'])
        sheet_name = f'{base_name}'
        sheet_name = re.sub(r'[^\w\s-]', '', sheet_name)  # 替换非字母数字的字符为下划线
        logging.info(f'sheet_name: {sheet_name}')
        
        if sheet_name not in wb.sheetnames:
            ws = wb.create_sheet(sheet_name)
            if platform:
                ws.append(["平台", "问题", "答案", '组号', 'quality_tag', 'reason'])
            else:
                ws.append(["问题", "答案", '组号', 'quality_tag', 'reason'])
        else:
            ws = wb[sheet_name]
        if platform:
            ws.append([platform, item['q'], item['a'], item['group'], '|'.join(item['quality_info']), item.get('reason', '')])
        else:
            ws.append([item['q'], item['a'], item['group'], '|'.join(item['quality_info']), item.get('reason', '')])


def batch_json_to_excel(batch_file, excel_file, field_num=3, mode=0):
    # 如果excel文件不存在，创建新的工作簿
    if not os.path.exists(excel_file):
        wb = Workbook()
        wb.remove(wb.active)  # 删除默认创建的sheet
    else:
        wb = load_workbook(excel_file)
    
    with open(batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            columns = line.strip().split('\t')
            if len(columns) >= 4:
                json_file = columns[field_num]
                with open(json_file, 'r', encoding='utf-8') as jf:
                    json_data = json.load(jf)
                    if mode == 0:
                        json_to_excel(json_data, wb)
                    else:
                        json_to_excel_has_quality(json_data, wb)
    
    wb.save(excel_file)


def qajson_to_line_text(qa_json_list, add_index=False):
    trans_texts = list()

    for index, item in enumerate(qa_json_list):
        q = item['q']
        a = item['a']
        if add_index:
            one_qa = f'{index+1}.问题:{q}\n答案:{a}'
        else:
            one_qa = f'问题:{q}\n答案:{a}'
        trans_texts.append(one_qa)
    trans_text = '\n###\n'.join(trans_texts)
    return trans_text


def output_qa_json_trans_result(qa_json_file, add_index=1, wrtite_file=None):
    """
    """
    add_index = bool(add_index)
    qa_json_list = json.load(open(qa_json_file, 'r', encoding='utf-8'))
    trans_text = qajson_to_line_text(qa_json_list, add_index)
    if wrtite_file:
        with open(wrtite_file, 'w', encoding='utf-8') as f:
            f.write(trans_text)
    else:
        print(trans_text)


def output_page_content_trans_result(page_content_file, add_page_num=1, wrtite_file=None):
    """Keep this review format's original text-only page policy."""
    return write_page_content(page_content_file, add_page_num, wrtite_file, trans_page_content_to_text)


def batch_split_json_quality_to_excel(batch_file, high_quality_excel_file, mid_quality_excel_file, low_quality_excel_file=None, field_num=3, platform_field_num=None):
    """
    将高质量和中等质量的数据分别写入不同的Excel文件
    
    Args:
        batch_file: 批处理文件路径
        high_quality_excel_file: 高质量数据的Excel文件路径
        mid_quality_excel_file: 中等质量数据的Excel文件路径
        field_num: 批处理文件中JSON文件路径所在的列号
    """
    # 修改工作簿创建和加载逻辑
    try:
        if os.path.exists(high_quality_excel_file):
            try:
                high_wb = load_workbook(high_quality_excel_file)
            except Exception as e:
                logging.warning(f"无法加载高质量Excel文件，创建新文件: {str(e)}")
                high_wb = Workbook()
                high_wb.remove(high_wb.active)
        else:
            high_wb = Workbook()
            high_wb.remove(high_wb.active)
            
        if os.path.exists(mid_quality_excel_file):
            try:
                mid_wb = load_workbook(mid_quality_excel_file)
            except Exception as e:
                logging.warning(f"无法加载中等质量Excel文件，创建新文件: {str(e)}")
                mid_wb = Workbook()
                mid_wb.remove(mid_wb.active)
        else:
            mid_wb = Workbook()
            mid_wb.remove(mid_wb.active)
        if low_quality_excel_file:
            low_wb = Workbook()
            low_wb.remove(low_wb.active)
            
        with open(batch_file, 'r', encoding='utf-8') as f:
            for line in f:
                columns = line.strip().split('\t')
                if platform_field_num is not None:
                    platform = columns[platform_field_num]
                else:
                    platform = None
                
                if len(columns) > field_num:
                    json_file = columns[field_num]
                    logging.info(f'process json_file: {json_file}')
                    with open(json_file, 'r', encoding='utf-8') as jf:
                        try:
                            json_data = json.load(jf)
                        except:
                            tb = traceback.format_exc()
                            logging.error(f'process json_file: {json_file} error: {tb}')
                            continue
                        # 分别处理高质量和中等质量数据
                        if 'high' in json_data:
                            json_to_excel(json_data['high'], high_wb, platform)
                        if 'mid' in json_data:
                            json_to_excel_mid_quality(json_data['mid'], mid_wb, platform)
                        if 'low' in json_data and low_quality_excel_file:
                            json_to_excel_mid_quality(json_data['low'], low_wb, platform)
        
        # 确保即使workbook为空也会保存文件
        if not high_wb.sheetnames:
            ws = high_wb.create_sheet("Sheet1")  # 创建一个空的sheet
        high_wb.save(high_quality_excel_file)
        
        if not mid_wb.sheetnames:
            ws = mid_wb.create_sheet("Sheet1")
        mid_wb.save(mid_quality_excel_file)
        
        if low_quality_excel_file:
            if not low_wb.sheetnames:
                ws = low_wb.create_sheet("Sheet1")
            low_wb.save(low_quality_excel_file)
    
    except Exception as e:
        tb = traceback.format_exc()
        logging.error('tb[%s]', tb)
        logging.error(f"处理Excel文件时发生错误: {str(e)}")
        raise


def batch_select_high_quality_qa_to_json(batch_file, field_num=6, platform_field_num=None):
    """
    批量选择高质量的QA数据并转换为JSON文件
    """
    with open(batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            columns = line.strip().split('\t')
            if platform_field_num is not None:
                platform = columns[platform_field_num]
            else:
                platform = None
            logging.info(f'platform_field_num: {platform_field_num}, platform: {platform}')
            if len(columns) > field_num:
                json_file = columns[field_num]
                logging.info(f'start process json_file: {json_file}')

                with open(json_file, 'r', encoding='utf-8') as jf:
                    json_data = json.load(jf)
                    # 分别处理高质量和中等质量数据                    
                    qa_list = json_data.get('high', [])
                    for qa in qa_list:
                        from_file_name = qa.get('from_file_name', '')
                        file_name = get_index_file_name(from_file_name)
                        trans_info = {'title': qa['q'], 'content': qa['a'], 'document_name': file_name} # document_name 用于在fastgpt下建立不同的document
                        if platform:
                            trans_info['platform'] = platform
                        print(json.dumps(trans_info, ensure_ascii=False))


def batch_select_high_quality_qa_and_white_answer_to_json(batch_file, white_name_file, field_num=6):
    """
    批量选择高质量以及在白名单中的数据QA数据并转换为JSON文件
    """
    white_name_dict = load_white_name_permission_dict(white_name_file)            
    with open(batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            columns = line.strip().split('\t')
            if len(columns) > field_num:
                json_file = columns[field_num]
                logging.info(f'start process json_file: {json_file}')
                with open(json_file, 'r', encoding='utf-8') as jf:
                    
                    json_data = json.load(jf)
                    # 分别处理高质量和中等质量数据                    
                    qa_list = list()
                    for k, v_list in json_data.items():
                        for v in v_list:
                            v['quality'] = k
                        qa_list.extend(v_list)
                    for qa in qa_list:
                        from_file_name = qa.get('from_file_name', '')
                        platform = qa.get('platform', '')

                        file_name = qa.get('from_user', '')
                        if file_name not in white_name_dict.get(platform, {}).get('writers', set()):
                            continue
                        if qa['quality'] not in white_name_dict.get(platform, {}).get('permissions', set()):
                            continue
                        trans_info = {'title': qa['q'], 'content': qa['a'], 'document_name': file_name} # document_name 用于在fastgpt下建立不同的document
                        if platform:
                            trans_info['platform'] = platform
                        print(json.dumps(trans_info, ensure_ascii=False))


def excel_to_qa_json(excel_file: str):
    """
    将带平台格式的excel数据转换为qa json格式
    
    Args:
        excel_file: Excel文件路径
    
    输出格式示例:
    {
        "title": "问题内容",
        "content": "答案内容",
        "document_name": "sheet名称",
        "platform": "平台名称"
    }
    """
    try:
        wb = load_workbook(excel_file, read_only=True)
        
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            # 获取表头
            headers = [cell.value for cell in next(ws.rows)]
            
            # 检查必要的列是否存在
            platform_idx = headers.index("平台") if "平台" in headers else None
            question_idx = headers.index("问题")
            answer_idx = headers.index("答案")
            
            # 遍历数据行
            for row in list(ws.rows)[1:]:  # 跳过表头
                trans_info = {
                    "title": row[question_idx].value,
                    "content": row[answer_idx].value,
                    "document_name": sheet_name
                }
                
                if platform_idx is not None:
                    platform = row[platform_idx].value
                    if platform:  # 只在平台值非空时添加
                        trans_info["platform"] = platform
                
                print(json.dumps(trans_info, ensure_ascii=False))
                
    except Exception as e:
        logging.error(f"处理Excel文件时发生错误: {str(e)}")
        raise


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')  
    import fire
    fire.Fire({
        'batch_json_to_excel': batch_json_to_excel,
        'output_qa_json_trans_result': output_qa_json_trans_result,
        'output_page_content_trans_result': output_page_content_trans_result,
        'batch_split_json_quality_to_excel': batch_split_json_quality_to_excel,
        'batch_select_high_quality_qa_to_json': batch_select_high_quality_qa_to_json,
        'excel_to_qa_json': excel_to_qa_json,
        'batch_select_high_quality_qa_and_white_answer_to_json': batch_select_high_quality_qa_and_white_answer_to_json,
    })
