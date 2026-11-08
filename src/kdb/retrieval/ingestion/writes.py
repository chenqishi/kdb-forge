from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Union
import copy
import logging

def insert_data(self, data: Dict[str, Any], check_duplicate: bool = None,
                index_name: str = None,
                is_update_data: bool = False,
                is_only_title: bool = False,
                basic_threshold: float = 0.7,
                title_basic_threshold: float = 0.95,
                refresh_imm: bool = False,
                is_need_llm: bool = None
                ) -> bool:
    """
    插入数据到检索库
    Args:
        data: 待插入的数据
        check_duplicate: 是否检查重复
        is_only_title: 是否只考虑标题相似度
        is_update_data: 若为True，查重发现重复数据时，将重复数据的del_flag设置为1并增加del_reason="cover_by_new"，然后插入新数据；若为False，发现重复则跳过插入
    Returns:
        bool: 插入是否成功
    """
    if check_duplicate is None:
        check_duplicate = self.check_duplicate
    #origin_id = data.get('_id')
    ori_data = data
    data = copy.deepcopy(data)
    # 方便打日志
    if not ori_data.get('_id'):
        ori_data['_id'] = data.get('_id')
    #logging.info(f"before process_one_data, data_id: {data.get('_id')}")
    # 处理数据

    if not self.process_one_data(data, index_name=index_name):
        return (False, '数据处理失败')

    is_need_llm = self.is_need_llm if is_need_llm is None else is_need_llm
    # 检查重复
    if check_duplicate:
        duplicates = self.find_duplicates(data, is_need_llm=is_need_llm, index_name=index_name,
                                          exclude_self=True,  # 现在改为都是更新数据，默认插入人保持正确
                                          is_only_title=is_only_title,
                                          basic_threshold=basic_threshold,
                                          title_basic_threshold=title_basic_threshold)
        if duplicates:
            duplicates_ids = [dup['_id'] for dup in duplicates]
            if is_update_data:
                # 将重复数据软删除：设置del_flag=1, del_reason="cover_by_new"
                try:
                    self.engine.update_value(
                        index_name=index_name,
                        update_value_dict={'del_flag': 1, 'del_reason': f'cover_by_new {data.get("_id")}'},
                        conditions=[{'_id': duplicates_ids}]
                    )
                    logging.info(f"数据{data['_id']}覆盖重复数据, title:{data.get('title')}，已软删除重复数据ID: {duplicates_ids}")
                except Exception as e:
                    logging.error(f"软删除重复数据失败: {str(e)}, 重复数据ID: {duplicates_ids}")
            else:
                logging.warning(f"数据{data['_id']}重复, title:{data.get('title')}，跳过插入，重复数据ID: {duplicates_ids}")
                return (False, '数据重复')

    #logging.info(f"ready to insert data: {data}, index_name: {index_name}")
    #if origin_id:
    #    return self.engine.update(origin_id, data, index_names=index_name)


    return (self.engine.insert(data, index_names=index_name, refresh_imm=refresh_imm), '')


def batch_insert_data(self, data_list: List[Dict[str, Any]],
                     check_duplicate: bool = True) -> List[bool]:
    """
    批量插入数据
    Args:
        data_list: 待插入的数据列表
        check_duplicate: 是否检查重复
    Returns:
        List[bool]: 每条数据插入是否成功的结果列表
    """
    results = []
    for data in data_list:
        results.append(self.insert_data(data, check_duplicate))
    return results


def update_data(self, data_id: str, data: Dict[str, Any]) -> bool:
    """
    更新数据
    Args:
        data_id: 数据ID
        data: 更新的数据内容
    Returns:
        bool: 更新是否成功
    """
    return self.engine.update(data_id, data)


def delete_data(self, data_id: str, index_names: Optional[Union[str, List[str]]] = None, refresh: bool = False) -> bool:
    """
    删除数据
    Args:
        data_id: 数据ID
        index_names: 索引名称
        refresh: 是否立即刷新使删除立即生效
    Returns:
        bool: 删除是否成功
    """

    return self.engine.delete(data_id, index_names=index_names, refresh=refresh)


def update_data_value(self, index_name: str, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]]) -> bool:
    """
    更新数据
    """
    return self.engine.update_value(index_name, update_value_dict, conditions)
