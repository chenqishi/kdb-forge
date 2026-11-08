from datetime import datetime
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
import kdb.retrieval.application.runtime as runtime_state
import logging
import traceback
logger = logging.getLogger('kdb.entrypoints.http.retrieval.app')

async def update_by_condition_service(index_name: str, update_fields: Dict[str, Any], conditions: List[Dict[str, Any]]) -> tuple[bool, int, str]:
    """
    根据条件更新服务函数
    Args:
        index_name: 索引名称
        update_fields: 要更新的字段和值的映射
        conditions: 查询条件列表
    Returns:
        tuple: (是否成功, 更新的文档数量, 消息)
    """
    try:
        logger.info(f"update_by_condition_service params: index_name={index_name}, update_fields={update_fields}, conditions={conditions}")

        # 调用SearchDataInterface的条件更新方法
        success = runtime_state.SEARCH_DATA_INTERFACE.update_data_value(
            index_name=index_name,
            update_value_dict=update_fields,
            conditions=conditions
        )

        if success:
            message = "条件更新操作完成"
            logger.info(message)
            return True, 0, message
        else:
            message = "条件更新失败"
            logger.error(message)
            return False, 0, message

    except Exception as e:
        tb = traceback.format_exc()
        message = f"条件更新异常: {str(e)}"
        logger.error(message)
        logger.error(f"traceback: {tb}")
        return False, 0, message


async def insert_to_service(_id: Optional[str], title: Optional[str], content: Optional[str],
                          multimodal_contents: Optional[List[Dict[str, Any]]], data_type: Optional[str], from_type: Optional[str],
                          index_names: str, platform: Optional[str], audit_result: Optional[int], del_flag: Optional[int],
                          from_type_norm: Optional[str],
                          tags: Optional[List[str]],
                          dataset: Optional[str],
                          task_id: Optional[str],
                          client: Optional[str],
                          ext_info: Optional[Dict[str, Any]] = None,
                          refresh_imm: bool = False,
                          is_need_llm: bool = None, category_infos: List[Dict[str, Any]] = None,
                          is_update_data: bool = True) -> bool:
    """
    向搜索服务插入数据
    Args:
        title: 标题
        content: 内容
        data_type: 数据类型
        from_type: 来源类型
        index_names: 索引名称
        ext_info: 额外信息
    Returns:
        bool: 插入是否成功
    """
    try:

        insert_data = {
            'insert_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 只添加非None的字段
        if _id is not None:
            insert_data['_id'] = _id
        if title is not None:
            insert_data['title'] = title
        if content is not None:
            insert_data['content'] = content
        if multimodal_contents is not None:
            insert_data['multimodal_contents'] = multimodal_contents
        if data_type is not None:
            insert_data['data_type'] = data_type
        if from_type is not None:
            insert_data['from_type'] = from_type
        if platform is not None:
            insert_data['platform'] = platform
        if audit_result is not None:
            insert_data['audit_result'] = audit_result
        if client is not None:
            insert_data['client'] = client
        if del_flag is not None:
            insert_data['del_flag'] = del_flag
        if tags is not None:
            insert_data['tags'] = tags
        if from_type_norm is not None:
            insert_data['from_type_norm'] = from_type_norm
        if dataset is not None:
            insert_data['dataset'] = dataset
        if task_id is not None:
            insert_data['task_id'] = task_id
        if category_infos is not None:
            insert_data['category_infos'] = category_infos
        if ext_info is not None:
            insert_data['ext_info'] = ext_info


        filter_insert_data = insert_data
        logging.info(f"filter insert data: {filter_insert_data}")

        success, message = runtime_state.SEARCH_DATA_INTERFACE.insert_data(filter_insert_data, index_name=index_names, check_duplicate=True, is_update_data=is_update_data, refresh_imm=refresh_imm, is_need_llm=is_need_llm)
        logger.info(f"insert data: {insert_data}, index_names: {index_names}, success: {success}, message: {message}")
        if success:
            logger.info(f"成功插入数据: title={title}, index={index_names}")
        else:
            logger.error(f"插入数据失败: title={title}, index={index_names}, message: {message}")
        return success, message

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"插入数据异常: {str(e)}")
        logger.error(f"traceback: {tb}")
        return False, str(e)
