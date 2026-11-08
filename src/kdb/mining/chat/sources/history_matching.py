import kdb.shared.text.common_utils as common_utils
from kdb.mining.chat.sources.robot_files import load_and_reorg_one_robot_data
from kdb.mining.chat.generation.batch import get_normal_group_bigmodel_prompt
import json
import logging
import sys
import os
import traceback

def find_similar_chat_history(group_chat_list, qa_info, similar_threshold=0.8, pre_history_near_nums=5, post_history_near_nums=10):
    """
    查询qa的来源历史记录
    """
    group_chat_list = list(sorted(group_chat_list, key=lambda m: m['message_time']))

    query = qa_info['title']
    answer = qa_info['content']
    simility_chat_histories = []
    for index, chat_info in enumerate(group_chat_list):
        chat_content = chat_info['content']
        query_sim_score = common_utils.context_dice_min(query, chat_content)
        if query_sim_score < similar_threshold:
            continue
        near_start_index = max(0, index - pre_history_near_nums)
        near_end_index = min(len(group_chat_list), index + post_history_near_nums)
        answer_sim_score = 0
        for near_index in range(near_start_index, near_end_index):
            near_chat_info = group_chat_list[near_index]
            near_chat_content = near_chat_info['content']
            answer_sim_score_tmp = common_utils.context_dice_min(answer, near_chat_content)
            answer_sim_score = max(answer_sim_score, answer_sim_score_tmp)
        simility_chat_histories.append((query_sim_score, answer_sim_score, group_chat_list[near_start_index: near_end_index]))
    return simility_chat_histories


def process_qa_file(data_file, chat_history_file):
    """
    处理单个机器人的数据
    """
    
    reorga_chat_dict = load_and_reorg_one_robot_data('all', chat_history_file, None, 
                                                     {}, need_robot_reply=True)
    all_qa_list = []
    with open(data_file, encoding='utf8') as f:
        for line in f:
            line = line.strip('\n')
            if not line:
                continue
            fields = line.split('\t')
            
            qa_info = json.loads(fields[-1])
            from_group_name = qa_info['ext_info'].get('from_file_name', 'unkonw')
            group_chat_list = reorga_chat_dict.get(from_group_name, [])
            if 'from_chat_history' not in qa_info and 'from_chat_history' not in qa_info['ext_info']:
                similar_chat_histories = find_similar_chat_history(group_chat_list, qa_info, similar_threshold=0.7, pre_history_near_nums=5, post_history_near_nums=15)
                if similar_chat_histories:
                    similar_chat_history = sorted(similar_chat_histories, key=lambda x: (x[0], x[1]), reverse=True) # 以答案相似度排序，如果答案相似度相同，则以查询相似度排序
                    similar_chat_history = similar_chat_history[0]
                    from_chat_history = get_normal_group_bigmodel_prompt(from_group_name, similar_chat_history[2], [], sep='\n')
                    qa_info['from_chat_history'] = from_chat_history
                else:
                    qa_info['from_chat_history'] = ''
            else:
                if 'from_chat_history' in qa_info['ext_info']:
                    qa_info['from_chat_history'] = qa_info['ext_info']['from_chat_history']
            fields[-1] = json.dumps(qa_info, ensure_ascii=False)
            new_line = "\t".join(fields)
            print(new_line)


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    import fire
    fire.Fire({
        'process_qa_file': process_qa_file,
    })


