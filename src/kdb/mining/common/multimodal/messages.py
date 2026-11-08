

def construct_multimodel_undestanding_content(content, url_process_result):
    """
    构造多媒体理解内容
    
    Args:
        content: 文本内容
        url_process_result: 链接处理结果，字典格式，key 为content中的 URL，value 为 process_one_data 返回的结果
            结果格式包含：
            - public_url: 内部链接（处理后的 URL）
            - image_understanding: 图片理解内容
            - image_ocr: OCR 内容
            - is_valid: 是否有效
    
    Returns:
        str: 处理后的内容，原始 URL 替换为 markdown 格式，并追加 OCR 和图片理解内容
    """
    if not content or not isinstance(content, str):
        return content or ""

    if not url_process_result or not isinstance(url_process_result, dict):
        return content

    result_content = content

    # 按照 URL 长度降序排序，避免短 URL 替换长 URL 的一部分
    sorted_urls = sorted(url_process_result.items(), key=lambda x: len(x[0]), reverse=True)

    for original_url, process_result in sorted_urls:
        if not isinstance(process_result, dict):
            continue

        # 获取处理结果
        public_url = process_result.get("public_url")
        image_ocr = process_result.get("image_ocr")
        image_understanding = process_result.get("image_understanding")
        is_valid = process_result.get("is_valid", False)

        # 如果无效或没有 public_url，跳过
        if not is_valid or not public_url:
            continue

        # 在 content 中查找原始 URL
        if original_url not in result_content:
            continue

        # 构建 markdown 格式的图片链接
        markdown_image = f'![嵌入图片]({public_url} "Flowchart")'

        # 构建追加内容
        append_content_parts = []

        # 添加 OCR 内容
        if image_ocr:
            append_content_parts.append(f'{public_url}的ocr理解为:\n<image_ocr>{image_ocr}</image_ocr>')

        # 添加图片理解内容
        if image_understanding:
            append_content_parts.append(f'{public_url}的图片理解为:\n<image_understanding>{image_understanding}</image_understanding>')

        # 将原始 URL 替换为 markdown 格式 + 追加内容
        if append_content_parts:
            replacement = f'{markdown_image}\n' + '\n'.join(append_content_parts)
        else:
            replacement = markdown_image

        # 替换所有出现的原始 URL
        result_content = result_content.replace(original_url, replacement)

    return result_content
