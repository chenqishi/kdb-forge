from kdb.shared.config.private_values import private_value as _private_value
import logging
import json
import sys
import traceback
from kdb.shared.clients.dify_tools import DifyWorkFlowRequest
from kdb.shared.text.text_utils import text_segment_by_limit
from kdb.mining.generation.processing.knowledge_clear_by_dify_model_longcontent import (
    parse_answer, 
    add_quality_info_to_qa_json,
    parse_dify_segment
)
from kdb.shared.config.legacy_config import GLOBAL_CONFIG

def load_html_business_context(business_context_path):
    """读取业务上下文 JSON。未启用或读取失败时返回 None，保持旧流程行为。"""
    if not business_context_path:
        return None
    try:
        with open(business_context_path, 'r', encoding='utf-8') as f:
            ctx = json.load(f)
        if not ctx or not ctx.get('enabled') or not ctx.get('context_text'):
            return None
        return ctx
    except Exception as e:
        logging.warning(f'读取 HTML 业务上下文失败，忽略: {e}')
        return None


def _trim_context_text(text, max_chars=4000):
    """限制上下文长度，避免挤占网页正文窗口。"""
    if not text:
        return ''
    text = str(text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + '\n[业务上下文因长度限制截断]'


def build_html_context_prefix(business_context, quality_profile=''):
    """构造给 Dify 的抽取约束前缀；该文本只作约束，不作为网页事实。"""
    if not business_context:
        return ''
    context_text = _trim_context_text(business_context.get('context_text', ''))
    boundaries = business_context.get('business_boundaries') or {}
    keep = '、'.join(boundaries.get('keep') or [])
    reject = '、'.join(boundaries.get('reject') or [])
    profile = quality_profile or 'business_task_knowledge'
    return (
        "【抽取约束，禁止作为知识内容输出】\n"
        f"{context_text}\n"
        f"质量画像：{profile}\n"
        f"优先保留：{keep}\n"
        f"优先拒绝：{reject}\n"
        "只基于下面网页正文生成知识；不要把本段约束或用户 query 样例当作答案事实。\n"
        "【网页正文】\n"
    )


def contextualize_html_text(formatted_text, business_context=None, quality_profile=''):
    """为 HTML 正文附加业务抽取约束；无上下文时原样返回。"""
    prefix = build_html_context_prefix(business_context, quality_profile)
    if not prefix:
        return formatted_text
    return prefix + (formatted_text or '')


def process_content(formatted_text, content_type, crawl_url, dify_segment, dify_subtract, dify_qa_subtract, client=None,
                    business_context=None, quality_profile=''):
    """
    处理文本内容，根据长度决定是否分段，并提取问答对。
    
    :param formatted_text: 要处理的文本内容
    :param content_type: 内容类型 ('qa' 或其他)
    :param crawl_url: 爬取的URL
    :param dify_segment: 用于分段的Dify模型实例
    :param dify_subtract: 用于提取QA的Dify模型实例
    :param dify_qa_subtract: 用于处理QA类型内容的Dify模型实例
    :return: 提取的问答对列表
    """
    qa_extract_json_list = []
    if client:
        other_inputs = {}
        other_inputs['client'] = client
    else:
        other_inputs = None
    if len(formatted_text) < 2000:
        # 根据content_type选择不同的处理模型
        dify_model = dify_qa_subtract if content_type == 'qa' else dify_subtract
        
        request_text = contextualize_html_text(formatted_text, business_context, quality_profile)
        answer = dify_model.request_dify(request_text, other_inputs=other_inputs)
        logging.info(f"crawler_url: {crawl_url} 使用模型类型：{content_type} 段落内容: {formatted_text}\t答案: {answer}")
        qa_extract_json_list.extend(parse_answer(answer, crawl_url, [1, 1]))
    else:
        logging.info(f'段落内容长度大于2000字符，进行段落分割')
        #segment_answer = dify_segment.request_dify(formatted_text)
        #segments = parse_dify_segment(segment_answer)
        segments, overlap_segments = text_segment_by_limit(formatted_text, len_limit=8000, overlap_num=0, sep=['\n--------\n'])
        logging.info(f'段落切分结果: {segments}')
        
        for index, segment in enumerate(segments):
            #segment_content = formatted_text[segment['start']:segment['end']] if 'start' in segment else formatted_text
            segment_content = overlap_segments[index]
            
            dify_model = dify_qa_subtract if content_type == 'qa' else dify_subtract
            request_text = contextualize_html_text(segment_content, business_context, quality_profile)
            answer = dify_model.request_dify(request_text, other_inputs=other_inputs)
            parse_result = parse_answer(answer, crawl_url, [index+1, index+1])
            logging.info(f"crawler_url: {crawl_url} 使用模型类型：{content_type} 段落内容: {segment_content}\t答案: {answer}\t解析结果: {parse_result}")
            qa_extract_json_list.extend(parse_result)
    
    return qa_extract_json_list

def run_batch_clear_html_content(input_file, output_file, process_field_num=-1, flag='', process_field='formatted_text',
                                 business_context_path=None, quality_profile='', llm_backend='dify',
                                 llm_model_name=None, llm_provider=None):
    """
    批量处理HTML内容，提取问答对并添加质量信息。
    """
    api_base = GLOBAL_CONFIG['dify_api_base']
    dify_segment = DifyWorkFlowRequest(api_base=api_base, api_key=_private_value('94db6555a441d5ddafe97983'), max_retries=3)
    #dify_subtract = DifyWorkFlowRequest(api_base=api_base, api_key='[PRIVATE_CREDENTIAL_REDACTED]', max_retries=3)
    dify_subtract = DifyWorkFlowRequest(api_base=api_base, api_key=_private_value('98192547ce5c4eb1ce4e9be4'), max_retries=3)
    dify_qa_subtract = DifyWorkFlowRequest(api_base=api_base, api_key=_private_value('3f5c95c6b6c0979ff3780e7d'), max_retries=3)
    dify_qa_filter = DifyWorkFlowRequest(api_base=api_base, api_key=_private_value('e4a1b0eecf36c50ab65cd2ec'), max_retries=3)
    business_context = load_html_business_context(business_context_path)
    if str(llm_backend).lower() not in ('', 'dify'):
        logging.warning(f'HTML QA 暂不切换 llm_backend={llm_backend}，继续使用 Dify 并附加业务上下文')
    logging.info(f'HTML QA 业务上下文启用: {business_context is not None}')

    # 生成输出文件路径
    index = 0
    with open(input_file, 'r', encoding='utf-8') as f, open(output_file, 'w', encoding='utf-8') as out_f:
        for line in f:
            try:
                line = line.strip()
                fields = line.split('\t')
                json_data_file = fields[process_field_num]
                data_json = json.load(open(json_data_file, 'r', encoding='utf-8'))
                client = data_json.get('client', None)
                formatted_text = data_json.get(process_field, '')
                content_type = data_json.get('content_type', '')
                crawl_url = data_json.get('crawl_url', '')
                if not client:
                    client = data_json.get('platform', '')
                if not formatted_text or not content_type:
                    logging.warning(f'缺少必要字段: formatted_text或content_type, 跳过处理')
                    continue

                # 保存原始内容
                index += 1
                logging.info(f'处理第{index}条数据')


                # 处理内容并提取问答对
                qa_extract_json_list = process_content(
                    formatted_text, 
                    content_type, 
                    crawl_url,
                    dify_segment,
                    dify_subtract,
                    dify_qa_subtract,
                    client,
                    business_context=business_context,
                    quality_profile=quality_profile,
                )


                # 添加质量信息
                quality_result = add_quality_info_to_qa_json(qa_extract_json_list, dify_qa_filter)
                for quality_level, qa_list in quality_result.items():
                    for qa_item in qa_list:
                        if data_json.get('category_id'):
                            qa_item['category_id'] = data_json['category_id']
                        if data_json.get('category_name'):
                            qa_item['category_name'] = data_json['category_name']
                        if data_json.get('original_url'):
                            qa_item['original_url'] = data_json['original_url']
                # 保存带质量信息的问答对
                add_quality_file = json_data_file.split('\\.')[0] + '_qa_quality.json'
                with open(add_quality_file, 'w', encoding='utf-8') as out_json_f:
                    json.dump(quality_result, out_json_f, ensure_ascii=False, indent=4)
                fields.append(add_quality_file)
                # 输出处理结果 platform, crawl_url, content_type, crawler_degree, html_local_file, data_json_file, add_quality_file
                out_f.write('\t'.join(fields) + '\n')
                
                # 输出处理结果            

            except json.JSONDecodeError:
                logging.error(f"JSON解析错误: {line}")
            except Exception as e:
                tb = traceback.format_exc()
                logging.error(f"处理出错: {str(e)}\n{tb}")
                
                continue

if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    import fire
    fire.Fire({
        'run_batch_clear_html_content': run_batch_clear_html_content,
    })
