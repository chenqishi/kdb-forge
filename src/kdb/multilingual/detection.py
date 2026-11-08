from kdb.multilingual.labels import convert_label_to_language
from kdb.multilingual.rules import rule_based_language_detection
import kdb.multilingual.runtime as runtime_state
import logging

logger = logging.getLogger('kdb.entrypoints.http.multilingual.app')


def detect_language(text):
    # 先使用规则判断
    rule_result = rule_based_language_detection(text)

    if rule_result:
        # 规则判断成功，使用规则结果
        label, confidence = rule_result
        logger.info(f"规则判断结果 - 文本: '{text[:50]}', label: {label}, 置信度: {confidence:.4f}")
    else:
        # 规则无法判断，使用 fastText 模型
        predictions = runtime_state.model.predict(text, k=1)
        label = predictions[0][0]
        confidence = float(predictions[1][0])
        logger.info(f"fastText预测结果 - 文本: '{text[:50]}', label: {label}, 置信度: {confidence:.4f}")

    # 统一转换标签为语言名称
    language = convert_label_to_language(label)
    logger.info(f"最终结果 - 文本: '{text[:50]}', 语言: {language}, 置信度: {confidence:.4f}")

    return {'lang': language, 'confidence': confidence, 'label': label}
