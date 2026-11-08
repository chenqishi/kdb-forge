import logging
import sys

def _setup_logging(self):
    """设置日志"""
    # 清除现有的handler，避免重复配置
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # 配置日志输出到标准输出，这样会被任务日志文件捕获
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)  # 确保输出到stdout
        ],
        force=True  # 强制重新配置
    )
