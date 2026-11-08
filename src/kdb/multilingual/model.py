import fasttext
import kdb.multilingual.runtime as runtime_state
import logging
import traceback
logger = logging.getLogger('kdb.entrypoints.http.multilingual.app')

def load_model(model_path):
    """加载 fastText 语言识别模型"""

    try:
        logger.info(f"正在加载语言识别模型: {model_path}")
        # 禁用 fastText 的警告信息
        fasttext.FastText.eprint = lambda x: None
        runtime_state.model = fasttext.load_model(model_path)
        logger.info("模型加载成功")
        return True
    except Exception as e:
        logger.error(f"模型加载失败: {str(e)}")
        logger.error(traceback.format_exc())
        return False
