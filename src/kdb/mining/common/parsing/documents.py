import PyPDF2
import json
import os
from PIL import Image
import io
import logging
import sys
import hashlib
from docx import Document
import re
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx2pdf import convert
import tempfile
import traceback
import fitz
import time
import platform
import subprocess
import uuid
from urllib.request import urlretrieve
from urllib.parse import urlparse
try:
    from openpyxl import load_workbook as _openpyxl_load_workbook
except ImportError:
    _openpyxl_load_workbook = None


def parse_excel_to_json(excel_path, data_dir, chunk_size=30):
    """
    Parse an Excel file (.xlsx/.xls) as unstructured document pages.

    Output format matches parse_pdf_to_json:
      {"1": [{"type": "text", "text_content": "...", "image_path": null}], ...}

    Each "page" covers chunk_size rows from one sheet, prefixed with file name,
    sheet name, row range, and column headers so downstream LLMs retain table context.
    """
    if _openpyxl_load_workbook is None:
        return json.dumps({"error": "openpyxl is not installed"})

    result = {}
    page_no = 1
    file_name = os.path.basename(excel_path)
    try:
        from kdb.mining.common.schema.excel_import import map_excel_columns
    except Exception:
        map_excel_columns = None

    try:
        wb = _openpyxl_load_workbook(excel_path, read_only=True, data_only=True)
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            all_rows = list(ws.rows)
            if not all_rows:
                continue
            headers = [cell.value for cell in all_rows[0]]
            header_str = ', '.join(str(h) for h in headers if h is not None)
            column_mapping = map_excel_columns(headers) if map_excel_columns else None
            data_rows = all_rows[1:]

            # Emit at least one page even if there are no data rows (header-only sheet)
            total_chunks = max(1, (len(data_rows) + chunk_size - 1) // chunk_size) if data_rows else 1
            for chunk_idx in range(total_chunks):
                chunk = data_rows[chunk_idx * chunk_size:(chunk_idx + 1) * chunk_size]
                row_start = chunk_idx * chunk_size + 2  # 1-indexed; row 1 is header
                row_end = row_start + len(chunk) - 1

                lines = [
                    f"文件: {file_name}",
                    f"Sheet: {sheet_name}",
                    f"行范围: {row_start}-{row_end}",
                    f"列标题: {header_str}",
                ]
                if column_mapping:
                    lines.append("解析方式: mapped_structured_excel")
                else:
                    lines.append("解析方式: unstructured_excel")

                for row in chunk:
                    row_parts = []
                    if column_mapping:
                        for field in [
                            'title', 'content', 'indexes', 'synonyms_title', 'supply_info_query',
                            'platform', 'category', 'from_scene', 'data_type', 'from_type',
                            'audit_result'
                        ]:
                            idx = column_mapping.get(field)
                            if idx is None or idx >= len(row):
                                continue
                            value = row[idx].value
                            if value is not None and str(value).strip():
                                row_parts.append(f"{field}: {value}")
                    else:
                        for h, cell in zip(headers, row):
                            if h is not None and cell.value is not None and str(cell.value).strip():
                                row_parts.append(f"{h}: {cell.value}")
                    if row_parts:
                        lines.append('\n'.join(row_parts))

                text_content = '\n'.join(lines)
                if text_content.strip():
                    result[str(page_no)] = [
                        {"type": "text", "text_content": text_content, "image_path": None}
                    ]
                    page_no += 1

        wb.close()
    except Exception as e:
        logging.error(f"处理Excel文件时发生错误: {str(e)}")
        return json.dumps({"error": str(e)})

    if not result:
        return json.dumps({"warning": "没有有效内容"})

    return json.dumps(result, ensure_ascii=False, indent=2)


def _normalize_pdf_image_ext(image_ext):
    if not isinstance(image_ext, str) or not image_ext:
        return "png"
    image_ext = image_ext.lower().lstrip(".")
    if image_ext == "jpeg":
        return "jpg"
    return image_ext or "png"


def _write_pdf_image_file(image_data, image_ext, page_num, img_index, data_dir, metadata=None):
    image_ext = _normalize_pdf_image_ext(image_ext)
    image_filename = f"{page_num}_{img_index}.{image_ext}"
    image_path = os.path.join(data_dir, image_filename)
    with open(image_path, 'wb') as img_file:
        img_file.write(image_data)

    item = {
        "type": "image",
        "text_content": None,
        "image_path": image_path
    }
    if isinstance(metadata, dict):
        item.update(metadata)
    return item


def _extract_rendered_pdf_images(page, page_num, data_dir):
    rendered_images = []
    page_dict = page.get_text("dict")
    for img_index, block in enumerate(page_dict.get("blocks", [])):
        if not isinstance(block, dict) or block.get("type") != 1:
            continue
        image_data = block.get("image")
        if not image_data:
            continue
        metadata = {
            "image_source": "rendered_block",
        }
        if block.get("bbox") is not None:
            metadata["image_bbox"] = block.get("bbox")
        if block.get("width") is not None:
            metadata["image_width"] = block.get("width")
        if block.get("height") is not None:
            metadata["image_height"] = block.get("height")
        rendered_images.append(
            _write_pdf_image_file(
                image_data,
                block.get("ext"),
                page_num,
                len(rendered_images),
                data_dir,
                metadata=metadata,
            )
        )
    return rendered_images


def _extract_pdf_resource_images(pdf, page, page_num, data_dir):
    resource_images = []
    image_list = page.get_images()
    for img_index, img in enumerate(image_list):
        try:
            xref = img[0]  # 获取图片的xref
            base_image = pdf.extract_image(xref)
            if base_image:
                metadata = {
                    "image_source": "pdf_resource",
                    "image_xref": xref,
                }
                resource_images.append(
                    _write_pdf_image_file(
                        base_image["image"],
                        base_image.get("ext"),
                        page_num,
                        img_index,
                        data_dir,
                        metadata=metadata,
                    )
                )
        except Exception as e:
            logging.warning(f"处理页面 {page_num} 的图片 {img_index} 时发生错误: {str(e)}")
            continue
    return resource_images


def parse_pdf_to_json(pdf_path, data_dir):
    result = {}
    
    try:
        pdf = fitz.open(pdf_path)
        
        # 遍历每一页
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            content = []
            
            # 提取文本
            text = page.get_text()
            if text:
                # 移除可能的页码或开头的数字
                lines = text.split('\n')
                if lines:
                    first_line = lines[0].strip()
                    # 检查开头的数字是否等于当前页码
                    match = re.match(r'^(\d+)', first_line)
                    if match and int(match.group(1)) == page_num + 1:
                        first_line = first_line[len(match.group(1)):].strip()
                    lines[0] = first_line
                cleaned_text = '\n'.join(lines).strip()
                
                if cleaned_text:
                    content.append({
                        "type": "text",
                        "text_content": cleaned_text,
                        "image_path": None
                    })
            
            # 提取实际绘制图片。PyMuPDF page.get_images() 返回页面资源字典，
            # 对 LibreOffice 转出的 PDF 可能把全局资源在每页重复列出。
            page_number = page_num + 1
            if not content:
                # Image-only slides can use clipping/masks that get_text("dict")
                # omits. Render the visible page so OCR sees the complete slide.
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                content.append(_write_pdf_image_file(
                    pix.tobytes("png"), "png", page_number, 0, data_dir,
                    metadata={"image_source": "rendered_page",
                              "image_width": pix.width, "image_height": pix.height},
                ))
                result[str(page_number)] = content
                continue
            try:
                content.extend(_extract_rendered_pdf_images(page, page_number, data_dir))
            except Exception as e:
                logging.warning(
                    f"提取页面 {page_number} 实际绘制图片失败，回退资源图片提取: {str(e)}"
                )
                content.extend(_extract_pdf_resource_images(pdf, page, page_number, data_dir))
            
            if content:  # 只有当页面有内容时才添加到结果中
                result[str(page_num + 1)] = content
        
        pdf.close()
    except Exception as e:
        logging.error(f"处理PDF文件时发生错误: {str(e)}")
        return json.dumps({"error": str(e)})
    
    return json.dumps(result, ensure_ascii=False, indent=2)


# 使用示例
# pdf_path = 'path/to/your/pdf/file.pdf'
# data_dir = 'path/to/your/data/directory'
# json_output = parse_pdf_to_json(pdf_path, data_dir)
# print(json_output)


def _count_text_length(text):
    """
    计算文本长度（中文字符数 + 英文单词数）
    
    Args:
        text: 文本内容
        
    Returns:
        int: 文本长度
    """
    if not text:
        return 0
    
    # 统计中文字符（包括中文标点）
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text))
    
    # 统计英文单词（按空格分割）
    # 先移除中文字符，只保留英文部分
    english_text = re.sub(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', ' ', text)
    # 按空格分割并过滤空字符串
    english_words = [w for w in english_text.split() if w.strip()]
    
    return chinese_chars + len(english_words)


def _extract_markdown_images(text):
    """
    提取 markdown 格式的图片链接
    
    Args:
        text: 文本内容
        
    Returns:
        list: [(完整markdown表达式, 图片URL), ...]
    """
    # Markdown 图片格式：![alt text](url) 或 ![](url)
    markdown_image_pattern = re.compile(
        r'(!\[([^\]]*)\]\(([^\)]+)\))',  # 匹配 ![alt](url) 格式
        re.IGNORECASE
    )
    
    results = []
    for match in markdown_image_pattern.finditer(text):
        full_markdown = match.group(1)  # 完整的 markdown 格式
        url = match.group(3).strip()  # 图片 URL
        
        # 处理可能包含的引号和标题
        url = url.strip('"\'')
        # 如果包含空格，取第一部分（markdown 支持 ![alt](url "title") 格式）
        url = url.split()[0] if url.split() else url
        
        results.append((full_markdown, url))
    
    return results


def _extract_plain_urls(text):
    """
    提取文本中的普通 URL（http/https 开头）
    
    Args:
        text: 文本内容
        
    Returns:
        list: [url, ...]
    """
    # 匹配 URL 模式（参考 multimodal_process.py 的实现）
    url_pattern = re.compile(
        r'(https?://'  # http:// or https://
        r'(?:[-\w.@])+'  # 域名部分
        r'(?::[0-9]+)?'  # 可选端口
        r'(?:/(?:[^\s<>"\'`\]]*)?)?'  # 路径部分
        r'(?:\?[^\s<>"\'`\]\]]*)?'  # 查询字符串
        r'(?:#[^\s<>"\'`\]\]]*)?)'  # 锚点部分
        r'(?=[^\w\-./?#]|$)',  # 前瞻断言
        re.IGNORECASE
    )
    
    return url_pattern.findall(text)


def _download_remote_file(url, data_dir):
    """
    下载远程文件到本地
    
    Args:
        url: 文件 URL
        data_dir: 保存目录
        
    Returns:
        str: 本地文件路径，失败返回 None
    """
    try:
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        
        # 如果没有文件名或扩展名，生成默认文件名
        if not filename or '.' not in filename:
            # 尝试从 URL 推断文件类型
            ext = '.png'  # 默认为图片
            if any(img_ext in url.lower() for img_ext in ['.jpg', '.jpeg']):
                ext = '.jpg'
            elif '.gif' in url.lower():
                ext = '.gif'
            elif '.webp' in url.lower():
                ext = '.webp'
            filename = f"{uuid.uuid4().hex}{ext}"
        
        # 确保文件名唯一
        local_path = os.path.join(data_dir, filename)
        if os.path.exists(local_path):
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
            local_path = os.path.join(data_dir, filename)
        
        # 下载文件
        urlretrieve(url, local_path)
        logging.info(f"下载文件成功: {url} -> {local_path}")
        return local_path
        
    except Exception as e:
        logging.warning(f"下载文件失败: {url}, error: {e}")
        return None


def _split_text_by_elements(text):
    """
    将文本按照元素分割（文本段落和图片）
    
    Args:
        text: 原始文本
        
    Returns:
        list: [{"type": "text", "content": "..."}, {"type": "image_url", "url": "..."}, ...]
    """
    elements = []
    
    # 提取 markdown 图片
    markdown_images = _extract_markdown_images(text)
    
    if not markdown_images:
        # 没有图片，整个文本作为一个元素
        if text.strip():
            elements.append({"type": "text", "content": text})
        return elements
    
    # 按照图片位置分割文本
    last_pos = 0
    for markdown_expr, url in markdown_images:
        pos = text.find(markdown_expr, last_pos)
        if pos == -1:
            continue
        
        # 添加图片之前的文本
        before_text = text[last_pos:pos].strip()
        if before_text:
            elements.append({"type": "text", "content": before_text})
        
        # 添加图片
        elements.append({"type": "image_url", "url": url})
        
        last_pos = pos + len(markdown_expr)
    
    # 添加最后剩余的文本
    remaining_text = text[last_pos:].strip()
    if remaining_text:
        elements.append({"type": "text", "content": remaining_text})
    
    return elements


def parse_txt_to_json(txt_path, data_dir, page_char_limit=2000):
    """
    解析文本文件（txt/markdown）为 JSON 格式
    
    输出格式与 parse_pdf_to_json 一致：
    {
        "1": [
            {"type": "text", "text_content": "...", "image_path": null},
            {"type": "image", "text_content": null, "image_path": "/path/to/image.png"}
        ],
        "2": [...]
    }
    
    Args:
        txt_path: 文本文件路径
        data_dir: 数据保存目录（用于保存下载的图片）
        page_char_limit: 每页字符数限制（按中文字符数+英文单词数计算）
        
    Returns:
        str: JSON 字符串
    """
    result = {}
    
    try:
        # 确保数据目录存在
        os.makedirs(data_dir, exist_ok=True)
        
        # 读取文件内容
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if not content.strip():
            logging.warning(f"文件内容为空: {txt_path}")
            return json.dumps({"warning": "文件内容为空"})
        
        # 分割文本和图片元素
        elements = _split_text_by_elements(content)
        
        # 下载远程图片并转换为本地路径
        processed_elements = []
        for element in elements:
            if element["type"] == "image_url":
                url = element["url"]
                # 判断是否是远程文件
                if url.startswith(('http://', 'https://')):
                    # 下载远程文件
                    local_path = _download_remote_file(url, data_dir)
                    if local_path:
                        processed_elements.append({
                            "type": "image",
                            "text_content": None,
                            "image_path": local_path
                        })
                    else:
                        # 下载失败，记录原始 URL
                        logging.warning(f"无法下载图片，保留URL: {url}")
                        processed_elements.append({
                            "type": "text",
                            "text_content": f"[图片: {url}]",
                            "image_path": None
                        })
                else:
                    # 本地文件路径
                    if os.path.exists(url):
                        processed_elements.append({
                            "type": "image",
                            "text_content": None,
                            "image_path": url
                        })
                    else:
                        logging.warning(f"本地图片不存在: {url}")
                        processed_elements.append({
                            "type": "text",
                            "text_content": f"[图片: {url}]",
                            "image_path": None
                        })
            else:
                # 文本元素
                processed_elements.append({
                    "type": "text",
                    "text_content": element["content"],
                    "image_path": None
                })
        
        # 按照字数限制分页
        current_page = 1
        current_page_content = []
        current_page_length = 0
        
        for element in processed_elements:
            if element["type"] == "image":
                # 图片直接添加到当前页
                current_page_content.append(element)
            else:
                # 文本需要考虑长度限制
                text = element["text_content"]
                text_length = _count_text_length(text)
                
                # 如果当前页为空，或者加入这段文本不超过限制
                #
                # 注意 `text_length <= page_char_limit` 这个前置条件不能省：
                # 原来写成「页为空就无条件收下」，于是**单个超长元素只要落在页首
                # 就会原样成为一整页**，下面 `text_length > page_char_limit` 的
                # 分割分支永远够不着。实测一张 32 万字的表格（整表是一个文本元素）
                # 就这样变成 1 页，后续 QA 生成和段落生成把整页送给 Dify，
                # 双双撞上 `paragraph must be less than 128000 characters` 而失败。
                fits_in_current = current_page_length + text_length <= page_char_limit
                if text_length <= page_char_limit and (not current_page_content or fits_in_current):
                    current_page_content.append(element)
                    current_page_length += text_length
                else:
                    # 当前页满了，保存并开始新页
                    if current_page_content:
                        result[str(current_page)] = current_page_content
                        current_page += 1
                    
                    # 如果单个文本段落超过限制，需要进一步分割
                    if text_length > page_char_limit:
                        # 按句子分割
                        sentences = re.split(r'([。！？\.!\?\n]+)', text)
                        sentences = [''.join(pair) for pair in zip(sentences[::2], sentences[1::2] + ['']) if pair[0].strip()]
                        
                        temp_content = []
                        temp_length = 0
                        
                        for sentence in sentences:
                            sentence_length = _count_text_length(sentence)
                            
                            if temp_length + sentence_length > page_char_limit and temp_content:
                                # 保存当前累积的内容
                                result[str(current_page)] = [{
                                    "type": "text",
                                    "text_content": ''.join(temp_content),
                                    "image_path": None
                                }]
                                current_page += 1
                                temp_content = [sentence]
                                temp_length = sentence_length
                            else:
                                temp_content.append(sentence)
                                temp_length += sentence_length
                        
                        # 剩余内容作为新页的开始
                        if temp_content:
                            current_page_content = [{
                                "type": "text",
                                "text_content": ''.join(temp_content),
                                "image_path": None
                            }]
                            current_page_length = temp_length
                        else:
                            current_page_content = []
                            current_page_length = 0
                    else:
                        # 文本不超过限制，作为新页的开始
                        current_page_content = [element]
                        current_page_length = text_length
        
        # 保存最后一页
        if current_page_content:
            result[str(current_page)] = current_page_content
        
        if not result:
            return json.dumps({"warning": "没有有效内容"})
        
    except Exception as e:
        logging.error(f"处理文本文件时发生错误: {str(e)}")
        traceback.print_exc()
        return json.dumps({"error": str(e)})
    
    return json.dumps(result, ensure_ascii=False, indent=2)


def parse_docx_to_json(docx_path, data_dir):
    #result = {"content": []}
    result = {}
    try:
        doc = Document(docx_path)
    except Exception as e:
        logging.error(f"无法打开文档 {docx_path}: {str(e)}")
        return json.dumps({"error": f"无法打开文档: {str(e)}"})
    index = 0
    for paragraph in doc.paragraphs:
        paragraph_content = []
        text = paragraph.text.strip()
        index += 1
        if text:
            paragraph_content.append({
                "type": "text",
                "text_content": text,
                "image_path": None
            })
        
        # 处理段落中的图片
        try:
            for run in paragraph.runs:
                if run._element is not None:
                    drawing_elements = run._element.findall('.//w:drawing', namespaces=nsdecls('w'))
                    if drawing_elements:
                        for i, drawing in enumerate(drawing_elements):
                            image_filename = f"image_{len(result['content'])}_{i}.png"
                            image_path = os.path.join(data_dir, image_filename)
                            # 这里需要实现图片提取和保存的逻辑
                            # 由于docx中图片提取较复杂，这里仅作示意
                            paragraph_content.append({
                                "type": "image",
                                "text_content": None,
                                "image_path": image_path
                            })
        except Exception as e:
            logging.warning(f"处理段落中的图片时发生错误: {str(e)}")
        
        if paragraph_content:
            #result["content"].extend(paragraph_content)
            result[index] = paragraph_content # 适配pdf的解析
    
    if not result:
        logging.warning(f"文档 {docx_path} 似乎是空的或无法解析")
        return json.dumps({"warning": "文档似乎是空的或无法解析"})
    
    return json.dumps(result, ensure_ascii=False, indent=2)

def get_md5(file_path):
    file_name = os.path.basename(file_path)
    return hashlib.md5(file_name.encode()).hexdigest()

def convert_docx_to_pdf(docx_path, output_dir=None, re_parse=False):
    """
    将DOCX文件转换为PDF
    如果是Linux环境，使用libreoffice命令行工具
    如果是其他环境，使用docx2pdf库
    
    Args:
        docx_path: DOCX文件路径
        output_dir: 输出目录，如果为None则使用输入文件所在目录
        re_parse: 是否重新解析，如果为True则删除已存在的PDF文件
    Returns:
        成功返回PDF文件路径，失败返回原始docx路径
    """
    if output_dir is None:
        output_dir = os.path.dirname(docx_path)
    
    pdf_filename = os.path.splitext(os.path.basename(docx_path))[0] + '.pdf'
    pdf_path = os.path.join(output_dir, pdf_filename)
    
    # 如果目标PDF文件已存在，先删除
    if os.path.exists(pdf_path) and re_parse:
        try:
            os.remove(pdf_path)
            logging.info(f"删除已存在的PDF文件: {pdf_path}")
        except Exception as e:
            logging.warning(f"无法删除已存在的PDF文件 {pdf_path}: {str(e)}")
            
    if os.path.exists(pdf_path):
        logging.info(f"已存在PDF文件: {pdf_path}")
        return pdf_path
    
    # 判断操作系统
    system = platform.system()
    
    try:
        if system == 'Linux':
            # Linux环境使用libreoffice命令行工具
            logging.info(f"检测到Linux环境，使用libreoffice进行转换: {docx_path}")
            cmd = [
                "libreoffice", 
                "--headless",
                "--convert-to", "pdf",
                docx_path,
                "--outdir", output_dir
            ]
            
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
            logging.info(f"libreoffice命令执行成功: {result.stdout}")
            
            # 等待文件生成
            for i in range(30):  # 最多等待30秒
                time.sleep(1)
                if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                    logging.info(f"转换 {docx_path} 到 {pdf_path} 成功")
                    return pdf_path
            
            # 如果等待后仍然没有文件，记录错误
            logging.error(f"libreoffice转换失败: PDF文件 {pdf_path} 未被创建或为空文件")
            logging.info(f"尝试直接解析DOCX文件: {docx_path}")
            return docx_path
            
        else:
            # Windows或macOS环境使用docx2pdf
            logging.info(f"检测到{system}环境，使用docx2pdf进行转换: {docx_path}")
            convert(docx_path, pdf_path)
            
            # 等待一段时间让转换完成
            for i in range(60):  # 最多等待60秒
                time.sleep(1)
                if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                    logging.info(f"转换 {docx_path} 到 {pdf_path} 成功")
                    return pdf_path
            
            # 如果等待后仍然没有文件，记录错误
            logging.error(f"docx2pdf转换失败: PDF文件 {pdf_path} 未被创建或为空文件")
            logging.info(f"尝试直接解析DOCX文件: {docx_path}")
            return docx_path
        
    except subprocess.TimeoutExpired:
        logging.error(f"libreoffice转换超时: {docx_path}")
        logging.info(f"转换超时，尝试直接解析DOCX文件: {docx_path}")
        return docx_path
    except subprocess.CalledProcessError as e:
        logging.error(f"libreoffice转换失败: {str(e)}, stderr: {e.stderr}")
        logging.info(f"转换失败，尝试直接解析DOCX文件: {docx_path}")
        return docx_path
    except Exception as e:
        logging.error(f"转换 {docx_path} 到 PDF 时发生错误: {str(e)}")
        tb = traceback.format_exc()
        logging.error(f"错误堆栈: {tb}")
        logging.info(f"转换失败，尝试直接解析DOCX文件: {docx_path}")
        return docx_path

def trans_files_to_json_and_save(batch_files, data_dir, platform=None):
    if isinstance(batch_files, str):
        batch_files = open(batch_files, 'r').readlines()
    for file_path in batch_files:
        file_path = file_path.strip()
        if not os.path.exists(file_path):
            logging.warning(f"文件不存在: {file_path}")
            continue        
        try:
            md5id = get_md5(file_path)
            one_data_dir = os.path.join(data_dir, md5id)
            os.makedirs(one_data_dir, exist_ok=True)
            
            file_extension = os.path.splitext(file_path)[1].lower()
            
            if file_extension == '.pdf':
                pdf_path = file_path
                json_output = parse_pdf_to_json(pdf_path, one_data_dir)
            elif file_extension in ['.docx', '.doc']:
                converted_path = convert_docx_to_pdf(file_path)
                if converted_path is None:
                    logging.error(f"无法处理文件 {file_path}，转换为PDF失败")
                    continue
                
                # 检查返回的是PDF还是原始DOCX文件
                if converted_path.endswith('.pdf'):
                    # 成功转换为PDF
                    pdf_path = converted_path
                    json_output = parse_pdf_to_json(pdf_path, one_data_dir)
                else:
                    # 转换失败，使用docx解析
                    logging.info(f"使用DOCX解析器处理文件: {file_path}")
                    json_output = parse_docx_to_json(converted_path, one_data_dir)
                    pdf_path = None  # 标记没有生成PDF
            else:
                logging.warning(f"不支持的文件类型: {file_path}")
                continue
            
            json_data = json.loads(json_output)
            if "error" in json_data or "warning" in json_data:
                logging.warning(f"处理文件 {file_path} 时出现问题: {json_data}")
                continue
            
            sorted_json_data = dict(sorted(json_data.items(), key=lambda item: int(item[0])))
            
            content_json_path = os.path.join(one_data_dir, 'content.json')
            with open(content_json_path, 'w', encoding='utf-8') as json_file:
                json.dump(sorted_json_data, json_file, ensure_ascii=False, indent=4)
            if not platform:
                result_line = f"{file_path}\t{one_data_dir}\t{content_json_path}"
            else:
                result_line = f"{platform}\t{file_path}\t{one_data_dir}\t{content_json_path}"
            print(result_line)
            logging.info(f"处理完成: {file_path}")
            
            # 如果是转换的PDF，处理完后删除
            if file_extension in ['.docx', '.doc'] and pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)
                logging.info(f"删除临时PDF文件: {pdf_path}")
        except Exception as e:
            tb = traceback.format_exc()
            logging.error('errortb:[%s]', tb)
            logging.error(f"处理文件 {file_path} 时发生错误: {str(e)}")

def batch_dir_trans(wait_process_file):
    """
    """
    with open(wait_process_file, 'r') as f:
        for line in f:
            fields = line.strip().split('\t')
            plat_form = fields[0]
            data_dir = fields[1]
            # 获取所有文件的绝对路径
            all_files = [os.path.join(data_dir, f) for f in os.listdir(data_dir)]
            trans_files_to_json_and_save(all_files, data_dir, plat_form)


def batch_map_files_trans(wait_process_file, output_file, file_path_field=3):
    """
    该函数用于批量处理wait_process_file中指定的文件，将文件转化为json（如果是docx，则先转换为pdf，再解析为json），直接在最后两列增加转化后的pdf和json文件路径（本身是pdf则是原路径）
    """
    with open(wait_process_file, 'r') as f, open(output_file, 'w') as f_out:
        for line in f:
            line = line.strip('\n')
            fields = line.split('\t')

            file_path = fields[file_path_field].strip()
            if not os.path.exists(file_path):
                logging.warning(f"文件不存在: {file_path}")
                continue        
            try:
                md5id = get_md5(file_path)
                data_dir = os.path.dirname(file_path)
                one_data_dir = os.path.join(data_dir, md5id)
                os.makedirs(one_data_dir, exist_ok=True)
                file_extension = os.path.splitext(file_path)[-1].lower()                
                if file_extension == '.pdf':
                    pdf_path = file_path
                    json_output = parse_pdf_to_json(pdf_path, one_data_dir)
                    logging.info(f"处理文件: {file_path}, 文件类型: {file_extension}, 文件路径: {pdf_path}")
                elif file_extension in ['.docx', '.doc']:
                    converted_path = convert_docx_to_pdf(file_path, re_parse=True)
                    if converted_path is None:
                        logging.error(f"无法处理文件 {file_path}，转换为PDF失败")
                        continue
                    
                    # 检查返回的是PDF还是原始DOCX文件
                    if converted_path.endswith('.pdf'):
                        # 成功转换为PDF
                        pdf_path = converted_path
                        json_output = parse_pdf_to_json(pdf_path, one_data_dir)
                        logging.info(f"处理文件: {file_path}, 文件类型: {file_extension}, PDF路径: {pdf_path}")
                    else:
                        # 转换失败，使用docx解析
                        logging.info(f"使用DOCX解析器处理文件: {file_path}")
                        json_output = parse_docx_to_json(converted_path, one_data_dir)
                        pdf_path = None  # 标记没有生成PDF
                        logging.info(f"处理文件: {file_path}, 文件类型: {file_extension}, 直接解析DOCX")
                elif file_extension in ['.txt', '.md']:
                    json_output = parse_txt_to_json(file_path, one_data_dir, page_char_limit=2000)
                    pdf_path = None  # 标记没有生成PDF
                    logging.info(f"处理文件: {file_path}, 文件类型: {file_extension}, 直接解析TXT")
                elif file_extension in ['.xlsx', '.xls']:
                    json_output = parse_excel_to_json(file_path, one_data_dir)
                    pdf_path = None
                    logging.info(f"处理文件: {file_path}, 文件类型: {file_extension}, 直接解析Excel")
                else:
                    logging.warning(f"不支持的文件类型: {file_path}")
                    continue
                logging.info(f"处理文件: {file_path}, 文件类型: {file_extension}, 文件路径: {pdf_path}")
                #json_output = parse_pdf_to_json(pdf_path, one_data_dir)
                
                json_data = json.loads(json_output)
                if "error" in json_data or "warning" in json_data:
                    logging.warning(f"处理文件 {file_path} 时出现问题: {json_data}")
                    continue
                
                sorted_json_data = dict(sorted(json_data.items(), key=lambda item: int(item[0])))
                
                content_json_path = os.path.join(one_data_dir, 'content.json')
                with open(content_json_path, 'w', encoding='utf-8') as json_file:
                    json.dump(sorted_json_data, json_file, ensure_ascii=False, indent=4)
                result_line = f"{line}\t{one_data_dir}\t{content_json_path}"
                f_out.write(result_line + '\n')
                logging.info(f"处理完成: {file_path}")
                
                # 如果是转换的PDF，处理完后删除
                if file_extension in ['.docx', '.doc'] and pdf_path and os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    logging.info(f"删除临时PDF文件: {pdf_path}")
            except Exception as e:
                tb = traceback.format_exc()
                logging.error('errortb:[%s]', tb)
                logging.error(f"处理文件 {file_path} 时发生错误: {str(e)}")    


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
