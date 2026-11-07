from kdb.shared.config.private_values import private_value as _private_value
from kdb.mining.generation.processing.tools.schema_trans import trans_page_content_to_text
from kdb.mining.generation.processing.knowledge_clear_by_dify_model_longcontent import (
    KnowledgeCleaner,
    SEGMENT_MAX_CHARS,
    SEGMENT_MAX_PAGES,
    build_page_chunks,
    document_last_page,
    fallback_page_segments,
    merge_segment_content,
    normalize_segments_in_chunk,
    parse_dify_segment,
    split_segment_for_qa,
)
from kdb.shared.clients.dify_tools import DifyWorkFlowRequest
from kdb.shared.text.text_utils import text_segment_by_limit
import logging
import traceback
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from kdb.shared.config.legacy_config import GLOBAL_CONFIG
from kdb.mining.generation.processing.knowledge_html_clear_by_dify import (
    contextualize_html_text,
    load_html_business_context,
)

def fill_uncovered_segments_in_chunk(segments, hard_chunk):
    """
    补齐 Dify 分段遗漏的页码，保证每个硬窗口都有 segment 覆盖。
    """
    chunk_start, chunk_end = hard_chunk['pages']
    normalized_segments = []
    covered_pages = set()

    for segment in segments or []:
        pages = segment.get('pages') if isinstance(segment, dict) else None
        if not pages or len(pages) != 2:
            continue
        try:
            start_page = max(chunk_start, int(pages[0]))
            end_page = min(chunk_end, int(pages[1]))
        except (TypeError, ValueError):
            continue
        if start_page > end_page:
            continue
        normalized_segment = dict(segment)
        normalized_segment['pages'] = [start_page, end_page]
        normalized_segments.append(normalized_segment)
        covered_pages.update(range(start_page, end_page + 1))

    gap_segments = []
    gap_start = None
    for page_num in range(chunk_start, chunk_end + 1):
        if page_num not in covered_pages:
            if gap_start is None:
                gap_start = page_num
            continue
        if gap_start is not None:
            gap_segments.extend(fallback_page_segments({'pages': [gap_start, page_num - 1]}))
            gap_start = None
    if gap_start is not None:
        gap_segments.extend(fallback_page_segments({'pages': [gap_start, chunk_end]}))

    if gap_segments:
        logging.warning(
            'segment 硬窗口存在未覆盖页，已用固定页数补齐: hard_chunk=%s gap_segments=%s',
            hard_chunk, gap_segments,
        )
    normalized_segments.extend(gap_segments)
    normalized_segments.sort(key=lambda item: (item['pages'][0], item['pages'][1], item.get('title', '')))
    return normalized_segments

def get_segment_knowledge_by_dify(pdf_json_file, dify_segment, dify_index, from_file_name, platform=None, use_image_content=0, index_workers=1):
    """
    获取分段知识库
    """
    
    data_json = json.load(open(pdf_json_file, 'r', encoding='utf-8'))
    document_content = merge_segment_content(data_json, {'pages': [1, document_last_page(data_json)]}, need_add_page_num=False, use_image_content=use_image_content, add_image_context=use_image_content)
    segment_list = []     
    if len(document_content) < 2000:
        document_content = merge_segment_content(data_json, {'pages': [1, document_last_page(data_json)]}, need_add_page_num=False, use_image_content=use_image_content, add_image_context=1)
        if not document_content or not document_content.strip():
            logging.warning('整篇文档内容为空，跳过 segment 生成: %s', from_file_name)
            return []
        try:
            answer = dify_index.request_dify(document_content)
        except Exception as exc:
            logging.error('短文档 index 请求失败，跳过: %s, error=%s', from_file_name, exc)
            return []
        logging.info(f"段落内容: {document_content}\t答案: {answer}")
        # 长文档分支早就有判空，短文档分支一直没有：Dify 返回 None 时
        # parse_index_answer 里 answer.replace 直接 AttributeError
        if not answer:
            logging.warning('短文档 index 返回为空，跳过 segment 生成: %s', from_file_name)
            return []
        segment_list.append(parse_index_answer(answer, from_file_name, [1, document_last_page(data_json)], data_json))
    else:
        logging.info(f'段落内容长度大于2000字符，进行段落分割')
        segments = []
        hard_chunks = build_page_chunks(data_json, use_image_content=use_image_content)
        logging.info(
            'segment 硬分段窗口生成完成: chunk_count=%s max_chars=%s max_pages=%s chunks=%s',
            len(hard_chunks), SEGMENT_MAX_CHARS, SEGMENT_MAX_PAGES, hard_chunks,
        )

        for chunk_index, hard_chunk in enumerate(hard_chunks, start=1):
            # 只传当前硬窗口；图片文档需包含 OCR 内容才能按主题分段。
            for_seg_document_content = merge_segment_content(
                data_json, hard_chunk, need_add_page_num=True,
                use_image_content=use_image_content, add_image_context=use_image_content,
            )
            logging.warning(
                'segment 开始硬窗口分段: %s/%s pages=%s chars=%s',
                chunk_index, len(hard_chunks), hard_chunk.get('pages'), len(for_seg_document_content),
            )

            def _segment_one_chunk():
                segment_answer = dify_segment.request_dify(for_seg_document_content)
                return normalize_segments_in_chunk(parse_dify_segment(segment_answer), hard_chunk), segment_answer

            try:
                chunk_segments, segment_answer = _segment_one_chunk()
            except Exception as e:
                logging.warning(f'segment 硬窗口第1次分段失败，重试中: hard_chunk={hard_chunk}, error={e}')
                try:
                    chunk_segments, segment_answer = _segment_one_chunk()
                except Exception as e2:
                    logging.warning(f'segment 硬窗口第2次分段失败，使用固定页数兜底: hard_chunk={hard_chunk}, error={e2}')
                    chunk_segments, segment_answer = [], None

            if not chunk_segments:
                logging.warning('segment Dify 分段无有效结果，使用固定页数兜底: hard_chunk=%s', hard_chunk)
                chunk_segments = fallback_page_segments(hard_chunk)
            else:
                chunk_segments = fill_uncovered_segments_in_chunk(chunk_segments, hard_chunk)

            logging.info(
                'segment 段落切分原始结果:%s\t硬窗口:%s\t切分结果:%s',
                segment_answer, hard_chunk, chunk_segments,
            )
            segments.extend(chunk_segments)

        index_segments = [chunk for segment in segments
                          for chunk in split_segment_for_qa(
                              data_json, segment, use_image_content=use_image_content)]

        def generate_index(index_segment):
            segment_content = merge_segment_content(
                data_json, index_segment, need_add_page_num=False,
                use_image_content=use_image_content, add_image_context=use_image_content,
            )
            logging.warning('segment 开始生成索引: pages=%s chars=%s',
                            index_segment.get('pages'), len(segment_content))
            if not segment_content or not segment_content.strip():
                logging.warning('segment 内容为空，跳过不请求 Dify: pages=%s', index_segment.get('pages'))
                return None
            try:
                answer = dify_index.request_dify(segment_content)
            except Exception as exc:
                logging.error('segment index 请求失败，跳过该段: pages=%s, error=%s',
                              index_segment.get('pages'), exc)
                return None
            if not answer:
                logging.warning('segment index 返回为空，跳过: pages=%s', index_segment.get('pages'))
                return None
            return parse_index_answer(answer, from_file_name, index_segment['pages'], data_json)

        workers = max(1, min(4, int(index_workers)))
        if workers == 1:
            segment_list.extend(result for chunk in index_segments
                                if (result := generate_index(chunk)) is not None)
        else:
            # Requests are independent; map retains source-page output order.
            with ThreadPoolExecutor(max_workers=workers) as executor:
                segment_list.extend(result for result in executor.map(generate_index, index_segments)
                                    if result is not None)
    if platform:
        for segment in segment_list:
            segment['platform'] = platform
    return segment_list


def parse_index_answer(answer, from_file_name, pages, ori_data_json_dict):
    """
    解析index信息
    """

    keywords = []
    phrases = []
    topics = []
    
    answer = answer.replace('：', ':')
    # 按行分割答案文本
    lines = answer.strip().split('\n')
    
    for line in lines:
        if line.startswith('关键词:'):
            # 移除"关键词:"前缀并按逗号分割
            keywords.extend([k.strip() for k in line[4:].split(',')])
        elif line.startswith('短语:'):
            # 移除"短语:"前缀并按逗号分割
            phrases.extend([p.strip() for p in line[3:].split(',')])
        elif line.startswith('主题:'):
            # 移除"主题:"前缀
            one_topics = line[3:].strip().split(',')
            topics.extend(one_topics) 
    logging.info(f'start parse_index_answer{answer}, keywords: {keywords}, phrases: {phrases}, topics: {topics}')    
    def _get_segment_by_index(ori_data_json_dict, pages):
        """根据 index 信息取段落内容。

        页码**不保证连续**：解析时既无文字也无图片的空白页会被 parse_pdf_to_json 丢掉，
        实测有文件是 100 页但最大页号 113、中间缺 13 页。所以边界要按**实际最大页号**算，
        取页时也必须判存在——早先按 len(dict) 当上界且直接下标取值，会抛
        KeyError（wayfair 任务 74256b78 在 2026-03 就是被这个异常带走整批的）。
        """
        tmp_dict = dict()
        page_numbers = []
        for key in ori_data_json_dict:
            try:
                page_numbers.append(int(key))
            except (TypeError, ValueError):
                continue
        if not page_numbers:
            return tmp_dict

        # 前面多取一页防止不正确截断。有缺口时取"最近的已存在前页"，
        # 否则像 100 页缺 13 页那种文件，前一页号经常正好落在缺口上，保护就白设了。
        existing = sorted(set(page_numbers))
        prior = [p for p in existing if p < pages[0]]
        start_page = prior[-1] if prior else max(1, pages[0])
        end_page = min(max(existing), pages[1])
        for page in range(start_page, end_page + 1):
            page = str(page)
            if page in ori_data_json_dict:      # 跳过被丢掉的空白页
                tmp_dict[page] = ori_data_json_dict[page]
        return tmp_dict

    segment_info = dict()
    # 模型输出「[phrases]:」后面空着时，''.split(',') 会得到 ['']，一路带到 indexes 就是
    # 空 text，送 DashScope 直接 400，然后整条 segment 入库失败。必须在这里滤掉。
    segment_info['keywords'] = [x for x in keywords if x and x.strip()]
    segment_info['phrases'] = [x for x in phrases if x and x.strip()]
    segment_info['topics'] = [x for x in topics if x and x.strip()]
    segment_info['content'] = _get_segment_by_index(ori_data_json_dict, pages)
    logging.info(f'get segment by index, pages: {pages}, segment_info: {segment_info["content"]}')
    segment_info['from_file_name'] = from_file_name
    file_name = from_file_name.split('/')[-1].split('.')[0]
    segment_info['index_file_name'] = file_name
    if pages:
        segment_info['pages'] = pages

    return segment_info



def parse_index_answer_html(answer, from_file_name, formatted_text):
    """
    解析index信息
    """

    keywords = []
    phrases = []
    topics = []
    
    answer = answer.replace('：', ':')
    # 按行分割答案文本
    lines = answer.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:  # 跳过空行
            continue
        
        # 兼容新格式：[phrases]:、[topic]:、[keywords]:
        if line.startswith('[phrases]:'):
            # 移除"[phrases]:"前缀并按逗号分割
            content = line[10:].strip()  # len('[phrases]:') = 10
            if content:
                phrases.extend([p.strip() for p in content.split(',')])
        elif line.startswith('[topic]:'):
            # 移除"[topic]:"前缀
            content = line[8:].strip()  # len('[topic]:') = 8
            if content:
                topics.append(content)  # topic通常每行一个，不需要按逗号分割
        elif line.startswith('[keywords]:'):
            # 移除"[keywords]:"前缀并按逗号分割
            content = line[11:].strip()  # len('[keywords]:') = 11
            if content:
                keywords.extend([k.strip() for k in content.split(',')])
        # 兼容旧格式：关键词:、短语:、主题:
        elif line.startswith('关键词:'):
            # 移除"关键词:"前缀并按逗号分割
            content = line[4:].strip()  # len('关键词:') = 4
            if content:
                keywords.extend([k.strip() for k in content.split(',')])
        elif line.startswith('短语:'):
            # 移除"短语:"前缀并按逗号分割
            content = line[3:].strip()  # len('短语:') = 3
            if content:
                phrases.extend([p.strip() for p in content.split(',')])
        elif line.startswith('主题:'):
            # 移除"主题:"前缀
            content = line[3:].strip()  # len('主题:') = 3
            if content:
                one_topics = content.split(',')
                topics.extend([t.strip() for t in one_topics])
    logging.info(f'start parse_index_answer{answer}, keywords: {keywords}, phrases: {phrases}, topics: {topics}')    


    segment_info = dict()
    # 同 parse_index_answer：空白项会变成空 index text，害整条入库失败
    segment_info['keywords'] = [x for x in keywords if x and x.strip()]
    segment_info['phrases'] = [x for x in phrases if x and x.strip()]
    segment_info['topics'] = [x for x in topics if x and x.strip()]
    segment_info['content'] = formatted_text
    logging.info(f'get segment by index, formatted_text: {formatted_text}, segment_info: {segment_info["content"]}')
    segment_info['from_file_name'] = from_file_name
    file_name = from_file_name.split('/')[-1].split('.')[0]
    segment_info['index_file_name'] = file_name

    return segment_info


def gen_segment_dataset_info(segment_info):
    """
    """
    indexes = []
    indexes.append(','.join(segment_info['keywords']))
    indexes.append(','.join(segment_info['phrases']))
    #indexes.extend(segment_info['phrases'])
    indexes.extend(segment_info['topics'])
    global_index = segment_info['index_file_name']
    indexes.append(global_index)

    q = segment_info['content']
    pages = segment_info['pages']
    pages_keys= [int(p) for p in q.keys()]
    start = min(pages_keys)
    end = max(pages_keys)
    q = trans_page_content_to_text(q, add_page_num=1, pages=[start, end])
    a = {}
    a['开始页数'] = pages[0]
    a['文件名'] = segment_info['index_file_name']
    a = json.dumps(a, ensure_ascii=False)
    segment_index_info = {}
    segment_index_info['q'] = q
    segment_index_info['a'] = a
    segment_index_info['indexes'] = indexes
    segment_index_info['document_name'] = segment_info['index_file_name']
    return segment_index_info


            

def load_segment_business_context(business_context_path):
    """读取业务上下文 JSON（business_context_builder 产物）。无效时返回 None（旧行为）。"""
    if not business_context_path or not os.path.exists(business_context_path):
        return None
    try:
        with open(business_context_path, 'r', encoding='utf-8') as f:
            ctx = json.load(f)
        if not ctx or not ctx.get('enabled') or not ctx.get('context_text'):
            return None
        return ctx
    except Exception as e:
        logging.warning(f'读取业务上下文失败，忽略: {e}')
        return None


def get_segment_knowledge_by_local_llm(pdf_json_file, business_context, from_file_name,
                                       platform=None, use_image_content=0,
                                       model_name=None, provider=None, max_chars=12000):
    """用本地统一 LLM 生成自包含 segment，输出与 dify 后端兼容的 segment_info 结构。

    Segment 不整篇灌入：要求 LLM 拆分为多个自包含业务主题段，标题不得为栏目式泛标题。
    后端不可用 / 解析失败时返回 []，由上层降级。
    """
    from kdb.shared.clients.local_llm_adapter import request_knowledge_llm

    data_json = json.load(open(pdf_json_file, 'r', encoding='utf-8'))
    document_content = merge_segment_content(
        data_json, {'pages': [1, document_last_page(data_json)]},
        need_add_page_num=False, use_image_content=use_image_content, add_image_context=use_image_content,
    )
    if len(document_content) > max_chars:
        document_content = document_content[:max_chars] + '\n[后文因长度限制省略，禁止基于省略内容生成 segment]'

    context_text = business_context.get('context_text', '') if business_context else ''
    system_prompt = f"""你是企业知识分段专家。客户业务背景：

{context_text}

任务：把文档正文拆分为若干“自包含业务主题段”，输出 JSON 对象，格式：
{{"segments":[{{"title":"自包含标题","content":"该主题完整内容","keywords":["..."],"topics":["..."]}}]}}。

要求：
- 只输出 JSON，不要 Markdown。
- 不允许整篇灌入；每段只表达一个相对完整的业务主题。
- 标题必须自包含，写清平台/活动/服务/计划名，不能只写“适合对象/推广内容/服务内容/详情/活动概述与目标”等栏目名。
- 不要包含 footer、相关文章推荐、关注公众号、版权隐私、空泛广告。
- 内容事实必须来自当前文档。"""

    content = request_knowledge_llm(
        query=f'文档名：{from_file_name}\n\n正文：\n{document_content}',
        system_message=system_prompt,
        model_name=model_name,
        provider=provider,
        temperature=0.1,
        max_tokens=9000,
    )
    if not content:
        return []
    import re as _re
    text = content.strip()
    text = _re.sub(r'^```(?:json)?', '', text).strip()
    text = _re.sub(r'```$', '', text).strip()
    try:
        obj = json.loads(text)
    except Exception:
        start = text.find('{'); end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                obj = json.loads(text[start:end + 1])
            except Exception:
                logging.warning('本地 LLM segment JSON 解析失败')
                return []
        else:
            return []
    seg_items = obj.get('segments', []) if isinstance(obj, dict) else (obj if isinstance(obj, list) else [])

    index_file_name = from_file_name.split('/')[-1].split('.')[0]
    result = []
    for one in seg_items:
        if not isinstance(one, dict):
            continue
        title = str(one.get('title', '')).strip()
        seg_content = str(one.get('content', '')).strip()
        if not seg_content:
            continue
        text_content = f'{title}\n{seg_content}' if title else seg_content
        keywords = one.get('keywords', []) if isinstance(one.get('keywords'), list) else []
        topics = one.get('topics', []) if isinstance(one.get('topics'), list) else []
        segment_info = {
            'keywords': [str(k) for k in keywords][:10],
            'phrases': [],
            'topics': [str(t) for t in topics][:10],
            'content': {'1': [{'type': 'text', 'text_content': text_content}]},
            'from_file_name': from_file_name,
            'index_file_name': index_file_name,
            'pages': [1, 1],
            'title': title,
        }
        if platform:
            segment_info['platform'] = platform
        result.append(segment_info)
    return result


def run_batch_get_segment_knowledge(pdf_json_batch_file, flag='', from_file_name_field_num=0, platform_field_num=None, is_direct_output=0, use_image_content=0,
                                    business_context_path=None, quality_profile='', llm_backend='dify', llm_model_name=None, llm_provider=None, index_workers=1):
    """
    批量生成 segment 知识。

    :param business_context_path: 可选业务上下文 JSON；仅 local 后端用于增强 prompt。
    :param llm_backend: 'dify'（默认，旧行为不变）/'local_llm'/'auto'。
    :param llm_model_name/llm_provider: 本地后端模型/渠道。
    """
    api_base = GLOBAL_CONFIG['dify_api_base']
    dify_segment_api_key = GLOBAL_CONFIG.get('dify_api_key_segment', _private_value('9efbbdbba322a7cfe24bbc08'))
    dify_index_api_key = GLOBAL_CONFIG.get('dify_api_key_index', _private_value('31295135388edf53ecc79dd8'))
    segment_dify_max_retries = int(GLOBAL_CONFIG.get('segment_dify_max_retries', 1))
    segment_dify_timeout = int(GLOBAL_CONFIG.get('segment_dify_timeout', 180))
    dify_segment = DifyWorkFlowRequest(
        api_base=api_base, api_key=dify_segment_api_key,
        max_retries=segment_dify_max_retries, timeout=segment_dify_timeout,
    )
    dify_index = DifyWorkFlowRequest(
        api_base=api_base, api_key=dify_index_api_key,
        max_retries=segment_dify_max_retries, timeout=segment_dify_timeout,
    )
    business_context = load_segment_business_context(business_context_path)
    use_local = str(llm_backend).lower() in ('local_llm', 'local', 'auto')
    logging.info(
        'segment 生成 llm_backend=%s, business_context_enabled=%s, dify_timeout=%s, dify_max_retries=%s',
        llm_backend, business_context is not None, segment_dify_timeout, segment_dify_max_retries,
    )
    with open(pdf_json_batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            pdf_json_file = fields[-1]
            logging.info(f'开始处理文件: {pdf_json_file}')
            # 使用 flag 参数来生成输出文件名
            from_file_name = fields[from_file_name_field_num]
            if platform_field_num is not None:
                platform = fields[platform_field_num]
            else:
                platform = None
            if flag:
                file_path = pdf_json_file.split("\\.")[0] + f'_indexes_{flag}.txt'
            else:
                file_path = pdf_json_file.split("\\.")[0] + '_indexes.txt'
            segments = None
            if use_local:
                try:
                    segments = get_segment_knowledge_by_local_llm(
                        pdf_json_file, business_context, from_file_name=from_file_name,
                        platform=platform, use_image_content=use_image_content,
                        model_name=llm_model_name, provider=llm_provider,
                    )
                    if not segments and str(llm_backend).lower() == 'auto':
                        logging.warning('本地 segment 后端无输出，auto 回退 dify')
                        segments = None
                except Exception as e:
                    logging.error(f'本地 segment 后端失败: {e}')
                    segments = None if str(llm_backend).lower() == 'auto' else []
            if segments is None:
                try:
                    segments = get_segment_knowledge_by_dify(pdf_json_file, dify_segment, dify_index, from_file_name=from_file_name, platform=platform, use_image_content=use_image_content, index_workers=index_workers)
                except Exception as exc:
                    # 单个文件失败不能带走整批：历史上 2026-03 的 KeyError 就是这样让
                    # 235 个文件一条 segment 都没产出的
                    logging.error('segment 生成失败，跳过该文件: %s, error=%s: %s',
                                  from_file_name, type(exc).__name__, exc)
                    logging.error(traceback.format_exc())
                    continue
            if not is_direct_output:
                with open(file_path, 'w', encoding='utf-8') as f:
                    for segment in segments:                
                        f.write(json.dumps(segment, ensure_ascii=False) + '\n')
                fields.append(file_path)
                print('\t'.join(fields))
            else:
                for segment in segments:
                    print(json.dumps(segment, ensure_ascii=False))
            


def process_html_json_content(html_json_content, process_field_key, dify_segment, dify_index, platform=None,
                              business_context=None, quality_profile=''):
    """
    """
    formatted_text = html_json_content.get(process_field_key, '')
    if not formatted_text:
        logging.error(f'缺少必要字段: {process_field_key}, html_json_content: {html_json_content}')
        return None
    from_file_name = html_json_content['crawl_url']
    segments, overlap_segments = text_segment_by_limit(formatted_text, len_limit=4000, overlap_num=1, sep=['\n'])
    result_segments = []
    for indexsegment in overlap_segments:
        request_text = contextualize_html_text(indexsegment, business_context, quality_profile)
        search_indexes = dify_index.request_dify(request_text)
        parse_result = parse_index_answer_html(search_indexes, from_file_name, indexsegment)
        if platform:
            parse_result['platform'] = platform
        result_segments.append(parse_result)
    return result_segments

def run_batch_get_segment_knowledge_html_json(html_json_batch_file, flag='', platform_field_num=None, filed_num=-1,
                                              process_field_key='formatted_text', is_direct_output=0,
                                              use_image_content=0, business_context_path=None,
                                              quality_profile='', llm_backend='dify',
                                              llm_model_name=None, llm_provider=None):
    """
    """
    api_base = GLOBAL_CONFIG['dify_api_base']
    dify_segment_api_key = GLOBAL_CONFIG.get('dify_api_key_segment', _private_value('55598498bb0d13c918c90af6'))
    
    dify_index_api_key = GLOBAL_CONFIG.get('dify_api_key_index', _private_value('625f43d1e1ada78e9938422c'))    
    dify_segment = KnowledgeCleaner(api_base=api_base, api_key=dify_segment_api_key, max_retries=3)
    dify_index = KnowledgeCleaner(api_base=api_base, api_key=dify_index_api_key, max_retries=3)    
    business_context = load_html_business_context(business_context_path)
    if str(llm_backend).lower() not in ('', 'dify'):
        logging.warning(f'HTML segment 暂不切换 llm_backend={llm_backend}，继续使用 Dify 并附加业务上下文')
    logging.info(f'HTML segment 业务上下文启用: {business_context is not None}')
    with open(html_json_batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                line = line.strip()
                fields = line.split('\t')
                if platform_field_num is not None:
                    platform = fields[platform_field_num]
                else:
                    platform = fields[0]
                html_json_file = fields[filed_num]
                html_json_content = json.load(open(html_json_file, 'r', encoding='utf-8'))
                segments = process_html_json_content(
                    html_json_content, process_field_key, dify_segment, dify_index,
                    platform=platform, business_context=business_context,
                    quality_profile=quality_profile,
                )
                if not segments:
                    logging.error(f'处理文件: {html_json_file} 失败')
                    continue
                for segment in segments:
                    if html_json_content.get('category_id'):
                        segment['category_id'] = html_json_content['category_id']
                    if html_json_content.get('category_name'):
                        segment['category_name'] = html_json_content['category_name']
                    if html_json_content.get('original_url'):
                        segment['original_url'] = html_json_content['original_url']
                    print(json.dumps(segment, ensure_ascii=False))
            except Exception as e:
                logging.error(f'处理文件: {html_json_file} 失败: {str(e)}')
                continue

                

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')      
    import fire
    fire.Fire({
        'run_batch_get_segment_knowledge': run_batch_get_segment_knowledge,
        'run_batch_get_segment_knowledge_html_json': run_batch_get_segment_knowledge_html_json,
    })
