import logging
import os
import fitz
from off_task_tools.minio_downloader import MinioDownloader
from config_tools.config import GLOBAL_CONFIG
from knowledge_clear_tool.wordtotext import parse_pdf_to_json, convert_docx_to_pdf


S3_DOWNLOADER = MinioDownloader(GLOBAL_CONFIG.get('minio_config_path'))

# 每个文档固定 100 积分（2026-09-17 起）。
# 之前按 token_count/10000 + image_count 算，改成按文档数计费：
# 前端只要知道「几个文档 = 几百积分」，不再依赖文档内容。
# 字符/token/图片数仍照常统计并返回，供观察用，但不再参与计费。
CREDITS_PER_DOCUMENT = 100


def estimate_tokens_from_text(text: str) -> int:
    """
    估算文本的token数
    简单规则：
    - 中文字符：1个字符约等于1.5个token
    - 英文单词：平均4-5个字母一个token
    - 数字和标点：按字符数/4估算
    """
    chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
    english_words = len([word for word in text.split() if any(c.isalpha() for c in word)])
    other_chars = len(text) - chinese_chars
    
    # 估算token数
    tokens = int(chinese_chars * 1.5 + english_words * 1.2 + other_chars * 0.25)
    return tokens


def count_pdf_stats(pdf_path: str, image_size_limit: int = 1024*1) -> dict:
    """
    统计PDF文档的字数和大于指定大小的图片数
    
    Args:
        pdf_path: PDF文件路径
        image_size_limit: 图片大小阈值（字节），默认1MB
        
    Returns:
        dict: {
            'char_count': 字符数,
            'token_count': token数,
            'image_count': 符合大小要求的图片数,
            'credits': 积分数
        }
    """
    try:
        pdf = fitz.open(pdf_path)
        
        total_text = ""
        valid_images = 0
        
        # 遍历每一页
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            
            # 提取文本
            text = page.get_text()
            if text:
                total_text += text
            
            # 提取图片并检查大小
            image_list = page.get_images()
            for img in image_list:
                try:
                    xref = img[0]
                    base_image = pdf.extract_image(xref)
                    if base_image:
                        image_data = base_image["image"]
                        # 检查图片大小是否大于阈值
                        if len(image_data) > image_size_limit:
                    
                            valid_images += 1
                        else:
                            logging.info(f"图片大小小于阈值: {len(image_data)} bytes")
                except Exception as e:
                    logging.warning(f"处理页面 {page_num + 1} 的图片时发生错误: {str(e)}")
                    continue
        
        pdf.close()
        
        # 统计字符数和token数
        char_count = len(total_text)
        token_count = estimate_tokens_from_text(total_text)
        
        # 每个文档固定 100 积分，不再按 token/图片数量计价
        credits = CREDITS_PER_DOCUMENT

        return {
            'char_count': char_count,
            'token_count': token_count,
            'image_count': valid_images,
            'credits': credits
        }
        
    except Exception as e:
        logging.error(f"统计PDF文件 {pdf_path} 时发生错误: {str(e)}")
        return {
            'char_count': 0,
            'token_count': 0,
            'image_count': 0,
            'credits': 0,
            'error': str(e)
        }


def asscess_document_clear_price(files_info_list: list[dict], image_size_limit: int = 1024):
    """
    批量评估文档解析成本
    
    Args:
        files_info_list: 文件信息列表
        image_size_limit: 图片大小阈值（字节），默认1MB
        
    Returns:
        dict: {
            'total_credits': 总积分数,
            'total_chars': 总字符数,
            'total_tokens': 总token数,
            'total_images': 总图片数,
            'detail_info': [每个文档的详细统计],
            'error_files': 处理失败的文件列表
        }
    """
    total_credits = 0
    total_chars = 0
    total_tokens = 0
    total_images = 0
    detail_info = []
    error_files = []
    
    for file_info in files_info_list:
        file_name = file_info.get('name', '')
        file_ext = file_info.get('ext', '')
        store_method = file_info.get('store_method', '')
        address = file_info.get('address', '')
        
        if not file_name or not address:
            logging.warning(f"文件信息不完整，跳过: {file_info}")
            error_files.append({
                'file_info': file_info,
                'error': '文件信息不完整'
            })
            continue
            
        save_dir = GLOBAL_CONFIG.get('tmp_file_dir')
        # 生成本地文件路径
        local_filename = f"{file_name}.{file_ext}" if file_ext else file_name
        local_path = os.path.join(save_dir, local_filename)
        logging.info(f"开始下载文件: {file_name}")
        logging.info(f"存储方式: {store_method}, 地址: {address}")
        logging.info(f"本地路径: {local_path}")
        
        success = S3_DOWNLOADER.download_file(file_info, local_path)  
        
        if success and os.path.exists(local_path):
            # 评估文档成本
            try:
                stats = access_document_clear_price(local_path, image_size_limit)
                
                if stats and 'error' not in stats:
                    # 累加统计数据
                    total_credits += stats['credits']
                    total_chars += stats['char_count']
                    total_tokens += stats['token_count']
                    total_images += stats['image_count']
                    
                    # 记录详细信息
                    detail_info.append({
                        'file_name': file_name,
                        'file_ext': file_ext,
                        'local_path': local_path,
                        'char_count': stats['char_count'],
                        'token_count': stats['token_count'],
                        'image_count': stats['image_count'],
                        'credits': stats['credits']
                    })
                    logging.info(f"文件 {file_name} 评估完成: 积分={stats['credits']:.2f}, "
                               f"字符数={stats['char_count']}, Token数={stats['token_count']}, "
                               f"图片数={stats['image_count']}")
                else:
                    error_msg = stats.get('error', '未知错误') if stats else '统计失败'
                    logging.error(f"文件 {file_name} 评估失败: {error_msg}")
                    error_files.append({
                        'file_info': file_info,
                        'local_path': local_path,
                        'error': error_msg
                    })
                    
            except Exception as e:
                logging.error(f"处理文件 {file_name} 时发生异常: {str(e)}")
                error_files.append({
                    'file_info': file_info,
                    'local_path': local_path,
                    'error': str(e)
                })
        else:
            logging.error(f"文件下载失败: {file_name}")
            error_files.append({
                'file_info': file_info,
                'error': '文件下载失败'
            })
    
    result = {
        'total_credits': total_credits,
        'total_chars': total_chars,
        'total_tokens': total_tokens,
        'total_images': total_images,
        'detail_info': detail_info,
        'error_files': error_files
    }
    
    logging.info(f"批量评估完成: 总积分={total_credits:.2f}, "
                f"总字符数={total_chars}, 总Token数={total_tokens}, "
                f"总图片数={total_images}, 成功={len(detail_info)}, 失败={len(error_files)}")
    
    return result
        

def access_document_clear_price(file_path: str, image_size_limit: int = 1024, re_parse: bool = False):
    """
    评估单个文档的解析成本
    
    Args:
        file_path: 文档文件路径（支持.pdf, .docx, .doc）
        image_size_limit: 图片大小阈值（字节），默认1MB
        
    Returns:
        dict: {
            'char_count': 字符数,
            'token_count': token数,
            'image_count': 符合大小要求的图片数,
            'credits': 积分数
        }
        或包含'error'字段的dict（如果处理失败）
    """
    file_extension = os.path.splitext(file_path)[-1].lower()
    pdf_path = file_path
    temp_pdf_path = None  # 用于记录临时生成的PDF文件
    
    # 如果是docx/doc文件，先转换为PDF
    if file_extension in ['.docx', '.doc']:
        logging.info(f"开始转换文档为PDF: {file_path}")
        converted_path = convert_docx_to_pdf(file_path, re_parse=re_parse)
        
        if converted_path is None:
            logging.error(f"无法转换文件: {file_path}")
            return {
                'char_count': 0,
                'token_count': 0,
                'image_count': 0,
                'credits': 0,
                'error': '文件转换失败'
            }
        
        # 检查是否成功转换为PDF
        if converted_path.endswith('.pdf'):
            pdf_path = converted_path
            temp_pdf_path = converted_path  # 记录临时PDF，处理完后需要删除
            logging.info(f"文档已转换为PDF: {pdf_path}")
        else:
            # 转换失败，返回原始docx文件路径（暂不支持直接统计docx）
            logging.warning(f"文档转换为PDF失败，暂不支持直接统计DOCX文件: {file_path}")
            return {
                'char_count': 0,
                'token_count': 0,
                'image_count': 0,
                'credits': 0,
                'error': 'DOCX转换失败，暂不支持直接统计'
            }
    elif file_extension != '.pdf':
        logging.error(f"不支持的文件类型: {file_extension}")
        return {
            'char_count': 0,
            'token_count': 0,
            'image_count': 0,
            'credits': 0,
            'error': f'不支持的文件类型: {file_extension}'
        }
    
    # 统计PDF文档
    try:
        logging.info(f"开始统计PDF文档: {pdf_path}")
        stats = count_pdf_stats(pdf_path, image_size_limit)
        logging.info(f"文档统计完成: {file_path}, 积分={stats.get('credits', 0):.2f}")
        
        # 如果是临时生成的PDF，删除它
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
                logging.info(f"删除临时PDF文件: {temp_pdf_path}")
            except Exception as e:
                logging.warning(f"删除临时PDF文件失败: {temp_pdf_path}, 错误: {str(e)}")
        
        return stats
        
    except Exception as e:
        logging.error(f"统计文档时发生异常: {file_path}, 错误: {str(e)}")
        
        # 清理临时文件
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
            except:
                pass
        
        return {
            'char_count': 0,
            'token_count': 0,
            'image_count': 0,
            'credits': 0,
            'error': str(e)
        }



if __name__ == '__main__':
    import sys
    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')      
    files_info_list = [
        {
            'name': 'test.pdf',
            'ext': 'pdf',
            'store_method': 'minio',
            'address': 'boot-admin/oceanpay/20251020/1980103780009074690.pdf'
        },
        {
            'name': 'test2.pdf',
            'ext': 'pdf',
            'store_method': 'minio',
            'address': 'boot-admin/oceanpay/20251020/1980103981683793921.pdf'
        },
        
    ]
    result = asscess_document_clear_price(files_info_list, image_size_limit=1024)
    print(result)