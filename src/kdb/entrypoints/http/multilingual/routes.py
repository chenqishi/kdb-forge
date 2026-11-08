from kdb.multilingual.detection import detect_language
from flask import jsonify
from flask import request
import kdb.multilingual.runtime as runtime_state
import logging
import traceback
logger = logging.getLogger('kdb.entrypoints.http.multilingual.app')

def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'model_loaded': runtime_state.model is not None
    })


def predict_language():
    """
    预测文本语言
    
    请求参数:
        text: 需要识别语言的文本
    
    返回:
        lang: 识别出的语言名称
        confidence: 置信度
    """
    try:
        # 检查模型是否已加载
        if runtime_state.model is None:
            return jsonify({
                'error': '模型未加载'
            }), 500

        # 获取请求参数
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({
                'error': '缺少必需参数: text'
            }), 400

        text = data['text']

        if text:
            text = text.replace('\n', ' ').strip()

        # 检查文本是否为空
        if not text or not text.strip():
            return jsonify({
                'error': '文本不能为空'
            }), 400

        return jsonify(detect_language(text))

    except Exception as e:
        logger.error(f"预测失败: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': f'预测失败: {str(e)}'
        }), 500


def register_routes(app):
    """Register the original handlers on the single entrypoint app."""
    app.route('/health', methods=['GET'])(health_check)
    app.route('/lang_predict', methods=['POST'])(predict_language)
