import json
import os

LLM_STAT_TOTAL_KEYS = (
    'logical_requests',
    'http_attempts',
    'successful_requests',
    'failed_requests',
    'timeout_attempts',
    'non_200_attempts',
    'response_format_fallbacks',
    'prompt_chars',
    'completion_chars',
    'prompt_tokens',
    'completion_tokens',
    'total_tokens',
    'elapsed_seconds',
)


def build_llm_run_summary(robot_stats_list, fatal_errors=None):
    totals = {
        'robots': len(robot_stats_list),
        'groups_seen': 0,
        'groups_eligible': 0,
        'groups_succeeded': 0,
        'groups_failed': 0,
        'qa_count': 0,
    }
    totals.update({key: 0 for key in LLM_STAT_TOTAL_KEYS})
    for robot_stats in robot_stats_list:
        for key in (
            'groups_seen', 'groups_eligible', 'groups_succeeded',
            'groups_failed', 'qa_count'
        ):
            totals[key] += robot_stats.get(key, 0) or 0
        llm_stats = robot_stats.get('llm') or {}
        for key in LLM_STAT_TOTAL_KEYS:
            totals[key] += llm_stats.get(key, 0) or 0
    totals['elapsed_seconds'] = round(totals['elapsed_seconds'], 3)
    return {
        'schema_version': 1,
        'totals': totals,
        'robots': robot_stats_list,
        'fatal_errors': fatal_errors or [],
    }


def write_llm_run_summary(llm_stats_file, summary):
    if not llm_stats_file:
        return
    stats_dir = os.path.dirname(llm_stats_file)
    if stats_dir:
        os.makedirs(stats_dir, exist_ok=True)
    temp_file = llm_stats_file + '.tmp'
    with open(temp_file, 'w', encoding='utf8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temp_file, llm_stats_file)
