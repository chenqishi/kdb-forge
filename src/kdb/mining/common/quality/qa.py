from kdb.mining.common.deduplication.qa import deduplicate_qa_list
from kdb.mining.common.deduplication.qa import re_group_qa_list
from kdb.shared.clients.dify_tools import DifyWorkFlowRequest
from kdb.shared.config.global_config import GLOBAL_CONFIG as config
import json
import kdb.mining.common.schema.qa_model_output as qa_text_tools
import kdb.mining.common.schema.review_formats as schema_trans
import kdb.shared.text.common_utils as common_utils
import logging
import sys
import traceback

HIGH_QUALITY_TAG = set(['优质', '高质量'])


MID_QUALITY_TAG = set(['无法判断'])


LOW_QUALITY_TAG = set(['不相关', '无实质答案', '不通用'])


def judge_qa_quality(qa_info):
    """
    判断QA质量
    """
    quailt_tag = set(qa_info.get('quality_info', []))
    if quailt_tag & HIGH_QUALITY_TAG:
        return 'high'
    elif quailt_tag & LOW_QUALITY_TAG:
        return 'low'
    else:
        return 'mid'


def split_qa_list(qa_info_list, exsited_gorup_key='group'):
    """
    """
    new_gorup_dict = re_group_qa_list(qa_info_list, exsited_gorup_key)
    high_quality_qa_list = list()
    mid_quality_qa_list = list()
    low_quality_qa_list = list()
    def _split_by_quality_tag(inner_qa_list):
        high_tmp = list()
        mid_tmp = list()
        low_tmp = list()
        for qa_info in inner_qa_list:
            quality_tag = judge_qa_quality(qa_info)
            qa_info['quality_level'] = quality_tag
            if quality_tag == 'high':
                high_tmp.append(qa_info)
            elif quality_tag == 'mid':
                mid_tmp.append(qa_info)
            else:
                low_tmp.append(qa_info)
        return high_tmp, mid_tmp, low_tmp
    for group_index, qa_info_list in new_gorup_dict.items():
        qa_info_list = list(filter(lambda x: x.get('q', '').strip(), qa_info_list))
        qa_info_list = sorted(qa_info_list, key=lambda x: len(x['a']), reverse=True)
        high_tmp, mid_tmp, low_tmp = _split_by_quality_tag(qa_info_list)

        # 当存在一个高质QA，其余重复QA都扔进低质
        if len(high_tmp) > 0:
            high_quality_qa_list.append(high_tmp[0])
            reason = f'存在一个高质QA[q:{high_tmp[0]["q"]}, a:{high_tmp[0]["a"]}]，其余重复QA都扔进低质' 
            high_tmp = high_tmp[1:]
           
        elif len(mid_tmp) > 0:
            mid_quality_qa_list.append(mid_tmp[0])
            reason = f'无高质qa，存在一个中质QA[q:{mid_tmp[0]["q"]}, a:{mid_tmp[0]["a"]}]，其余重复QA都扔进低质'
            mid_tmp = mid_tmp[1:]
        else:
            reason = f'无高质和中质QA，所有QA都扔进低质'
        all_qa_tmp = high_tmp + mid_tmp + low_tmp
        for qa_info in all_qa_tmp:
            qa_info['reason'] = reason
        low_quality_qa_list.extend(all_qa_tmp)
    return high_quality_qa_list, mid_quality_qa_list, low_quality_qa_list


def add_quality_info_to_qa_json_by_dify(qa_json_list, dify_qa_filter):
    """
    为问答对添加质量信息，统计每组的QA数量，并将其分为高质量和中等质量两类。
    
    :param qa_json_list: 原始问答对列表
    :param dify_qa_filter: 用于质量评估的Dify模型实例
    :return: 包含高质量和中等质量问答对的字典
    """
    dedup_qa_info_list = deduplicate_qa_list(qa_json_list)
    logging.info(f'before dedup_len {len(qa_json_list)} afterlen {len(dedup_qa_info_list)} deduplicate_qa_list: {dedup_qa_info_list}')
    qa_json_list = dedup_qa_info_list
    qa_text = schema_trans.qajson_to_line_text(qa_json_list, add_index=True)
    if not qa_text:
        # QA 列表为空是正常情况（该群没抽出可用问答），不是错误
        logging.info(f'qa_text is empty, qa_json_list: {qa_json_list}')
        return {'high': [], 'mid': qa_json_list}
    quality_result = dify_qa_filter.request_dify(qa_text)
    
    if quality_result is None:
        logging.error("无法获取质量评估结果")
        return {'high': [], 'mid': qa_json_list}
    
    quality_info = qa_text_tools.parse_qa_quality_result(quality_result)
    logging.info(f'ori_quality_result: {quality_result}, parse_quality_result: {quality_info}')
    
    group_counter = 0
    group_mapping = {}
    group_qa_count = {}
    
    # 第一次遍历：分配组号和统计每组的QA数量
    for i, qa_item in enumerate(qa_json_list):
        if i + 1 in quality_info:
            qa_info = quality_info[i + 1]
            qa_content1 = qa_item['q'] + '\n' + qa_item['a']
            qa_content2 = qa_info['question'] + '\n' + qa_info['answer']
            if common_utils.context_dice(qa_content1, qa_content2) < 0.9:
                logging.info('index %s not simility, not match skip, content1: %s, content2: %s', i + 1, qa_content1, qa_content2)
                qa_item['quality_info'] = []
                qa_item['duplicate_index'] = i + 1
                group_counter += 1
                qa_item['group'] = group_counter
                group_qa_count[group_counter] = 1                
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


def re_clear_qa_info(qa_info_file, output_file=None):
    """
    重新过滤qa数据
    """
    if output_file is None:
        output_file = qa_info_file.replace('.json', '_re_clear.json').replace('.txt', '_re_clear.txt')
    qa_info_dict = json.load(open(qa_info_file, 'r', encoding='utf-8'))
    all_qa_list = list()
    for k, v in qa_info_dict.items():
        all_qa_list.extend(v)
    high_quality_qa_list, mid_quality_qa_list, low_quality_qa_list = split_qa_list(all_qa_list)
    new_qa_info_dict = dict()
    new_qa_info_dict['high'] = high_quality_qa_list
    new_qa_info_dict['mid'] = mid_quality_qa_list
    new_qa_info_dict['low'] = low_quality_qa_list
    json.dump(new_qa_info_dict, open(output_file, 'w', encoding='utf-8'), ensure_ascii=False, indent=4)
    return output_file


def run_batch_re_clear_qa_info(input_file, output_file, process_field_num=-1, flag=''):
    """
    批量重新处理qa
    """
    with open(input_file, 'r', encoding='utf-8') as f, open(output_file, 'w', encoding='utf-8') as out_f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            qa_info_file = fields[process_field_num]
            new_qa_info_file = re_clear_qa_info(qa_info_file, None)
            fields.append(new_qa_info_file)
            out_f.write('\t'.join(fields) + '\n')


def add_dify_quality_and_resplit_file(qa_info_file, output_file, dify_qa_filter):
    """
    为问答对添加质量信息并重新分割
    """
    try:
        logging.info(f'process qa_info_file: {qa_info_file}')
        if isinstance(dify_qa_filter, str): # 如果dify_qa_filter是字符串，则认为是dify_api_key
            dify_qa_filter = DifyWorkFlowRequest(config.get('dify_api_base'), config.get(f'dify_api_key_{dify_qa_filter}'))
        qa_info_list = [l.strip() for l in open(qa_info_file, 'r', encoding='utf-8')]
        qa_info_list = [json.loads(l) for l in qa_info_list if l]
        qa_info_add_quality_dict = add_quality_info_to_qa_json_by_dify(qa_info_list, dify_qa_filter)
        qa_info_add_quality_list = list()
        for k, v in qa_info_add_quality_dict.items():
            qa_info_add_quality_list.extend(v)
        high_quality_qa_list, mid_quality_qa_list, low_quality_qa_list = split_qa_list(qa_info_add_quality_list)
        new_qa_info_dict = dict()
        new_qa_info_dict['high'] = high_quality_qa_list
        new_qa_info_dict['mid'] = mid_quality_qa_list
        new_qa_info_dict['low'] = low_quality_qa_list
        json.dump(new_qa_info_dict, open(output_file, 'w', encoding='utf-8'), ensure_ascii=False, indent=4)
    except:
        tb = traceback.format_exc()
        logging.error(f'process qa_info_file: {qa_info_file} error: {tb}')
        exit(1)
    
    return output_file


def build_qa_filter(dify_qa_filter_name='dify_qa_filter', client=''):
    """
    构造 QA 质检客户端。

    本地 chat_qa_extract 已配好凭证时返回本地实现（对应 Dify 流「qa选择过滤」，
    额外做了分块和条数对齐，并按 client 命中 prompts/quality.<client>.md 的增强规则）；
    未配置时回落到原 Dify 流，行为与改造前一致。
    """
    try:
        from kdb.mining.common.quality.filter import build_quality_filter
        from kdb.mining.common.llm.config import load_llm_config
        import kdb.mining.common.llm.client as local_llm
        load_llm_config()
        if local_llm.is_configured():
            qa_filter = build_quality_filter(client=client)
            logging.info('QA质检使用本地 chat_qa_extract, client=%s, model=%s, batch_size=%d',
                         client, qa_filter.model, qa_filter.batch_size)
            return qa_filter
        logging.warning('chat_qa_extract 未配置 LLM 凭证，QA质检回落 Dify 流')
    except Exception as e:  # noqa: BLE001
        logging.warning('chat_qa_extract 不可用，QA质检回落 Dify: %s', e)

    return DifyWorkFlowRequest(config.get('dify_api_base'),
                               config.get(f'dify_api_key_{dify_qa_filter_name}'))


def run_batch_add_dify_quality_and_resplit(input_file, output_file, process_field_num=-1, dify_qa_filter_name='dify_qa_filter', flag='', client=''):
    """
    批量添加dify质量信息并重新分割

    Args:
        client: 客户名，用于命中 prompts/quality.<client>.md 的增强判定规则
    """
    dify_qa_filter = build_qa_filter(dify_qa_filter_name, client)
    with open(input_file, 'r', encoding='utf-8') as f, open(output_file, 'w', encoding='utf-8') as out_f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            qa_info_file = fields[process_field_num]
            prefix = '.'.join(qa_info_file.rsplit('.', 1)[0: -1])
            suffix = qa_info_file.split('.')[-1]
            output_qa_info_file = f'{prefix}_dify_quality_and_resplit.{suffix}'
            new_qa_info_file = add_dify_quality_and_resplit_file(qa_info_file, output_qa_info_file, dify_qa_filter)
            fields.append(new_qa_info_file)
            out_f.write('\t'.join(fields) + '\n')


def only_add_tags_file(qa_info_file, output_file):
    """
    仅为问答对添加[优质]标签，不做质量检测
    输出格式与add_dify_quality_and_resplit_file完全一样
    """
    try:
        logging.info(f'process qa_info_file: {qa_info_file}')
        # 读取QA文件（JSONL格式）
        qa_info_list = []
        with open(qa_info_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    qa_info_list.append(json.loads(line))
        
        # 为每个QA添加quality_info字段，值为['优质']
        high_quality_qa_list = []
        for qa_item in qa_info_list:
            qa_item['quality_info'] = ['优质']
            qa_item['quality_level'] = 'high'
            high_quality_qa_list.append(qa_item)
        
        # 按照与add_dify_quality_and_resplit_file相同的格式输出
        new_qa_info_dict = {
            'high': high_quality_qa_list,
            'mid': [],
            'low': []
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(new_qa_info_dict, f, ensure_ascii=False, indent=4)
        
        logging.info(f'successfully processed {len(high_quality_qa_list)} QAs, output to {output_file}')
        
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f'process qa_info_file: {qa_info_file} error: {tb}')
        exit(1)
    
    return output_file


def run_batch_only_add_tags(input_file, output_file, process_field_num=-1, flag=''):
    """
    批量仅添加[优质]标签，不做质量检测
    输入输出格式与run_batch_add_dify_quality_and_resplit完全一样
    """
    with open(input_file, 'r', encoding='utf-8') as f, open(output_file, 'w', encoding='utf-8') as out_f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            qa_info_file = fields[process_field_num]
            prefix = '.'.join(qa_info_file.rsplit('.', 1)[0: -1])
            suffix = qa_info_file.split('.')[-1]
            output_qa_info_file = f'{prefix}_dify_quality_and_resplit.{suffix}'
            new_qa_info_file = only_add_tags_file(qa_info_file, output_qa_info_file)
            fields.append(new_qa_info_file)
            out_f.write('\t'.join(fields) + '\n')


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    import fire
    fire.Fire({
        'run_batch_re_clear_qa_info': run_batch_re_clear_qa_info,
        'run_batch_add_dify_quality_and_resplit': run_batch_add_dify_quality_and_resplit,
        'add_dify_quality_and_resplit_file': add_dify_quality_and_resplit_file,
        'run_batch_only_add_tags': run_batch_only_add_tags,
        'only_add_tags_file': only_add_tags_file,
    })
