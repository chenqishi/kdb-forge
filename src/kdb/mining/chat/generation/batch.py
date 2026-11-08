from kdb.mining.chat.generation.answer_windows import request_llm_for_answer_windows
from kdb.mining.chat.generation.direct_json import DirectLLMJsonRequest
from kdb.mining.chat.generation.output import build_direct_llm_quality_batch
from kdb.mining.chat.generation.output import write_quality_bucket_file
from kdb.mining.chat.identity import extract_answer_source_names
from kdb.mining.chat.identity import load_contact_identity_lookup
from kdb.mining.chat.prompts import build_group_prompt_header
from kdb.mining.chat.prompts import format_chat_message_for_model
from kdb.mining.chat.reports.llm_run import build_llm_run_summary
from kdb.mining.chat.reports.llm_run import write_llm_run_summary
from kdb.mining.chat.sources.robot_files import load_and_reorg_one_robot_data
from kdb.mining.chat.sources.robot_files import load_robot_room_type
from kdb.mining.chat.sources.robot_files import load_white_list_dict
from kdb.mining.chat.sources.robot_files import save_3file_dict
from kdb.shared.text.common_utils import load_attr_map_dict as load_3file_dict
import json
import kdb.shared.text.common_utils as common_utils
import logging
import os
import sys

def get_forword_group_bigmodel_prompt(group_name, group_chat_list, sep='\n',
                                      white_name_list=None, answer_source_names=None, platform=None,
                                      identity_lookup=None):
    """
    获取转发群的大模型prompt
    """
    prompt_list = []
    group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
    for index, message_info in enumerate(group_chat_list, 1):
        prompt_list.append(format_chat_message_for_model(
            message_info, index,
            white_name_list=white_name_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup
        ))

    prompt_str = sep.join(prompt_list)
    if group_name:
        prompt_str = build_group_prompt_header(group_name, platform, answer_source_names) + prompt_str
    return prompt_str


def get_normal_group_bigmodel_prompt(group_name, group_chat_list, white_name_list, sep='\n',
                                     answer_source_names=None, platform=None, identity_lookup=None):
    """
    获取普通群的大模型prompt
    """
    prompt_list = []
    group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
    for index, message_info in enumerate(group_chat_list, 1):
        prompt_list.append(format_chat_message_for_model(
            message_info, index,
            white_name_list=white_name_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup
        ))
    prompt_str = sep.join(prompt_list)
    if group_name:
        prompt_str = build_group_prompt_header(group_name, platform, answer_source_names) + prompt_str
    return prompt_str


def process_forward_group_data(group_name, platform, group_chat_list,
                               group_white_list, llm_model, answer_source_names=None,
                               identity_lookup=None):
    """
    处理转发群的数据
    """
    return request_llm_for_answer_windows(
        group_name,
        platform,
        group_chat_list,
        group_white_list,
        llm_model,
        answer_source_names=answer_source_names,
        identity_lookup=identity_lookup
    )


def process_normal_group_data(group_name, platform, group_chat_list, group_white_list, llm_model,
                              answer_source_names=None, identity_lookup=None):
    """
    处理普通群的数据
    """
    return request_llm_for_answer_windows(
        group_name,
        platform,
        group_chat_list,
        group_white_list,
        llm_model,
        answer_source_names=answer_source_names,
        identity_lookup=identity_lookup
    )


def process_one_group_data(group_name, group_chat_list, group_type,
                           group_white_list, platform, forward_llm_model, norm_llm_model,
                           answer_source_names=None, identity_lookup=None):
    """
    处理单个群的数据
    """
    if group_type == 'forward':
        return process_forward_group_data(
            group_name, platform, group_chat_list, group_white_list,
            forward_llm_model,
            answer_source_names=answer_source_names,
            identity_lookup=identity_lookup
        )
    elif group_type == 'normal':
        return process_normal_group_data(
            group_name, platform, group_chat_list, group_white_list,
            norm_llm_model,
            answer_source_names=answer_source_names,
            identity_lookup=identity_lookup
        )

    else:
        raise ValueError(f"群类型错误: {group_type}")


def process_one_robot_group_data(robot_name, data_file,
                                robot_room_type_config, robot_white_list_dict, robot_room_process_record=None,
                                need_robot_reply=False, need_add_chat_history=True, prompt_file=None,
                                client=None,
                                identity_lookup=None, mysql_config_file='config/mysql_conn_config.json',
                                run_stats=None):
    """
    处理单个机器人的数据
    """
    logging.info(f'process robot_name:{robot_name} data_file:{data_file}')
    if isinstance(robot_room_type_config, str):
        robot_room_type_config = load_robot_room_type(robot_room_type_config)
    if robot_room_process_record is None:
        robot_room_process_record = dict()
    if isinstance(robot_white_list_dict, str):
        robot_white_list_dict = load_white_list_dict(robot_white_list_dict)
    if identity_lookup is None:
        identity_lookup = load_contact_identity_lookup(mysql_config_file)

    reorga_chat_dict = load_and_reorg_one_robot_data(robot_name, data_file, robot_room_type_config.get(robot_name, {}),
                                                     robot_room_process_record, need_robot_reply)
    logging.info(f'robot_name:{robot_name} reorga_chat_dict:\n{reorga_chat_dict}\n')
    if prompt_file:
        system_prompt = open(prompt_file, encoding='utf8').read()
    else:
        system_prompt = None
    answer_source_names = extract_answer_source_names(system_prompt)

    logging.info(f'robot_name:{robot_name} prompt_file:{prompt_file} system_prompt:\n{system_prompt}\n')
    direct_llm_model = DirectLLMJsonRequest(system_prompt=system_prompt, client=client)
    if hasattr(direct_llm_model, 'validate_config'):
        direct_llm_model.validate_config()
    forward_llm_model_nomix = direct_llm_model
    forward_llm_model_mix = direct_llm_model
    norm_llm_model_nomix = direct_llm_model
    norm_llm_model_mix = direct_llm_model
    all_qa_list = []
    eligible_group_count = 0
    successful_group_count = 0
    group_failures = []
    group_type_config = robot_room_type_config.get(robot_name, {})
    logging.info(f'group_type_config:\n{group_type_config}\n')
    logging.info(f'reorga_chat_dict:\n{len(reorga_chat_dict)}\n')
    for group_name, group_chat_list in reorga_chat_dict.items():
        if group_name in group_type_config:
            group_type = group_type_config[group_name].get('type', 'unknown')
            platform = group_type_config[group_name].get('platform', 'unknown')
        elif 'all' in group_type_config:
            # 命中黑名单
            logging.info('group_name[%s], black_name_set[%s], is_hit[%s]', group_name, group_type_config['all'].get('black_group', set()), group_name in group_type_config['all'].get('black_group', set()))
            if group_name in group_type_config['all'].get('black_group', set()):
                continue
            group_type = group_type_config['all'].get('type', 'unknown')
            platform = group_type_config['all'].get('platform', 'unknown')
        else:
            logging.info(f'group_name[{group_name}] not in group_type_config and not has all')
            continue
        eligible_group_count += 1
        logging.info(f'group_name:{group_name} group_type:{group_type} platform:{platform}')
        white_list = robot_white_list_dict.get(robot_name, {}).get(group_name, [])
        if platform == 'mix':
            norm_llm_model = norm_llm_model_mix
            forward_llm_model = forward_llm_model_mix
        else:
            norm_llm_model = norm_llm_model_nomix
            forward_llm_model = forward_llm_model_nomix
        try:
            qa_list = process_one_group_data(
                group_name,
                group_chat_list,
                group_type,
                white_list,
                platform,
                forward_llm_model,
                norm_llm_model,
                answer_source_names=answer_source_names,
                identity_lookup=identity_lookup
            )
        except Exception as e:
            # 继续处理同一机器人其它群以保留完整失败证据；批次入口会在所有群处理完后
            # 将任何群失败升级为任务失败，因此 App/全局水位都不会推进。
            group_failures.append({
                'group_name': group_name,
                'error_type': type(e).__name__,
                'error': str(e)[:500],
            })
            logging.error(
                'group[%s] process failed, skip without advancing watermark. err: %s',
                group_name,
                e,
                exc_info=True
            )
            continue
        successful_group_count += 1
        if need_add_chat_history:
            history_prompt = get_normal_group_bigmodel_prompt(
                group_name, group_chat_list, white_list, sep='\n',
                answer_source_names=answer_source_names,
                platform=platform,
                identity_lookup=identity_lookup
            ) # 增加聊天历史对话，为了让人知道qa从哪里出来。方便审核
            for qa_info in qa_list:
                qa_info.setdefault('from_chat_history', history_prompt)

        if 'all' in group_type_config:
            qa_list = list(filter(lambda x: x.get('source', 'unknow') not in group_type_config['all'].get('black_group', set()), qa_list)) # 过滤部分答案来源为非专业人士的数据
        all_qa_list.extend(qa_list)
        max_process_time = list(sorted(group_chat_list, key=lambda x: x['message_time']))[-1]['message_time']
        robot_room_process_record.setdefault(robot_name, {})
        robot_room_process_record[robot_name][group_name] = max_process_time
    if run_stats is not None:
        run_stats.update({
            'robot_name': robot_name,
            'groups_seen': len(reorga_chat_dict),
            'groups_eligible': eligible_group_count,
            'groups_succeeded': successful_group_count,
            'groups_failed': len(group_failures),
            'failed_groups': group_failures,
            'qa_count': len(all_qa_list),
            'llm': direct_llm_model.get_stats() if hasattr(direct_llm_model, 'get_stats') else {},
        })
    return all_qa_list


def run_batch_robot_chat_data(data_file, output_dir,
                              robot_room_type_config_file, robot_process_record_file,
                              robot_white_list_file, need_robot_reply=False, data_file_field_num=2, filter_group_name='all', flag='', prompt_file_map=None,
                              mysql_config_file='config/mysql_conn_config.json', llm_stats_file=None):
    """
    批量处理机器人的数据
    """
    robot_room_type_config = load_robot_room_type(robot_room_type_config_file, filter_group_name)

    if os.path.exists(robot_process_record_file):
        robot_process_record = load_3file_dict(robot_process_record_file)
    else:
        robot_process_record = dict()
    robot_white_list_dict = load_white_list_dict(robot_white_list_file)
    logging.info(f'robot_white:\n{robot_white_list_dict}\n')
    identity_lookup = load_contact_identity_lookup(mysql_config_file)
    prompt_file_map_dict = common_utils.load_map_dict(prompt_file_map, k_field=0, value_field=1)
    logging.info(f'prompt_file_map:\n{prompt_file_map}\nprompt_file_map_dict:\n{prompt_file_map_dict}\n')
    robot_stats_list = []
    fatal_errors = []
    fatal_exception = None
    try:
        with open(data_file, encoding='utf8') as f:
            for line in f:
                line = line.strip('\n')
                if not line:
                    continue
                fields = line.split('\t')
                robot_name = fields[0]
                platform = fields[1]
                robot_data_file = fields[data_file_field_num]
                prompt_file = prompt_file_map_dict.get(platform, None)
                if prompt_file:
                    prompt_file = prompt_file.strip()
                logging.info(f'robot_name:{robot_name} platform:{platform} data_file:{robot_data_file} prompt_file:{prompt_file}')
                robot_stats = {'robot_name': robot_name}
                try:
                    qa_list = process_one_robot_group_data(
                        robot_name,
                        robot_data_file,
                        robot_room_type_config,
                        robot_white_list_dict,
                        robot_process_record,
                        prompt_file=prompt_file,
                        client=platform,
                        identity_lookup=identity_lookup,
                        mysql_config_file=mysql_config_file,
                        run_stats=robot_stats
                    )
                except Exception as e:
                    robot_stats['fatal_error'] = {
                        'error_type': type(e).__name__,
                        'error': str(e)[:500],
                    }
                    fatal_errors.append({
                        'robot_name': robot_name,
                        'error_type': type(e).__name__,
                        'error': str(e)[:500],
                    })
                    fatal_exception = e
                    robot_stats_list.append(robot_stats)
                    break
                robot_stats_list.append(robot_stats)
                qa_save_file = f"{output_dir}/{robot_name}_{platform}_json_{flag}.txt"
                with open(qa_save_file, 'w', encoding='utf8') as qa_file:
                    for qa_info in qa_list:
                        qa_file.write(json.dumps(qa_info, ensure_ascii=False) + '\n')
                print(f'{line}\t{qa_save_file}')
    finally:
        write_llm_run_summary(
            llm_stats_file,
            build_llm_run_summary(robot_stats_list, fatal_errors=fatal_errors)
        )

    if fatal_exception is not None:
        raise fatal_exception

    failed_group_count = sum(item.get('groups_failed', 0) for item in robot_stats_list)
    if failed_group_count:
        raise RuntimeError(
            'chat QA group processing failed for %s group(s); task and watermarks must fail' %
            failed_group_count
        )

    save_3file_dict(robot_process_record_file, robot_process_record)


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    import fire
    fire.Fire({
        'run_batch_robot_chat_data': run_batch_robot_chat_data,
        'process_one_robot_group_data': process_one_robot_group_data,
        'build_direct_llm_quality_batch': build_direct_llm_quality_batch,
        'write_quality_bucket_file': write_quality_bucket_file,
    })
