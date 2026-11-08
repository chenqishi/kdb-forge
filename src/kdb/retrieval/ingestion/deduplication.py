from typing import Any
from typing import Dict
from typing import List
import logging

def find_duplicates(self, data: Dict[str, Any], topK: int = 5,
                    is_need_llm: bool = True,
                    index_name: str = None,
                    exclude_self: bool = False,
                    is_only_title: bool = False,
                    basic_threshold: float = 0.7,
                    title_basic_threshold: float = 0.95
                    ) -> List[Dict[str, Any]]:
    """
    查找重复数据
    Args:
        data: 待查重的数据
        topK: 检索返回的候选结果数量
    Returns:
        List[Dict]: 重复数据列表
    """
    # 1. 首先处理输入数据
    processed_data = data.copy()
    if not self.process_one_data(processed_data):
        logging.error("处理待查重数据失败")
        return []

    # 2. 构建检索query
    query = {
        "query": processed_data.get('title', '') + ' ' + processed_data.get('content', ''),
    }

    # 如果有向量，添加向量检索
    if processed_data.get('indexes') and processed_data['indexes'][0].get('embedding'):
        query["vector"] = {
            "value": processed_data['indexes'][0]['embedding']
        }

    # 3. 添加属性过滤
    query["attribute"] = {
        "data_type": processed_data.get('data_type', 'unkonw'),
        "platform": processed_data.get('platform', 'unkonw')
    }

    # 4. 检索相似文档
    candidates = self.search_data(query, size=topK, index_names=index_name)

    # 5. 使用simility_tools进行精确判断
    duplicates = []
    candidate_titles = [candidate.get('title') for candidate in candidates]
    logging.debug(f"candidate_sim_titles: {candidate_titles}")
    for candidate in candidates:
        # 跳过自身
        if candidate.get('_id') == processed_data.get('_id'):
            if not exclude_self: # 如果不排除自身，则该数据为重复数据
                duplicates.append(candidate)
            logging.debug(f"数据{processed_data.get('_id')} 已存在")
            continue

        # 使用simility_tools判断是否相似
        if self.simility_tools.is_simility_knowledge(processed_data, candidate, is_need_llm=is_need_llm,
                                                     is_only_title=is_only_title,
                                                     basic_threshold=basic_threshold,
                                                     title_basic_threshold=title_basic_threshold):
            duplicates.append(candidate)

    return duplicates
