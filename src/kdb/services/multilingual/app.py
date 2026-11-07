from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT, resource_path as _resource_path
#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-01-01

多语言识别服务
基于 fastText 的语言识别模型，提供文本语言预测服务
"""
import sys
import os
import json
import logging

from flask import Flask, request, jsonify
import fasttext
import traceback

# 添加项目根目录到sys.path


app = Flask(__name__)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
           '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
)

logger = logging.getLogger(__name__)

# 全局变量
model = None

# 语言代码映射表，将 fastText 的标签转换为完整的语言名称
LANGUAGE_MAP = {
    'af': 'afrikaans',
    'als': 'albanian',
    'am': 'amharic',
    'an': 'aragonese',
    'ar': 'arabic',
    'arz': 'egyptian_arabic',
    'as': 'assamese',
    'ast': 'asturian',
    'av': 'avaric',
    'az': 'azerbaijani',
    'azb': 'south_azerbaijani',
    'ba': 'bashkir',
    'bar': 'bavarian',
    'bcl': 'central_bikol',
    'be': 'belarusian',
    'bg': 'bulgarian',
    'bh': 'bihari',
    'bn': 'bengali',
    'bo': 'tibetan',
    'bpy': 'bishnupriya',
    'br': 'breton',
    'bs': 'bosnian',
    'bxr': 'buryat',
    'ca': 'catalan',
    'cbk': 'chavacano',
    'ce': 'chechen',
    'ceb': 'cebuano',
    'ckb': 'kurdish',
    'co': 'corsican',
    'cs': 'czech',
    'cv': 'chuvash',
    'cy': 'welsh',
    'da': 'danish',
    'de': 'german',
    'diq': 'dimli',
    'dsb': 'lower_sorbian',
    'dty': 'doteli',
    'dv': 'maldivian',
    'el': 'greek',
    'eml': 'emilian_romagnol',
    'en': 'english',
    'eo': 'esperanto',
    'es': 'spanish',
    'et': 'estonian',
    'eu': 'basque',
    'fa': 'persian',
    'fi': 'finnish',
    'fr': 'french',
    'frr': 'northern_frisian',
    'fy': 'western_frisian',
    'ga': 'irish',
    'gd': 'scottish_gaelic',
    'gl': 'galician',
    'gn': 'guarani',
    'gom': 'goan_konkani',
    'gu': 'gujarati',
    'gv': 'manx',
    'he': 'hebrew',
    'hi': 'hindi',
    'hif': 'fiji_hindi',
    'hr': 'croatian',
    'hsb': 'upper_sorbian',
    'ht': 'haitian',
    'hu': 'hungarian',
    'hy': 'armenian',
    'ia': 'interlingua',
    'id': 'indonesian',
    'ie': 'interlingue',
    'ilo': 'iloko',
    'io': 'ido',
    'is': 'icelandic',
    'it': 'italian',
    'ja': 'japanese',
    'jbo': 'lojban',
    'jv': 'javanese',
    'ka': 'georgian',
    'kk': 'kazakh',
    'km': 'khmer',
    'kn': 'kannada',
    'ko': 'korean',
    'krc': 'karachay_balkar',
    'ku': 'kurdish',
    'kv': 'komi',
    'kw': 'cornish',
    'ky': 'kyrgyz',
    'la': 'latin',
    'lb': 'luxembourgish',
    'lez': 'lezghian',
    'li': 'limburgish',
    'lmo': 'lombard',
    'lo': 'lao',
    'lrc': 'northern_luri',
    'lt': 'lithuanian',
    'lv': 'latvian',
    'mai': 'maithili',
    'mg': 'malagasy',
    'mhr': 'meadow_mari',
    'min': 'minangkabau',
    'mk': 'macedonian',
    'ml': 'malayalam',
    'mn': 'mongolian',
    'mr': 'marathi',
    'mrj': 'hill_mari',
    'ms': 'malay',
    'mt': 'maltese',
    'mwl': 'mirandese',
    'my': 'burmese',
    'myv': 'erzya',
    'mzn': 'mazanderani',
    'nah': 'nahuatl',
    'nap': 'neapolitan',
    'nds': 'low_german',
    'ne': 'nepali',
    'new': 'newari',
    'nl': 'dutch',
    'nn': 'norwegian_nynorsk',
    'no': 'norwegian',
    'oc': 'occitan',
    'or': 'oriya',
    'os': 'ossetic',
    'pa': 'punjabi',
    'pam': 'pampanga',
    'pfl': 'palatine_german',
    'pl': 'polish',
    'pms': 'piedmontese',
    'pnb': 'western_punjabi',
    'ps': 'pashto',
    'pt': 'portuguese',
    'qu': 'quechua',
    'rm': 'romansh',
    'ro': 'romanian',
    'ru': 'russian',
    'rue': 'rusyn',
    'sa': 'sanskrit',
    'sah': 'sakha',
    'sc': 'sardinian',
    'scn': 'sicilian',
    'sco': 'scots',
    'sd': 'sindhi',
    'sh': 'serbo_croatian',
    'si': 'sinhala',
    'sk': 'slovak',
    'sl': 'slovenian',
    'so': 'somali',
    'sq': 'albanian',
    'sr': 'serbian',
    'su': 'sundanese',
    'sv': 'swedish',
    'sw': 'swahili',
    'ta': 'tamil',
    'te': 'telugu',
    'tg': 'tajik',
    'th': 'thai',
    'tk': 'turkmen',
    'tl': 'tagalog',
    'tr': 'turkish',
    'tt': 'tatar',
    'tyv': 'tuvinian',
    'ug': 'uyghur',
    'uk': 'ukrainian',
    'ur': 'urdu',
    'uz': 'uzbek',
    'vec': 'venetian',
    'vep': 'veps',
    'vi': 'vietnamese',
    'vls': 'west_flemish',
    'vo': 'volapuk',
    'wa': 'walloon',
    'war': 'waray',
    'wuu': 'wu_chinese',
    'xal': 'kalmyk',
    'xmf': 'mingrelian',
    'yi': 'yiddish',
    'yo': 'yoruba',
    'yue': 'cantonese',
    'zh': 'chinese',
}


def load_model(model_path):
    """加载 fastText 语言识别模型"""
    global model
    try:
        logger.info(f"正在加载语言识别模型: {model_path}")
        # 禁用 fastText 的警告信息
        fasttext.FastText.eprint = lambda x: None
        model = fasttext.load_model(model_path)
        logger.info("模型加载成功")
        return True
    except Exception as e:
        logger.error(f"模型加载失败: {str(e)}")
        logger.error(traceback.format_exc())
        return False


def convert_label_to_language(label):
    """将 fastText 的标签（如 __label__ja）转换为语言名称"""
    # 移除 __label__ 前缀
    code = label.replace('__label__', '')
    # 从映射表中获取语言名称，如果没有则返回代码本身
    return LANGUAGE_MAP.get(code, code)


def has_hiragana_or_katakana(text):
    """检测文本是否包含日文假名（ひらがな、カタカナ）"""
    # ひらがな（平假名）: \u3040-\u309F
    # カタカナ（片假名）: \u30A0-\u30FF
    for char in text:
        if '\u3040' <= char <= '\u309F' or '\u30A0' <= char <= '\u30FF':
            return True
    return False


def has_hangul(text):
    """检测文本是否包含韩文（Hangul）"""
    # Hangul: \uAC00-\uD7AF
    for char in text:
        if '\uAC00' <= char <= '\uD7AF':
            return True
    return False


def mostly_cjk(text):
    """检测文本是否80%以上是汉字（CJK）"""
    if not text:
        return False
    
    # CJK统一汉字范围: \u4E00-\u9FFF
    # CJK扩展A区: \u3400-\u4DBF
    cjk_count = 0
    total_chars = 0
    
    for char in text:
        # 统计所有字符（包括空格、标点等）
        total_chars += 1
        # 检查是否是CJK字符
        if '\u4E00' <= char <= '\u9FFF' or '\u3400' <= char <= '\u4DBF':
            cjk_count += 1
    
    if total_chars == 0:
        return False
    
    # 计算CJK字符占比
    cjk_ratio = cjk_count / total_chars
    return cjk_ratio >= 0.8


def rule_based_language_detection(text):
    """
    基于规则的语言检测
    返回: (label, confidence) 或 None（如果规则无法判断）
    label格式: __label__xx
    """
    # 若文本够长，则不进行规则判断，因为模型判断会更准确
    if len(text) > 100:
        return None
    # 规则1: 如果包含日文假名，判断为日语
    if has_hiragana_or_katakana(text):
        logger.info(f"规则判断: 检测到日文假名，判断为日语")
        return ('__label__ja', 1.0)
    
    # 规则2: 如果包含韩文，判断为韩语
    if has_hangul(text):
        logger.info(f"规则判断: 检测到韩文，判断为韩语")
        return ('__label__ko', 1.0)
    
    # 规则3: 如果80%以上是CJK且没有日文假名和韩文，判断为中文
    if mostly_cjk(text):
        logger.info(f"规则判断: 检测到80%以上CJK字符，判断为中文")
        return ('__label__zh', 1.0)
    
    # 规则无法判断，返回None
    return None


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'model_loaded': model is not None
    })


@app.route('/lang_predict', methods=['POST'])
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
        if model is None:
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
        
        # 先使用规则判断
        rule_result = rule_based_language_detection(text)
        
        if rule_result:
            # 规则判断成功，使用规则结果
            label, confidence = rule_result
            logger.info(f"规则判断结果 - 文本: '{text[:50]}', label: {label}, 置信度: {confidence:.4f}")
        else:
            # 规则无法判断，使用 fastText 模型
            predictions = model.predict(text, k=1)
            label = predictions[0][0]
            confidence = float(predictions[1][0])
            logger.info(f"fastText预测结果 - 文本: '{text[:50]}', label: {label}, 置信度: {confidence:.4f}")
        
        # 统一转换标签为语言名称
        language = convert_label_to_language(label)
        logger.info(f"最终结果 - 文本: '{text[:50]}', 语言: {language}, 置信度: {confidence:.4f}")
        
        return jsonify({
            'lang': language,
            'confidence': confidence,
            'label': label
        })
        
    except Exception as e:
        logger.error(f"预测失败: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': f'预测失败: {str(e)}'
        }), 500


def parse_args():
    """解析命令行参数"""
    import argparse
    parser = argparse.ArgumentParser(description='多语言识别服务')
    parser.add_argument('--port', 
                       type=int,
                       help='服务端口号',  
                       default=8007)
    parser.add_argument('--host',
                       help='服务监听地址',
                       default='0.0.0.0')
    parser.add_argument('--model_path',
                       help='fastText 模型文件路径',
                       default=None)

    return parser.parse_args()


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
