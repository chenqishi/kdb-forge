import json
import numpy as np
import logging

from kdb.shared.text import common_utils
from kdb.shared.clients import dify_tools
from kdb.shared.config.legacy_config import GLOBAL_CONFIG  


class SimLLMModel(object):
    def __init__(self, api_base: str, api_key: str):
        self.model = dify_tools.DifyWorkFlowRequest(api_base, api_key, 3)
    
    def _build_prompt(self, doc_1, doc_2):
        """构建提示词"""
        prompt = "请处理以下两段文本\n\n"
        doc1_str = ""
        if doc_1.get('title'):
            doc1_str += f"{doc_1['title']}"
        if doc_1.get('content'):
            doc1_str = f'{doc1_str}\n{doc_1["content"]}'
        doc2_str = ""
        if doc_2.get('title'):
            doc2_str += f"{doc_2['title']}"
        if doc_2.get('content'):
            doc2_str = f'{doc2_str}\n{doc_2["content"]}'
        prompt += f"文本1：\n{doc1_str}\n文本2：\n{doc2_str}"
        return prompt

    def _trans_to_num(self, result):
        """将文本结果转换为数字"""
        if not result:
            return 0
        result = result.split('\n')[0]
        if '类别1' in result:
            return 1
        else:
            return 0

    def is_simility_knowledge(self, doc_1, doc_2):
        """
        判断两个知识是否相似
        :param doc_1: 第一个文档
        :param doc_2: 第二个文档
        :return: 1表示相似，0表示不相似
        """
        prompt = self._build_prompt(doc_1, doc_2)
        result = self.model.request_dify(prompt)
        result_num = self._trans_to_num(result)
        logging.debug(f"prompt: {prompt} result: {result} result_num: {result_num}")

        return result_num

class SimilityTools(object):
    def __init__(self, config_path: str=None):
        if config_path:
            self.config = json.load(open(config_path, 'r', encoding='utf-8'))
        else:
            self.config = {}
        if 'simility_dify_api_key' in self.config:
            api_key = self.config['simility_dify_api_key']
            api_base = self.config.get('simility_dify_api_base', GLOBAL_CONFIG['dify_api_base'])
            self.simility_llm_model = SimLLMModel(api_base, api_key)
        else:
            self.simility_llm_model = None
    


    def is_simility_knowledge(self, doc_1, doc_2, is_need_llm=False, is_only_title=False, basic_threshold=0.7, title_basic_threshold=0.95):
        """
        判断两个知识是否相似        
        """
        if doc_1.get('data_type') != doc_2.get('data_type') or\
            doc_1.get('platform') != doc_2.get('platform'):
            return 0
        if 'title_embedding' in doc_1 and 'title_embedding' in doc_2:
            title_sim_score = cosine_similarity(doc_1['title_embedding'], doc_2['title_embedding'])
        elif 'title_embedding' not in doc_1 and 'title_embedding' not in doc_2:
            title_sim_score = -1
        else:
            return 0 
        
        if 'content_embedding' in doc_1 and 'content_embedding' in doc_2:
            content_sim_score = cosine_similarity(doc_1['content_embedding'], doc_2['content_embedding'])
        elif 'content_embedding' not in doc_1 and 'content_embedding' not in doc_2:
            content_sim_score = -1
        else:
            return 0 
        
        max_sim_score = max(title_sim_score, content_sim_score)
        min_sim_score = min(title_sim_score, content_sim_score)
        logging.debug(f"title1: {doc_1.get('title')} content1: {doc_1.get('content')} \n title2: {doc_2.get('title')} content2: {doc_2.get('content')} \n max_sim_score: {max_sim_score} min_sim_score: {min_sim_score}")
        if max_sim_score < basic_threshold:
            return 0 
        #if max_sim_score > 0.95:
        #    return 1
        if is_only_title: # 只考虑标题相似度
            if title_sim_score > title_basic_threshold:
                logging.debug(f"title_sim, title1: {doc_1.get('title')} content1: {doc_1.get('content')} \n title2: {doc_2.get('title')} content2: {doc_2.get('content')} \n is duplicatemin_sim_score: {min_sim_score}")
                return 1
        if min_sim_score > title_basic_threshold:
            logging.debug(f"title1: {doc_1.get('title')} content1: {doc_1.get('content')} \n title2: {doc_2.get('title')} content2: {doc_2.get('content')} \n is duplicatemin_sim_score: {min_sim_score}")
            return 1
        if is_need_llm:
            return self.simility_llm_model.is_simility_knowledge(doc_1, doc_2)
        return 0



def cosine_similarity(vec1, vec2):
    """
    计算两个向量的余弦相似度
    :param vec1: 向量1
    :param vec2: 向量2
    :return: 相似度分数 (0-1之间)
    """
    if isinstance(vec1, list):
        vec1 = np.array(vec1)
    if isinstance(vec2, list):
        vec2 = np.array(vec2)
    
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0
    
    return np.dot(vec1, vec2) / (norm1 * norm2)


