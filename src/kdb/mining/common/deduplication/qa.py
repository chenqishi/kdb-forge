import kdb.shared.text.common_utils as common_utils

def is_simlity_qa_info(qa_info_1, qa_info_2, title_threshold=0.9, answer_threshold=0.8):
    """
    """
    qa_1_title = qa_info_1['q']
    qa_2_title = qa_info_2['q']
    qa_1_answer = qa_info_1['a']
    qa_2_answer = qa_info_2['a']
    if common_utils.context_dice(qa_1_title, qa_2_title) > 0.9:
        return True
    elif common_utils.context_dice(qa_1_answer, qa_2_answer) > 0.8  and qa_1_answer.find('未提供答案') == -1:
        return True
    else:
        return False


def deduplicate_qa_list(qa_info_list):
    """
    去重
    """
    deduplicate_qa_list = list()
    qa_info_list = sorted(qa_info_list, key=lambda x: len(x['a']), reverse=True)
    for qa_info in qa_info_list:
        for deduplicate_qa in deduplicate_qa_list:
            if qa_info.get('platform') == deduplicate_qa.get('platform') and is_simlity_qa_info(qa_info, deduplicate_qa,
                                  title_threshold=0.95, answer_threshold=0.9):
                break
        else:
            deduplicate_qa_list.append(qa_info)
    return deduplicate_qa_list


def re_group_qa_list(qa_info_list, exsited_gorup_key='group'):
    """
    """   
    process_qa_list = list()
    group_index = 0
    for qa_info in qa_info_list:
        has_simility = False
        for process_qa in process_qa_list:
            is_simility = (is_simlity_qa_info(qa_info, process_qa) and (qa_info.get('platform') == process_qa.get('platform')))
            is_same_group = (qa_info.get(exsited_gorup_key) == process_qa.get(exsited_gorup_key)) & (qa_info.get(exsited_gorup_key) is not None)
            if is_simility or is_same_group:
                has_simility = True
                qa_info['re_gorup_index'] = process_qa['re_gorup_index']
                process_qa_list.append(qa_info)
                break
        if not has_simility:
            qa_info['re_gorup_index'] = group_index
            group_index += 1
            process_qa_list.append(qa_info)
    regroup_qa_dict = dict()
    for qa_info in process_qa_list:
        group_index = qa_info['re_gorup_index']
        regroup_qa_dict.setdefault(group_index, list()).append(qa_info)
    return regroup_qa_dict
