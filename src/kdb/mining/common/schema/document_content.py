from kdb.mining.common.schema.image_placeholders import _placeholder_for
import logging

IMAGE_PLACEHOLDER_GUIDE = (
    '【本文中的 [图1] [图2] … 是文档里的插图。'
    '紧跟其后的「里的文字」「内容说明」就是这张图的内容，请据此作答。'
    '如果某张图能直观说明答案（截图、流程图、对比表），'
    '请在答案末尾单独一行写上对应的 [图N] 标记，系统会自动还原成图片；'
    '不要写图片网址。答案必须先给出完整的文字说明，不能只给 [图N] 标记。】\n'
)


def merge_segment_content(data_json, segment, need_add_page_num=False, use_image_content=0,
                          add_image_context=0, image_placeholder_map=None):
    """
    合并指定页面范围内的文本内容。

    :param data_json: 包含所有页面内容的JSON数据
    :param segment: 包含页面范围的字典
    :param need_add_page_num: 是否需要添加页码信息
    :param add_image_context: 1 时把 OCR/图片理解直接铺在图片位置
    :param image_placeholder_map: 传入一个 dict 即启用**占位符模式**：
        图片位置输出 `[图N]` + 该图的 OCR/图片理解，真实 URL 只留在这个 map 里，
        生成完再用 `restore_image_placeholders` 还原。
        既让模型看得到图里的内容，又不用它抄 URL。
    :return: 合并后的文本内容
    """
    start_page, end_page = segment['pages']
    segment_content = ''
    logging.info(f'start merge segment content, start_page: {start_page}, end_page: {end_page} use_image_content: {use_image_content}, add_image_context: {add_image_context}')
    for page_num in range(start_page, end_page + 1):
        page_values = data_json.get(str(page_num), [])
        one_page_content = ''
        for one_value in page_values:
            if one_value.get('type') == 'text':
                one_segment_content = one_value.get('text_content', '')
                one_page_content = one_page_content + '\n' + one_segment_content if one_page_content else one_segment_content
            elif use_image_content and one_value.get('type') == 'image':
                if not one_value.get("is_valid", False):
                    continue
                public_url = one_value.get('public_url', '')
                ocr = one_value.get('image_ocr', '')
                image_understanding = one_value.get('image_understanding', '')
                #name = one_value.get('name', '')

                if image_placeholder_map is not None:
                    if not public_url:
                        continue
                    tag = _placeholder_for(public_url, image_placeholder_map)
                    parts = [tag]
                    if ocr:
                        parts.append('%s里的文字：%s' % (tag, ocr))
                    if image_understanding:
                        parts.append('%s的内容说明：%s' % (tag, image_understanding))
                    one_segment_content = '\n'.join(parts)
                elif add_image_context:
                    one_segment_content = f'![嵌入图片]({public_url} "Flowchart")'
                    if ocr:
                        one_segment_content = f'{one_segment_content}\n{public_url}的ocr理解为:\n<image_ocr>{ocr}</image_ocr>'
                    if image_understanding:
                        one_segment_content = f'{one_segment_content}\n{public_url}的图片理解为:\n<image_understanding>{image_understanding}</image_understanding>'

                else:
                    one_segment_content = f'{public_url}'

                one_page_content = one_page_content + '\n' + one_segment_content if one_page_content else one_segment_content

        if one_page_content:
            if need_add_page_num:
                one_page_content = f'第{page_num}页内容如下:\n{one_page_content}'
            segment_content = segment_content + '\n' + one_page_content if segment_content else one_page_content

    # 占位符模式下把用法说明放在正文最前面，模型才知道 [图N] 是什么、该怎么用。
    # 放在这里而不是调用方，是因为每次调用都是一次独立的 prompt，都得带上这个约定。
    if image_placeholder_map is not None and segment_content:
        segment_content = IMAGE_PLACEHOLDER_GUIDE + segment_content

    return segment_content


def trans_page_content_to_text(page_content_json, add_page_num=1, pages=None):
    """
    """
    pages = pages if pages else [1, len(page_content_json)]
    trans_text = merge_segment_content(page_content_json, {'pages': pages}, add_page_num, use_image_content=1, add_image_context=0)    # add_image_context为0 ，因为已经增加multimodal_contents字段, image_context在检索的时候实时拼接
    return trans_text
