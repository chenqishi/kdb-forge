from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
from kdb.shared.config.paths import source_path as _source_path
import kdb.mining.tasks.state as runtime_state
import logging
import os

def init_script_base_dir(provided_dir=None):
    """初始化脚本基础目录"""

    if provided_dir:
        # 使用提供的目录路径
        runtime_state.script_base_dir = os.path.abspath(provided_dir)
    else:
        # 默认使用当前服务脚本的上级目录
        runtime_state.script_base_dir = str(_PROJECT_ROOT)

    logging.info(f"脚本基础目录设置为: {runtime_state.script_base_dir}")

    # 检查脚本目录是否存在
    script_dir = str(_source_path('kdb', 'entrypoints', 'cli', 'mining'))
    if not os.path.exists(script_dir):
        logging.warning(f"脚本目录不存在: {script_dir}")
    else:
        logging.info(f"脚本目录确认存在: {script_dir}")
