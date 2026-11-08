

def merge_segment_content(data_json, segment, need_add_page_num=False):
    """
    合并指定页面范围内的文本内容。
    
    :param data_json: 包含所有页面内容的JSON数据
    :param segment: 包含页面范围的字典
    :param need_add_page_num: 是否需要添加页码信息
    :return: 合并后的文本内容
    """
    start_page, end_page = segment['pages']
    start_page = int(start_page)
    end_page = int(end_page)
    segment_content = ''

    for page_num in range(start_page, end_page + 1):
        page_values = data_json.get(str(page_num), [])
        one_page_content = ''
        for one_value in page_values:
            if one_value.get('type') == 'text':
                one_segment_content = one_value.get('text_content', '')
                one_page_content = one_page_content + '\n' + one_segment_content if one_page_content else one_segment_content

        if one_page_content:
            if need_add_page_num:
                one_page_content = f'第{page_num}页内容如下:\n{one_page_content}'
            segment_content = segment_content + '\n' + one_page_content if segment_content else one_page_content

    return segment_content


def trans_page_content_to_text(page_content_json, add_page_num=1, pages=None):
    """
    """
    pages = pages if pages else [1, len(page_content_json)]
    trans_text = merge_segment_content(page_content_json, {'pages': pages}, add_page_num)
    return trans_text
