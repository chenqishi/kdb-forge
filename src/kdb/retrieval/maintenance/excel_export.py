from openpyxl import Workbook
from openpyxl.utils import get_column_letter
import json
import logging

def trans_es_data_to_excel(es_data_file: str, output_file: str, headers=None, is_need_trans_column=False):
    """
    将ES数据转换为Excel文件
    
    Args:
        es_data_file (str): ES数据文件路径,每行为一个JSON格式的数据
        output_file (str): 输出的Excel文件路径
    """
    try:
        # 创建新的工作簿
        wb = Workbook()
        ws = wb.active

        # 写入表头
        if headers is None:
            headers = ['_id', 'title', 'content', 'synonyms_title', 'supply_info_query',
                  'platform', 'data_type', 'from_type', 'audit_result', 'quality_level', 'from_chat_history']
        elif isinstance(headers, (list, tuple)):  # list 之前会掉进下面的 else 报错
            headers = list(headers)
        elif isinstance(headers, str):
            headers = headers.split(',')
        else:
            raise ValueError(f"headers参数类型错误: {type(headers)}")
        if isinstance(is_need_trans_column, str):
            is_need_trans_column = is_need_trans_column.lower() == 'true'
        if is_need_trans_column: # 保证是否已经上线在最后
            if '是否已经上线'in headers:
                headers.remove('是否已经上线')
            headers.append('是否已经上线')
        ws.append(headers)

        # 读取并处理每行数据
        with open(es_data_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    # 解析JSON数据
                    data = json.loads(line.strip())

                    # 准备行数据
                    row_data = []
                    for header in headers:
                        if header == 'synonyms_title':
                            row_data.append('|'.join(data.get(header, [])))
                        else:
                            row_data.append(data.get(header, ''))
                    if is_need_trans_column:
                        is_audit = data.get('audit_result', -1)
                        quality_level = data.get('quality_level', '')
                        if is_audit != 0 and quality_level == 'high':
                            row_data.append('是')
                        elif is_audit == 1:
                            row_data.append('是')
                        else:
                            row_data.append('否')
                    # 写入行数据
                    ws.append(row_data)

                except json.JSONDecodeError as e:
                    logging.error(f"JSON解析错误: {str(e)}, 行内容: {line}")
                    continue
                except Exception as e:
                    logging.error(f"处理数据行时发生错误: {str(e)}, 行内容: {line}")
                    continue

        # 调整列宽
        for column in ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 100)  # 限制最大宽度为100
            ws.column_dimensions[column_letter].width = adjusted_width

        # 保存Excel文件
        wb.save(output_file)
        logging.info(f"Excel文件已保存到: {output_file}")

    except Exception as e:
        logging.error(f"转换ES数据到Excel时发生错误: {str(e)}")
        raise


def trans_es_modify_data_to_excel(es_data_file: str, output_file: str, headers=None):
    """
    将ES数据转换为Excel文件
    
    Args:
        es_data_file (str): ES数据文件路径,每行为一个JSON格式的数据
        output_file (str): 输出的Excel文件路径
        仅过滤is_modify为True的数据
    """
    try:
        # 创建新的工作簿
        wb = Workbook()
        ws = wb.active

        # 写入表头
        if headers is None:
            headers = ['_id', 'title', 'new_content', 'old_content', 'synonyms_title', 'supply_info_query',
                  'platform', 'data_type', 'from_type', 'need_modify', 'quality_level']
        elif isinstance(headers, tuple):
            headers = list(headers)
        elif isinstance(headers, str):
            headers = headers.split(',')
        else:
            raise ValueError(f"headers参数类型错误: {type(headers)}")

        ws.append(headers)

        # 读取并处理每行数据
        with open(es_data_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    # 解析JSON数据
                    data = json.loads(line.strip())
                    if not data.get('is_modify', False):
                        continue

                    # 准备行数据
                    row_data = []
                    for header in headers:
                        if header == 'new_content':
                            row_data.append(data.get('modify_content', ''))
                        elif header == 'old_content':
                            row_data.append(data.get('content', ''))
                        elif header == 'need_modify':
                            row_data.append(int(data.get('is_modify', False)))
                        elif header == 'synonyms_title':
                            row_data.append('|'.join(data.get(header, [])))
                        else:
                            row_data.append(data.get(header, ''))

                    # 写入行数据
                    ws.append(row_data)

                except json.JSONDecodeError as e:
                    logging.error(f"JSON解析错误: {str(e)}, 行内容: {line}")
                    continue
                except Exception as e:
                    logging.error(f"处理数据行时发生错误: {str(e)}, 行内容: {line}")
                    continue

        # 调整列宽
        for column in ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 100)  # 限制最大宽度为100
            ws.column_dimensions[column_letter].width = adjusted_width

        # 保存Excel文件
        wb.save(output_file)
        logging.info(f"Excel文件已保存到: {output_file}")

    except Exception as e:
        logging.error(f"转换ES数据到Excel时发生错误: {str(e)}")
        raise
