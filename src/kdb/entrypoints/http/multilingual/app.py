from flask import Flask
from kdb.entrypoints.http.multilingual.bootstrap import parse_args
from kdb.entrypoints.http.multilingual.routes import register_routes
from kdb.multilingual.model import load_model
from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
from kdb.shared.config.paths import resource_path as _resource_path
import logging
import os
import sys
logger = logging.getLogger('kdb.entrypoints.http.multilingual.app')

app = Flask(__name__)


"""
Authors: qishichen(263436967@qq.com)
Date: 2024-01-01

多语言识别服务
基于 fastText 的语言识别模型，提供文本语言预测服务
"""


logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
           '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
)


register_routes(app)


if __name__ == '__main__':
    # 解析命令行参数
    args = parse_args()

    # 确定模型路径
    if args.model_path:
        model_path = args.model_path
    else:
        # 默认使用项目中的模型
        project_root = str(_PROJECT_ROOT)
        model_path = str(_resource_path('models', 'lid.176.ftz'))

    # 检查模型文件是否存在
    if not os.path.exists(model_path):
        logger.error(f"模型文件不存在: {model_path}")
        sys.exit(1)

    # 加载模型
    if not load_model(model_path):
        logger.error("无法启动服务：模型加载失败")
        sys.exit(1)

    # 启动 Flask 服务
    logger.info(f"启动多语言识别服务 - {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
