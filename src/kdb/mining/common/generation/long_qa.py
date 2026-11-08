from kdb.mining.common.deduplication.qa import deduplicate_qa_list
from kdb.mining.common.schema.qa_model_output import find_duplicate_index
from kdb.mining.common.schema.document_content import merge_segment_content
from kdb.mining.common.schema.image_placeholders import restore_image_placeholders
from kdb.mining.common.schema.image_placeholders import strip_hallucinated_image_urls
from kdb.mining.common.schema.image_placeholders import strip_image_placeholders
from kdb.shared.config.global_config import GLOBAL_CONFIG
from kdb.shared.config.private_values import private_value as _private_value
import copy
import json
import kdb.mining.common.schema.review_formats as schema_trans
import kdb.shared.text.common_utils as common_utils
import logging
import os
import re
import requests
import sys
import time
import traceback

SEGMENT_MAX_CHARS = 80000


SEGMENT_MAX_PAGES = 40


QA_MAX_CHARS = 30000


QA_MAX_PAGES = 10


QA_QUALITY_BATCH_SIZE = 40


def document_last_page(data_json):
    """Page keys retain original PDF numbers even when empty pages are omitted."""
    return max((int(page) for page in data_json if str(page).isdigit()), default=0)


class KnowledgeCleaner:
    def __init__(self, api_base=None, api_key=None, max_retries=3):
        self.api_base = api_base
        self.api_key = api_key
        self.max_retries = max_retries

    def request_dify(self, paragraph):
        headers = {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json'
        }
        
        payload = {
            'inputs': {
                'paragraph': paragraph
            },
            "response_mode": "blocking",
            "user": "test"
        }
        
        for attempt in range(self.max_retries):
            try:
                logging.info(f"正在调用Dify API，请求内容: {payload}")
                response = requests.post(f"{self.api_base}/workflows/run", headers=headers, json=payload, timeout=600)
                
                if response.status_code != 200:
                    logging.error(f"API返回非200状态码: {response.status_code}")
                    logging.error(f"响应内容: {response.text}")
                    continue
                
                result = response.json()
                if result['data']['status'] == 'failed':
                    logging.error(f"Dify请求失败: {result['data']['error']} api_key: {self.api_key}")
                    if attempt < self.max_retries - 1:
                        logging.info(f"正在进行第{attempt + 2}次重试...")
                        time.sleep(5)  # 在重试之前等待5秒
                        continue
                    else:
                        return None
                
                return result['data']['outputs']['Final']
            except KeyError as e:
                logging.error(f"响应中缺少字段: {str(e)}")
                logging.error(f"完整响应内容: {response.text}")
            except requests.exceptions.Timeout:
                logging.error("请求超时（10分钟）")
            except requests.exceptions.RequestException as e:
                logging.error(f"请求异常: {str(e)}")
                logging.error(f"请求URL: {self.api_base}/workflows/run")
                logging.error(f"请求头: {headers}")
                logging.error(f"请求体: {payload}")
            except Exception as e:
                tb = traceback.format_exc()
                logging.error('tb[%s]', tb)
                logging.error(f"调用Dify API时发生错误: {str(e)}")
            
            if attempt < self.max_retries - 1:
                logging.info(f"正在进行第{attempt + 2}次重试...")
                time.sleep(5)  # 在重试之前等待5秒
            else:
                logging.error("已达到最大重试次数,请求失败")
        
        return None


def load_business_context(business_context_path):
    """读取业务上下文 JSON 文件（business_context_builder 产物）。

    缺省 / 读取失败 / enabled=False 时返回 None，表示不增强 prompt（兼容旧行为）。
    """
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


def _build_local_qa_system_prompt(business_context, quality_profile=''):
    """构建本地 LLM QA 抽取的系统 prompt（含业务背景与自包含/反 boilerplate 规则）。"""
    context_text = business_context.get('context_text', '') if business_context else ''
    boundaries = business_context.get('business_boundaries', {}) if business_context else {}
    keep = '、'.join(boundaries.get('keep', []) or [])
    reject = '、'.join(boundaries.get('reject', []) or [])
    return f"""你是企业知识抽取专家。下面是客户业务背景与用户高频问题方向：

{context_text}

任务：从给定文档正文中抽取面向外部用户的业务/任务知识，输出 JSON 对象。

保留（优先）：{keep or '操作步骤、条件、费用、时间地点报名方式、平台规则、适用对象'}
拒绝：{reject or '品牌宣传、版权隐私、关注公众号、点赞、阅读原文、免责声明、无事实广告'}

输出要求：
- 只输出 JSON，不要 Markdown。格式：{{"qa":[{{"q":"","a":"","indexes":[],"category":"","evidence":""}}]}}。
- 答案事实必须来自当前文档；网络/背景信息只用于判断什么值得抽，不能编造文档没有的事实。
- 每个问题必须单独可理解，不能依赖文档标题或上一条 QA 的上下文。
- 问题和标题中不要单独使用“第一期/第二期/本次/此次/该活动/该合作/该服务/该平台”等悬空指代，必须写清活动名、计划名、平台名或服务名。
- 标题不能只写“适合对象/推广内容/活动概述与目标/服务内容/详情/核心优势”等栏目名，必须写成自包含标题。
- 活动/课程/直播类知识：原文给出时间则答案必须含明确时间；线下活动原文给出地点则必须含地点。
- 如果没有高质量业务知识，返回 {{"qa":[]}}。
"""


def _parse_local_qa_json(content):
    """从本地 LLM 输出解析 qa 列表，容错 Markdown 包裹与多余文本。"""
    if not content:
        return []
    text = content.strip()
    text = re.sub(r'^```(?:json)?', '', text).strip()
    text = re.sub(r'```$', '', text).strip()
    obj = None
    try:
        obj = json.loads(text)
    except Exception:
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                obj = json.loads(text[start:end + 1])
            except Exception:
                logging.warning('本地 LLM QA JSON 解析失败')
                return []
        else:
            return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return obj.get('qa', []) or []
    return []


def clear_pdf_json_content_local(pdf_json_file, output_file, business_context, from_file_name,
                                 use_image_content=0, model_name=None, provider=None,
                                 quality_profile='', max_chars=12000, image_placeholder_map=None):
    """使用本地统一 LLM（agents.commons.llm_client）生成 QA。

    与 Dify 后端输出结构保持一致：返回 [{q,a,from_file_name,from_page}, ...]。
    后端不可用或返回空时返回 []，由上层降级处理。
    """
    from kdb.shared.clients.local_llm_adapter import request_knowledge_llm

    data_json = json.load(open(pdf_json_file, 'r', encoding='utf-8'))
    document_content = merge_segment_content(
        data_json, {'pages': [1, document_last_page(data_json)]},
        need_add_page_num=False, use_image_content=use_image_content, add_image_context=use_image_content,
        image_placeholder_map=image_placeholder_map,
    )
    if len(document_content) > max_chars:
        document_content = document_content[:max_chars] + '\n[后文因长度限制省略，禁止基于省略内容生成知识]'

    system_prompt = _build_local_qa_system_prompt(business_context, quality_profile)
    content = request_knowledge_llm(
        query=f'文档名：{from_file_name}\n\n正文：\n{document_content}',
        system_message=system_prompt,
        model_name=model_name,
        provider=provider,
        temperature=0.1,
        max_tokens=9000,
    )
    qa_items = _parse_local_qa_json(content)
    json_list = []
    for one in qa_items:
        if not isinstance(one, dict):
            continue
        q = str(one.get('q', '')).strip()
        a = str(one.get('a', '')).strip()
        if not q or not a:
            continue
        item = {
            'q': q,
            'a': a,
            'from_file_name': from_file_name,
            'from_page': [1, document_last_page(data_json)],
        }
        if one.get('category'):
            item['category'] = one.get('category')
        if one.get('evidence'):
            item['evidence'] = one.get('evidence')
        json_list.append(item)

    with open(output_file, 'w', encoding='utf-8') as out_f:
        json.dump(json_list, out_f, ensure_ascii=False, indent=4)
    return json_list


def mark_local_qa_quality(qa_json_list):
    """为本地后端生成的 QA 标注质量结构，对齐 Dify 后端 add_quality_file 输出。"""
    dedup = deduplicate_qa_list(qa_json_list)
    high = []
    for i, qa_item in enumerate(dedup, start=1):
        qa_item['quality_info'] = ['优质']
        qa_item['quality_level'] = 'high'
        qa_item['duplicate_index'] = i
        qa_item['group'] = i
        qa_item['group_qa_count'] = 1
        high.append(qa_item)
    return {'high': high, 'mid': [], 'low': []}


def save_all_document_content(pdf_json_file, output_file, use_image_content=0):
    """
    保存整个文档的内容到输出文件。
    
    :param pdf_json_file: 包含PDF内容的JSON文件路径
    :param output_file: 保存整个文档内容的输出文件路径
    """
    data_json = json.load(open(pdf_json_file, 'r', encoding='utf-8'))
    document_content = merge_segment_content(data_json, {'pages': [1, document_last_page(data_json)]}, need_add_page_num=True, use_image_content=use_image_content)
    
    with open(output_file, 'w', encoding='utf-8') as out_f:
        out_f.write(document_content)


def build_page_chunks(data_json, max_chars=SEGMENT_MAX_CHARS, max_pages=SEGMENT_MAX_PAGES, use_image_content=0):
    """
    按页边界把文档切成给 Dify 分段模型的硬窗口。
    """
    chunks = []
    current_start = None
    current_end = None
    current_len = 0
    page_count = document_last_page(data_json)

    for page_num in range(1, page_count + 1):
        page_segment = {'pages': [page_num, page_num]}
        page_content = merge_segment_content(
            data_json, page_segment, need_add_page_num=True,
            use_image_content=use_image_content, add_image_context=use_image_content,
        )
        page_len = len(page_content)

        if current_start is None:
            current_start = current_end = page_num
            current_len = page_len
            if page_len > max_chars:
                logging.warning(
                    '单页内容超过分段字符上限，保留为单页窗口: page=%s len=%s max_chars=%s',
                    page_num, page_len, max_chars,
                )
                chunks.append({'pages': [page_num, page_num]})
                current_start = current_end = None
                current_len = 0
            continue

        next_page_count = page_num - current_start + 1
        next_len = current_len + (1 if current_len and page_len else 0) + page_len
        if next_page_count > max_pages or (page_len and next_len > max_chars):
            chunks.append({'pages': [current_start, current_end]})
            current_start = current_end = page_num
            current_len = page_len
            if page_len > max_chars:
                logging.warning(
                    '单页内容超过分段字符上限，保留为单页窗口: page=%s len=%s max_chars=%s',
                    page_num, page_len, max_chars,
                )
                chunks.append({'pages': [page_num, page_num]})
                current_start = current_end = None
                current_len = 0
        else:
            current_end = page_num
            current_len = next_len

    if current_start is not None:
        chunks.append({'pages': [current_start, current_end]})

    return chunks


def normalize_segments_in_chunk(segments, hard_chunk):
    """
    将 Dify 返回的段落页码限制在当前硬窗口内，过滤无效范围。
    """
    chunk_start, chunk_end = hard_chunk['pages']
    normalized = []
    seen = set()
    for segment in segments or []:
        if not isinstance(segment, dict) or 'pages' not in segment:
            continue
        try:
            start_page, end_page = segment['pages']
            start_page = max(chunk_start, int(start_page))
            end_page = min(chunk_end, int(end_page))
        except (TypeError, ValueError):
            logging.warning('分段页码无法解析，跳过: %s', segment)
            continue
        if start_page > end_page:
            logging.warning('分段页码超出硬窗口，跳过: segment=%s hard_chunk=%s', segment, hard_chunk)
            continue
        key = (start_page, end_page, segment.get('title', ''))
        if key in seen:
            continue
        seen.add(key)
        normalized.append({
            'title': segment.get('title', ''),
            'pages': [start_page, end_page],
        })

    normalized.sort(key=lambda item: (item['pages'][0], item['pages'][1], item.get('title', '')))
    return normalized


def fallback_page_segments(hard_chunk, max_pages=QA_MAX_PAGES):
    """
    Dify 分段失败时，按固定页数生成兜底段落。
    """
    start_page, end_page = hard_chunk['pages']
    segments = []
    for segment_start in range(start_page, end_page + 1, max_pages):
        segment_end = min(end_page, segment_start + max_pages - 1)
        segments.append({
            'title': f'第{segment_start}-{segment_end}页',
            'pages': [segment_start, segment_end],
        })
    return segments


def split_segment_for_qa(data_json, segment, max_chars=QA_MAX_CHARS, max_pages=QA_MAX_PAGES,
                         use_image_content=0, image_placeholder_map=None):
    """
    在 QA 抽取前再次按页边界限制段落长度，避免单个语义段过长。
    """
    pages = segment.get('pages', [])
    if len(pages) != 2:
        return []
    start_page, end_page = pages
    qa_segments = []
    current_start = None
    current_end = None
    current_len = 0

    for page_num in range(int(start_page), int(end_page) + 1):
        page_segment = {'pages': [page_num, page_num]}
        page_content = merge_segment_content(
            data_json, page_segment, need_add_page_num=False,
            use_image_content=use_image_content, add_image_context=use_image_content,
            image_placeholder_map=image_placeholder_map,
        )
        page_len = len(page_content)

        if current_start is None:
            current_start = current_end = page_num
            current_len = page_len
            if page_len > max_chars:
                logging.warning(
                    '单页内容超过 QA 字符上限，保留为单页窗口: page=%s len=%s max_chars=%s',
                    page_num, page_len, max_chars,
                )
                qa_segments.append({'title': segment.get('title', ''), 'pages': [page_num, page_num]})
                current_start = current_end = None
                current_len = 0
            continue

        next_page_count = page_num - current_start + 1
        next_len = current_len + (1 if current_len and page_len else 0) + page_len
        if next_page_count > max_pages or (page_len and next_len > max_chars):
            qa_segments.append({'title': segment.get('title', ''), 'pages': [current_start, current_end]})
            current_start = current_end = page_num
            current_len = page_len
            if page_len > max_chars:
                logging.warning(
                    '单页内容超过 QA 字符上限，保留为单页窗口: page=%s len=%s max_chars=%s',
                    page_num, page_len, max_chars,
                )
                qa_segments.append({'title': segment.get('title', ''), 'pages': [page_num, page_num]})
                current_start = current_end = None
                current_len = 0
        else:
            current_end = page_num
            current_len = next_len

    if current_start is not None:
        qa_segments.append({'title': segment.get('title', ''), 'pages': [current_start, current_end]})

    return qa_segments


def clear_pdf_json_content(pdf_json_file, output_file, dify_segment, dify_subtract, from_file_name,
                           use_image_content=0, image_placeholder_map=None):
    """
    处理PDF JSON文件，提取问答对并保存结果。
    
    :param pdf_json_file: 输入的PDF JSON文件路径
    :param output_file: 输出文件路径
    :param dify_segment: 用于分段的Dify模型实例
    :param dify_subtract: 用于提取QA的Dify模型实例
    :param from_file_name: 源文件名
    :param image_placeholder_map: 传 dict 即启用占位符模式（图片位置给 [图N] + OCR/图片理解），
        生成后由调用方用 schema_trans.restore_image_placeholders 还原成图片。
    :return: 提取的问答对列表
    """
    data_json = json.load(open(pdf_json_file, 'r', encoding='utf-8'))
    document_content = merge_segment_content(data_json, {'pages': [1, document_last_page(data_json)]}, need_add_page_num=False, use_image_content=use_image_content, add_image_context=use_image_content, image_placeholder_map=image_placeholder_map)
    json_list = []

    
    if len(document_content) < 2000:
        # 实际理解的时候当采用图片时要加入图片理解内容
        document_content = merge_segment_content(data_json, {'pages': [1, document_last_page(data_json)]}, need_add_page_num=False, use_image_content=use_image_content, add_image_context=use_image_content, image_placeholder_map=image_placeholder_map)
        answer = dify_subtract.request_dify(document_content)
        logging.info(f"段落内容: {document_content}\t答案: {answer}")
        json_list.extend(parse_answer(answer, from_file_name, [1, document_last_page(data_json)]))
    else:
        logging.info(f'段落内容长度大于2000字符，进行段落分割')
        segments = []
        hard_chunks = build_page_chunks(data_json, use_image_content=use_image_content)
        logging.info(
            '硬分段窗口生成完成: chunk_count=%s max_chars=%s max_pages=%s chunks=%s',
            len(hard_chunks), SEGMENT_MAX_CHARS, SEGMENT_MAX_PAGES, hard_chunks,
        )
        for hard_chunk in hard_chunks:
            for_seg_document_content = merge_segment_content(
                data_json, hard_chunk, need_add_page_num=True,
                use_image_content=use_image_content, add_image_context=use_image_content,
            )  # 图片文档使用 OCR 内容分段
            segment_answer = dify_segment.request_dify(for_seg_document_content)
            chunk_segments = normalize_segments_in_chunk(parse_dify_segment(segment_answer), hard_chunk)
            if not chunk_segments:
                logging.warning('Dify 分段无有效结果，使用固定页数兜底: hard_chunk=%s', hard_chunk)
                chunk_segments = fallback_page_segments(hard_chunk)
            logging.info(
                '段落切分原始结果:%s\t硬窗口:%s\t切分结果:%s',
                segment_answer, hard_chunk, chunk_segments,
            )
            segments.extend(chunk_segments)

        for segment in segments:
            qa_segments = split_segment_for_qa(data_json, segment, use_image_content=use_image_content,
                                               image_placeholder_map=image_placeholder_map)
            for qa_segment in qa_segments:
                segment_content = merge_segment_content(data_json, qa_segment, need_add_page_num=False, use_image_content=use_image_content, add_image_context=use_image_content)# image_context改为在检索时加入
                answer = dify_subtract.request_dify(segment_content)
                parse_result = parse_answer(answer, from_file_name, qa_segment['pages'])
                logging.info(f"段落内容: {segment_content}\t段落长度: {len(segment_content)}\t答案: {answer}\t解析结果: {parse_result}")
                json_list.extend(parse_result)

    with open(output_file, 'w', encoding='utf-8') as out_f:
        json.dump(json_list, out_f, ensure_ascii=False, indent=4)
    return json_list


def parse_answer(answer, from_file_name, pages):
    """
    解析Dify模型返回的答案，提取问答对。
    
    :param answer: Dify模型返回的答案文本
    :param from_file_name: 源文件名
    :param pages: 问答对所在的页面范围
    :return: 解析后的问答对列表
    """
    json_list = []
    if not isinstance(answer, str) or not answer.strip():
        logging.warning('Dify QA 返回为空或类型异常: %s', type(answer).__name__)
        return json_list
    qa_pairs = answer.split('###') if '###' in answer else [answer]
    for qa_pair in qa_pairs:
        qa_pair = qa_pair.strip()
        if not qa_pair:
            continue
        # 冒号必须半角全角都认：模型输出形态不稳定，同一批里既有 `问题:` 也有 `问题：`，
        # 只认半角会解析出空列表，再被下游当空输入抛异常，整页 QA 静默丢失
        matches = re.findall(r'问题[:：](.*?)答案[:：](.*?)(?=问题[:：]|$)', qa_pair, re.DOTALL)
        if matches:
            for q, a in matches:
                json_list.append({
                    'q': q.strip(),
                    'a': a.strip(),
                    'from_file_name': from_file_name,
                    'from_page': pages
                })
        else:
            # 尝试匹配 q:/a: 模式（大小写不敏感）
            qa_matches = re.findall(r'\bq\s*[:：]\s*(.*?)\ba\s*[:：]\s*(.*?)(?=\bq\s*[:：]|$)', qa_pair, re.DOTALL | re.IGNORECASE)
            if qa_matches:
                for q, a in qa_matches:
                    json_list.append({
                        'q': q.strip(),
                        'a': a.strip(),
                        'from_file_name': from_file_name,
                        'from_page': pages
                    })
            else:
                # 如果没有找到匹配的问答对，记录日志
                logging.warning(f"无法解析问答对: {qa_pair}")
    return json_list


def run_batch_clear_pdf_json_content(pdf_json_batch_file, flag='', from_file_name_field_num=0, use_image_content=0,
                                     business_context_path=None, quality_profile='', llm_backend='dify',
                                     llm_model_name=None, llm_provider=None, image_placeholder=1):
    """
    批量处理PDF JSON文件，取问答对并添加质量信息。

    :param pdf_json_batch_file: 包含多个PDF JSON文件路径的批处理文件
    :param flag: 用于生成输出文件名的标志
    :param business_context_path: 可选，业务上下文 JSON（business_context_builder 产物）；
        仅在内容有效时增强 prompt，缺省/无效时保持旧行为。
    :param quality_profile: 可选，质量画像标签，透传给本地后端 prompt。
    :param llm_backend: LLM 后端：'dify'（默认，旧行为不变）/'local_llm'/'auto'（local 失败回退 dify）。
    :param llm_model_name: 本地后端模型名（如 openai/gpt-4.1-mini）。
    :param llm_provider: 本地后端渠道名（如 openrouter）。
    :param image_placeholder: 1（默认）启用图片占位符：图片位置给模型 `[图N]` + 该图的
        OCR/图片理解，生成后按映射还原成图片。0 则退回旧行为（图片位置只给裸 URL）。
        旧行为下模型看不到图里的内容，只能把 URL 当答案，而且抄 URL 会抄错。
    """
    api_base = GLOBAL_CONFIG['dify_api_base']
    dify_segment_api_key = GLOBAL_CONFIG.get('dify_api_key_segment', _private_value('e317f1c4f7841b3b99613815'))
    dify_subtract_api_key = GLOBAL_CONFIG.get('dify_api_key_subtract', _private_value('b8868b90bfed91ebd423ffe2'))
    dify_qa_filter_api_key = GLOBAL_CONFIG.get('dify_api_key_qa_filter', _private_value('2c541bf7d777685ca9291aa1'))

    dify_segment = KnowledgeCleaner(api_base=api_base, api_key=dify_segment_api_key, max_retries=3)
    dify_subtract = KnowledgeCleaner(api_base=api_base, api_key=dify_subtract_api_key, max_retries=3)
    dify_qa_filter = KnowledgeCleaner(api_base=api_base, api_key=dify_qa_filter_api_key, max_retries=3)

    business_context = load_business_context(business_context_path)
    use_local = str(llm_backend).lower() in ('local_llm', 'local', 'auto')
    logging.info(f"start process pdf json content, llm_backend={llm_backend}, "
                 f"business_context_enabled={business_context is not None}")


    with open(pdf_json_batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            pdf_json_file = fields[-1]
            logging.info(f'开始处理文件: {pdf_json_file}')

            # 使用 flag 参数来生成输出文件名
            if flag:
                file_path = pdf_json_file.replace('.json', f'_qa_{flag}.txt')
                add_quality_file = pdf_json_file.replace('.json', f'_qa_add_quality_{flag}.txt')
            else:
                file_path = pdf_json_file.replace('.json', '_qa.txt')
                add_quality_file = pdf_json_file.replace('.json', '_qa_add_quality.txt')
            output_file = file_path
            from_file_name = fields[from_file_name_field_num]

            # 保存整个文档内容
            all_content_file = pdf_json_file.replace('.json', '_all_content.txt')
            save_all_document_content(pdf_json_file, all_content_file, use_image_content)

            # 映射必须**按文件**新建：它在拼正文时生成、在还原时才用，中间隔着 LLM 调用，
            # 用全局变量会让多文件之间串号。
            image_placeholder_map = {} if (use_image_content and image_placeholder) else None

            quality_result = None
            if use_local:
                try:
                    qa_extract_json_list = clear_pdf_json_content_local(
                        pdf_json_file, output_file, business_context, from_file_name,
                        use_image_content=use_image_content, model_name=llm_model_name,
                        provider=llm_provider, quality_profile=quality_profile,
                        image_placeholder_map=image_placeholder_map,
                    )
                    if qa_extract_json_list and image_placeholder_map is not None:
                        for _qa in qa_extract_json_list:
                            _qa['a'] = strip_hallucinated_image_urls(_qa.get('a', ''))
                    if qa_extract_json_list:
                        quality_result = mark_local_qa_quality(copy.deepcopy(qa_extract_json_list))
                    elif str(llm_backend).lower() == 'auto':
                        logging.warning('本地后端无输出，auto 模式回退 Dify')
                    else:
                        logging.warning('本地后端无输出，生成空 QA 结果')
                        quality_result = {'high': [], 'mid': [], 'low': []}
                except Exception as e:
                    logging.error(f'本地后端 QA 生成失败: {e}')
                    if str(llm_backend).lower() != 'auto':
                        quality_result = {'high': [], 'mid': [], 'low': []}

            if quality_result is None:
                # Dify 后端（默认 / auto 回退）：与旧流程完全一致
                qa_extract_json_list = clear_pdf_json_content(
                    pdf_json_file, output_file, dify_segment, dify_subtract, from_file_name,
                    use_image_content, image_placeholder_map=image_placeholder_map)
                # 送质检**之前**先清掉模型编造的图床 URL：这类幻觉会退化成复读，
                # 一条就能撑爆质检调用的 token 预算，让整批 QA 丢标签。
                if image_placeholder_map is not None:
                    for _qa in qa_extract_json_list:
                        _qa['a'] = strip_hallucinated_image_urls(_qa.get('a', ''))
                # 添加质量信息并分类
                quality_result = add_quality_info_to_qa_json(copy.deepcopy(qa_extract_json_list), dify_qa_filter)

            # 占位符还原：答案里的 [图N] 换成真实图片，问题里的直接去掉。
            # URL 从映射表取，不经过模型，所以不可能出现抄错的坏链。
            if image_placeholder_map:
                for bucket in quality_result.values():
                    for qa_item in bucket:
                        qa_item['a'] = restore_image_placeholders(
                            qa_item.get('a', ''), image_placeholder_map)
                        qa_item['q'] = strip_image_placeholders(qa_item.get('q', ''))
                logging.info('图片占位符还原完成: %s 张图', len(image_placeholder_map))

            # 将更新后的qa列表写回文件
            with open(add_quality_file, 'w', encoding='utf-8') as out_f:
                json.dump(quality_result, out_f, ensure_ascii=False, indent=4)

            fields.append(file_path)
            fields.append(all_content_file)
            fields.append(add_quality_file)
            print('\t'.join(fields))


def parse_dify_segment(segment_answer):
    """
    解析Dify分段模型的返回结果。
    
    :param segment_answer: Dify分段模型的返回文本
    :return: 解析后的段落信息列表
    """
    segments = []
    if not isinstance(segment_answer, str) or not segment_answer.strip():
        logging.warning('Dify 分段返回为空或类型异常: %s', type(segment_answer).__name__)
        return segments
    # 使用正则表达式匹配段落信息
    pattern = re.compile(r'(.+?)\s+第(\d+)页\s+第(\d+)页')
    for match in pattern.finditer(segment_answer):
        title = match.group(1).strip()
        start_page = int(match.group(2))
        end_page = int(match.group(3))
        segments.append({
            'title': title,
            'pages': [start_page, end_page]
        })
    return segments


def parse_quality_result(quality_result):
    """
    解析质量评估结果。
    
    :param quality_result: Dify质量评估模型的返回文本
    :return: 解析后的质量信息字典
    """
    quality_info = {}
    qa_pairs = quality_result.split('###') if '###' in quality_result else [quality_result]
    index = 1 
    for qa_pair in qa_pairs:
        qa_pair = qa_pair.strip()
        if not qa_pair:
            continue
        
        # 冒号必须半角全角都认：模型输出形态不稳定，同一批里既有 `问题:` 也有 `问题：`，
        # 只认半角会解析出空列表，再被下游当空输入抛异常，整页 QA 静默丢失
        matches = re.findall(r'问题[:：](.*?)答案[:：](.*?)(?=问题[:：]|$)', qa_pair, re.DOTALL)
        for match in matches:
            question, answer = match
            question = question.strip()
            answer = answer.strip()
            
            # 从答案中提取标签
            tags, answer_without_tags = extract_tags(answer)
            duplicate_index = find_duplicate_index(tags)
            logging.info(f'问题: {question}\torianswer:{answer}, 索引: {index}\t答���: {answer_without_tags}\t标签: {tags}\t重复索引: {duplicate_index}')
            
            quality_info[index] = {
                'question': question,
                'answer': answer_without_tags,
                'tags': tags,
                'duplicate_index': duplicate_index
            }
            
            logging.info(f'索引: {index}\t问题: {question}\t答案: {answer_without_tags}\t标签: {tags}\t重复索引: {duplicate_index}')
            index += 1
    
    return quality_info


def extract_tags(answer):
    """
    从答案中提取标签。
    
    :param answer: 包含标签的��案文本
    :return: ��签列表和不包含标签的答案
    """
    tags = []
    answer_without_tags = answer
    
    # 查找答案末尾的标签
    tag_match = re.search(r'(#[^#\s]+)+$', answer)
    if tag_match:
        tag_string = tag_match.group()
        tags = tag_string.split('#')[1:]  # 去掉空字符串
        answer_without_tags = answer[:tag_match.start()].strip()
    
    return tags, answer_without_tags


def request_quality_info_in_batches(qa_json_list, dify_qa_filter, batch_size=QA_QUALITY_BATCH_SIZE):
    """分块送质检，再按全局序号把每批结果合起来。

    **不要退回「整份清单一次调用」**：质检模型要逐条回标签，条数一多必然对不上。
    实测印尼那篇 584 条一次发出去，只有 180 条对上，其余 404 条拿不到标签、
    在 `add_quality_info_to_qa_json` 里落到「没有对应质检结果」分支被清空，全部降级；
    而 76~77 条的小文档完全正常。同样的坑在聊天 QA 链路上踩过一次，
    修法就是分块 + 条数校验（见 docs/chat_qa_extract_local_migration.md）。

    注意：`#重复-N` 里的 N 是**批内序号**，合并时要按批偏移换算成全局序号，
    否则分组会串到别的 QA 上。
    代价是跨批的重复检测不到——宁可漏判重复，也不要整批丢标签。
    """
    quality_info = {}
    total = len(qa_json_list)
    for start in range(0, total, batch_size):
        chunk = qa_json_list[start:start + batch_size]
        qa_text = schema_trans.qajson_to_line_text(chunk, add_index=True)
        if not qa_text or not qa_text.strip():
            continue
        try:
            quality_result = dify_qa_filter.request_dify(qa_text)
        except Exception as exc:  # noqa: BLE001
            logging.error('质检调用失败 batch=%s-%s: %s', start + 1, start + len(chunk), exc)
            continue
        if quality_result is None:
            logging.error('质检返回为空 batch=%s-%s', start + 1, start + len(chunk))
            continue
        parsed = parse_quality_result(quality_result)
        if len(parsed) != len(chunk):
            logging.warning('质检条数不符 batch=%s-%s 期望%s 实得%s（该批部分条目将无标签）',
                            start + 1, start + len(chunk), len(chunk), len(parsed))
        for local_idx, info in parsed.items():
            dup = info.get('duplicate_index')
            if dup:
                info = dict(info, duplicate_index=start + int(dup))
            quality_info[start + local_idx] = info
    logging.info('质检分块完成: 共%s条，分%s批，拿到标签%s条',
                 total, (total + batch_size - 1) // batch_size, len(quality_info))
    return quality_info


def add_quality_info_to_qa_json(qa_json_list, dify_qa_filter):
    """
    为问答对添加质量信息，统计每组的QA数量，并将其分为高质量和中等质量两类。
    
    :param qa_json_list: 原始问答对列表
    :param dify_qa_filter: 用于质量评估的Dify模型实例
    :return: 包含高质量和中等质量问答对的字典
    """
    dedup_qa_info_list = deduplicate_qa_list(qa_json_list)
    logging.info(f'before dedup_len {len(qa_json_list)} afterlen {len(dedup_qa_info_list)} deduplicate_qa_list: {dedup_qa_info_list}')
    qa_json_list = dedup_qa_info_list
    # 没有 QA 就别调质检：空输入会让 request_dify 抛 ValueError，异常会把整页产出带没，
    # 而上层只记一条 ERROR、阶段照报成功，结果是整页知识静默消失（实测 FAQs 页就这么丢的）
    if not qa_json_list:
        logging.warning('QA 列表为空，跳过质量评估（通常是上游解析失败，请检查 parse_answer 日志）')
        return {'high': [], 'mid': qa_json_list}

    quality_info = request_quality_info_in_batches(qa_json_list, dify_qa_filter)

    if not quality_info:
        logging.error("无法获取质量评估结果")
        return {'high': [], 'mid': qa_json_list}
    
    group_counter = 0
    group_mapping = {}
    group_qa_count = {}
    
    # 第一次遍历：分配组号和统计每组的QA数量
    for i, qa_item in enumerate(qa_json_list):
        if i + 1 in quality_info:
            qa_info = quality_info[i + 1]
            qa_content1 = qa_item['q'] #+ '\n' + qa_item['a']
            qa_content2 = qa_info['question'] #+ '\n' + qa_info['answer']
            if common_utils.context_dice(qa_content1, qa_content2) < 0.9:
                qa_item['quality_info'] = []
                qa_item['duplicate_index'] = i + 1
                group_counter += 1
                qa_item['group'] = group_counter
                group_qa_count[group_counter] = 1                
                logging.info('index %s not simility, not match skip, content1: %s, content2: %s', i + 1, qa_content1, qa_content2)
                continue
            qa_item['quality_info'] = qa_info['tags']
            qa_item['duplicate_index'] = qa_info['duplicate_index'] or (i + 1)
            if qa_item['duplicate_index'] == i + 1:
                group_counter += 1
                group_mapping[i + 1] = group_counter
                qa_item['group'] = group_counter
                group_qa_count[group_counter] = 1
            else:
                qa_item['group'] = group_mapping.get(qa_item['duplicate_index'], group_counter)
                group_qa_count[qa_item['group']] = group_qa_count.get(qa_item['group'], 0) + 1
        else:
            qa_item['quality_info'] = []
            qa_item['duplicate_index'] = i + 1
            group_counter += 1
            qa_item['group'] = group_counter
            group_qa_count[group_counter] = 1
    
    # 第二次遍历：添加每组的QA数量到每个QA项
    for qa_item in qa_json_list:
        qa_item['group_qa_count'] = group_qa_count[qa_item['group']]
    
    high_quality_qa_list = []
    mid_quality_qa_list = []
    
    for qa_item in qa_json_list:
        if '优质' in qa_item['quality_info'] and qa_item['group_qa_count'] == 1:
            high_quality_qa_list.append(qa_item)
        else:
            mid_quality_qa_list.append(qa_item)
    
    high_quality_qa_list.sort(key=lambda x: x['group'])
    mid_quality_qa_list.sort(key=lambda x: x['group'])
    
    return {'high': high_quality_qa_list, 'mid': mid_quality_qa_list}


"""
Authors: qishichen(263436967@qq.com)
Date: 2024-10-19
"""


if __name__ == '__main__':
    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')  
    import fire
    fire.Fire({
        'run_batch_clear_pdf_json_content': run_batch_clear_pdf_json_content,
    })
