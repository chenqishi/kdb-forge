import copy
import json
import logging
import os

def load_global_config(defaults, project_root):
    """
    加载全局配置。
    优先从 ../config/global_config.json 加载，如果不存在则使用默认配置。
    """
    # 获取当前文件所在目录
    current_dir = str(project_root)
    # 构建配置文件路径：相对于 config_tools 目录的 ../config/global_config.json
    config_file = os.path.join(str(project_root), 'config', 'global_config.json')
    config_file = os.path.normpath(config_file)

    # 先使用默认配置
    config = copy.deepcopy(defaults)

    # 如果外部配置文件存在，则加载并覆盖默认配置
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                external_config = json.load(f)
                # 用外部配置更新默认配置
                config.update(external_config)
                logging.info(f"成功从外部配置文件加载配置: {config_file}")
        except Exception as e:
            logging.warning(f"加载外部配置文件失败，使用默认配置: {config_file}, 错误: {e}")
    else:
        logging.debug(f"外部配置文件不存在，使用默认配置: {config_file}")

    return config
