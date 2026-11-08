from PIL import Image
from kdb.mining.common.schema.excel_import import _canonical_excel_field
from kdb.mining.common.schema.excel_import import map_excel_columns
from openpyxl import load_workbook
from typing import Any
from typing import Dict
from typing import List
from typing import Union
import io
import json
import logging
import os
import traceback

def trans_review_excel_to_json_file(excel_file: str, output_file: str, list_field_names: Union[str, List[str]] = None, image_save_dir: str = None):
    """
    将审核后的excel文件转换为JSON格式文件
    """
    try:
        # 处理list_field_names参数
        if isinstance(list_field_names, str):
            list_field_names = [name.strip() for name in list_field_names.split(',') if name.strip()]

        wb = load_workbook(excel_file, read_only=False, data_only=True)
        excel_base_name = os.path.basename(excel_file)
        excel_name = os.path.splitext(excel_base_name)[0]

        # 如果指定了图片保存目录，确保目录存在
        if image_save_dir:
            os.makedirs(image_save_dir, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                # 获取表头（第一行作为key）
                headers = [cell.value for cell in next(ws.rows) if cell.value is not None]
                column_mapping = map_excel_columns(headers)
                canonical_by_idx = {idx: field for field, idx in column_mapping.items()} if column_mapping else {}
                logging.info(f"表头: {headers}")

                # 获取所有图片及其位置
                image_map = {}
                for image in ws._images:
                    logging.info(f"Found image: {image}")
                    if not hasattr(image, 'anchor'):
                        continue

                    try:
                        # 获取图片位置
                        row = image.anchor._from.row + 1
                        col = image.anchor._from.col + 1
                        logging.info(f"Image position: row={row}, col={col}")

                        # 尝试获取图片数据
                        if hasattr(image, '_data'):
                            img_data = image._data()
                        elif hasattr(image, 'ref') and hasattr(image.ref, 'image'):
                            if hasattr(image.ref.image, 'blob'):
                                img_data = image.ref.image.blob
                            elif hasattr(image.ref.image, '_data'):
                                img_data = image.ref.image._data()
                            else:
                                logging.warning(f"Cannot get image data from {image}")
                                continue
                        else:
                            logging.warning(f"Cannot get image data from {image}")
                            continue

                        # 验证图片数据
                        try:
                            img = Image.open(io.BytesIO(img_data))
                            # 如果能打开图片，说明数据是有效的
                            if (row, col) not in image_map:
                                image_map[(row, col)] = []
                            image_map[(row, col)].append((img_data, img.format.lower() if img.format else 'png'))
                        except Exception as e:
                            logging.error(f"Invalid image data: {str(e)}")
                            continue

                    except Exception as e:
                        logging.error(f"Error processing image: {str(e)}")
                        continue

                # 遍历数据行
                for row_idx, row in enumerate(list(ws.rows)[1:], 2):  # 从2开始，因为1是表头
                    row_data = {}
                    ext_info = {
                        'from_file_name': f'{excel_name}_{sheet_name}'
                    }
                    row_data['ext_info'] = ext_info

                    # 处理每一列的数据
                    for col_idx, (header, cell) in enumerate(zip(headers, row), 1):
                        if cell.value is not None and str(cell.value).strip():  # 只处理非空值
                            field_name = _canonical_excel_field(header, col_idx - 1, canonical_by_idx)
                            field_name_str = str(field_name)
                            if list_field_names and field_name in list_field_names:
                                value_list = [v.strip() for v in str(cell.value).split('|') if v.strip()]
                                row_data[field_name] = value_list
                            elif field_name == 'indexes':
                                text_list = str(cell.value).split('|')
                                text_list = [{"text": t.strip()} for t in text_list if t.strip()]
                                row_data[field_name] = text_list
                            elif field_name_str.find("image_path") != -1:
                                image_path_list = str(cell.value).split('|')
                                row_data.setdefault('ori_image_path', [])
                                row_data['ori_image_path'].extend(image_path_list)
                            elif field_name_str.find("image_data") != -1 and image_save_dir:
                                # 检查该位置是否有图片
                                cell_pos = (row_idx, col_idx)
                                logging.info(f"Checking for image at position {cell_pos}")
                                if cell_pos in image_map:
                                    row_data.setdefault('ori_image_path', [])
                                    for idx, (img_data, img_format) in enumerate(image_map[cell_pos]):
                                        try:
                                            # 构建图片文件名
                                            image_filename = f"{excel_name}_{row_idx}_{col_idx}_{idx}.{img_format}"
                                            image_path = os.path.join(image_save_dir, image_filename)

                                            # 保存图片数据
                                            with open(image_path, 'wb') as f_img:
                                                f_img.write(img_data)

                                            # 在JSON中记录图片路径
                                            row_data['ori_image_path'].append(image_path)
                                            logging.info(f"Saved image to {image_path}")
                                        except Exception as e:
                                            tb = traceback.format_exc()
                                            logging.error(f"保存图片失败: {str(e)}")
                                            logging.error(f"tb: {tb}")
                            else:
                                row_data[field_name] = cell.value

                    # 添加 multimodal_contents 字段（纯文本格式）
                    if 'content' in row_data and row_data['content']:
                        row_data['multimodal_contents'] = [
                            {"type": "text", "content": row_data['content']}
                        ]

                    # 写入JSON行
                    if len(row_data) > 1:  # 确保不只有ext_info
                        f.write(json.dumps(row_data, ensure_ascii=False) + '\n')

    except Exception as e:
        tb = traceback.format_exc()
        logging.error('tb[%s]', tb)
        logging.error(f"转换Excel到JSON时发生错误: {str(e)}")
        raise


def trans_web_excel_to_json_file(excel_file: str, output_file: str, list_field_names: Union[str, List[str]] = None, image_save_dir: str = None, extra_field_name_dict: Dict[str, Any] = None):
    """
    将审核后的excel文件转换为JSON格式文件
    """
    try:
        extra_field_names = ['category_id', 'category_name', 'task_id', 'client', 'file_name', 'dataset', 'data_type', 'from_type', 'from_type_norm', 'audit_result', 'index_name'] # 可以外部传入的
        # 处理list_field_names参数
        if isinstance(list_field_names, str):
            list_field_names = [name.strip() for name in list_field_names.split(',') if name.strip()]

        wb = load_workbook(excel_file, read_only=False, data_only=True)
        excel_base_name = os.path.basename(excel_file)
        excel_name = os.path.splitext(excel_base_name)[0]

        # 如果指定了图片保存目录，确保目录存在
        if image_save_dir:
            os.makedirs(image_save_dir, exist_ok=True)

        # 获取类目映射（用于补全category_name和category_id）
        name_to_id_map = {}
        id_to_name_map = {}
        if extra_field_name_dict and extra_field_name_dict.get('client'):
            try:
                from kdb.shared.categories.trees import get_category_maps
                name_to_id_map, id_to_name_map = get_category_maps(extra_field_name_dict.get('client'))
                if name_to_id_map:
                    logging.info(f"成功获取客户端 {extra_field_name_dict.get('client')} 的类目映射，共 {len(name_to_id_map)} 个类目")
            except Exception as e:
                logging.warning(f"获取类目映射失败: {e}")

        with open(output_file, 'w', encoding='utf-8') as f:
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                # 获取表头（第一行作为key）
                headers = [cell.value for cell in next(ws.rows) if cell.value is not None]
                column_mapping = map_excel_columns(headers)
                canonical_by_idx = {idx: field for field, idx in column_mapping.items()} if column_mapping else {}
                logging.info(f"表头: {headers}")

                # 获取所有图片及其位置
                image_map = {}
                for image in ws._images:
                    logging.info(f"Found image: {image}")
                    if not hasattr(image, 'anchor'):
                        continue

                    try:
                        # 获取图片位置
                        row = image.anchor._from.row + 1
                        col = image.anchor._from.col + 1
                        logging.info(f"Image position: row={row}, col={col}")

                        # 尝试获取图片数据
                        if hasattr(image, '_data'):
                            img_data = image._data()
                        elif hasattr(image, 'ref') and hasattr(image.ref, 'image'):
                            if hasattr(image.ref.image, 'blob'):
                                img_data = image.ref.image.blob
                            elif hasattr(image.ref.image, '_data'):
                                img_data = image.ref.image._data()
                            else:
                                logging.warning(f"Cannot get image data from {image}")
                                continue
                        else:
                            logging.warning(f"Cannot get image data from {image}")
                            continue

                        # 验证图片数据
                        try:
                            img = Image.open(io.BytesIO(img_data))
                            # 如果能打开图片，说明数据是有效的
                            if (row, col) not in image_map:
                                image_map[(row, col)] = []
                            image_map[(row, col)].append((img_data, img.format.lower() if img.format else 'png'))
                        except Exception as e:
                            logging.error(f"Invalid image data: {str(e)}")
                            continue

                    except Exception as e:
                        logging.error(f"Error processing image: {str(e)}")
                        continue

                # 遍历数据行
                for row_idx, row in enumerate(list(ws.rows)[1:], 2):  # 从2开始，因为1是表头
                    row_data = {}
                    ext_info = {
                        'from_file_name': f'{excel_name}_{sheet_name}'
                    }
                    row_data['ext_info'] = ext_info

                    # 处理每一列的数据
                    for col_idx, (header, cell) in enumerate(zip(headers, row), 1):
                        if cell.value is not None and str(cell.value).strip():  # 只处理非空值
                            field_name = _canonical_excel_field(header, col_idx - 1, canonical_by_idx)
                            field_name_str = str(field_name)
                            header_str = str(header)
                            if list_field_names and field_name in list_field_names:
                                value_list = [v.strip() for v in str(cell.value).split('|') if v.strip()]
                                row_data[field_name] = value_list
                            elif field_name == 'indexes':
                                text_list = str(cell.value).split('|')
                                text_list = [{"text": t.strip()} for t in text_list if t.strip()]
                                row_data[field_name] = text_list
                            elif field_name_str.find("image_path") != -1:
                                image_path_list = str(cell.value).split('|')
                                row_data.setdefault('ori_image_path', [])
                                row_data['ori_image_path'].extend(image_path_list)
                            elif field_name == 'title' or header_str.find("Question") != -1:
                                row_data['title'] = cell.value
                            elif field_name == 'content' or header_str.find("Answer") != -1:
                                row_data['content'] = cell.value
                            elif field_name_str.find("image_data") != -1 and image_save_dir:
                                # 检查该位置是否有图片
                                cell_pos = (row_idx, col_idx)
                                logging.info(f"Checking for image at position {cell_pos}")
                                if cell_pos in image_map:
                                    row_data.setdefault('ori_image_path', [])
                                    for idx, (img_data, img_format) in enumerate(image_map[cell_pos]):
                                        try:
                                            # 构建图片文件名
                                            image_filename = f"{excel_name}_{row_idx}_{col_idx}_{idx}.{img_format}"
                                            image_path = os.path.join(image_save_dir, image_filename)

                                            # 保存图片数据
                                            with open(image_path, 'wb') as f_img:
                                                f_img.write(img_data)

                                            # 在JSON中记录图片路径
                                            row_data['ori_image_path'].append(image_path)
                                            logging.info(f"Saved image to {image_path}")
                                        except Exception as e:
                                            tb = traceback.format_exc()
                                            logging.error(f"保存图片失败: {str(e)}")
                                            logging.error(f"tb: {tb}")
                            else:
                                row_data[field_name] = cell.value
                    if len(row_data) <= 1: # 什么数据都没有, 只有ext_info
                        continue

                    if name_to_id_map or id_to_name_map:
                        cat_name = row_data.get('category_name')
                        cat_id = row_data.get('category_id')
                        if cat_name and not cat_id and cat_name in name_to_id_map:
                            row_data['category_id'] = name_to_id_map[cat_name]
                        elif cat_id and not cat_name and str(cat_id) in id_to_name_map:
                            row_data['category_name'] = id_to_name_map[str(cat_id)]

                    for extra_field_name in extra_field_names:
                        if extra_field_name not in row_data and extra_field_name_dict.get(extra_field_name):
                            row_data[extra_field_name] = extra_field_name_dict.get(extra_field_name)
                    if not row_data.get('data_type'):
                        if 'title' in row_data:
                            row_data['data_type'] = 'qa'
                        else:
                            row_data['data_type'] = 'segment'

                    # 补全类目信息（在转换成category_infos之前）


                    if 'category_id' in row_data and 'category_name' in row_data:
                        row_data['category_infos'] = [{
                            'category_id': row_data['category_id'],
                            'category_name': row_data['category_name'],
                            'score': 1.0,
                            'source': 'manual'
                        }]
                    if 'category_id' in row_data:
                        del row_data['category_id']
                    if 'category_name' in row_data:
                        del row_data['category_name']

                    # 添加 multimodal_contents 字段（纯文本格式）
                    if 'content' in row_data and row_data['content']:
                        row_data['multimodal_contents'] = [
                            {"type": "text", "content": row_data['content']}
                        ]
                    if 'from_type' not in row_data:
                        row_data['from_type'] = "manual"

                    # 写入JSON行
                      # 确保不只有ext_info
                    f.write(json.dumps(row_data, ensure_ascii=False) + '\n')

    except Exception as e:
        tb = traceback.format_exc()
        logging.error('tb[%s]', tb)
        logging.error(f"转换Excel到JSON时发生错误: {str(e)}")
        raise
