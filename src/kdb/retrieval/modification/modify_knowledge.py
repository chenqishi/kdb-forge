import logging
import json
import traceback
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed

from knowledge_interface_tools.search_index_data_interface import SearchDataInterface
from commons.dify_tools import DifyWorkFlowRequest
import time


from config_tools.config import GLOBAL_CONFIG



def gen_modify_es_qa_knowledge_by_dify_model(search_handle, es_index, dify_model, title, content, search_querys, sub_prompt='', is_need_print=False):
    """
    根据最新知识q(title)，a(content)，检索es知识库中需要改变的数据，并产生最新的数据，使其与最新知识保持一致
    
    Args:
        search_handle: SearchDataInterface对象
        es_index: ES索引名称
        dify_model: DifyWorkFlowRequest对象
        title: 最新知识的标题
        content: 最新知识的内容
        search_querys: 搜索查询列表，如果没有title则使用此参数
    
    Returns:
        List[Dict]: 包含修改结果的文档列表，每个文档包含is_modify(bool)和modify_content字段
    """
    try:
        # 1. 构建搜索查询
        if not title and not search_querys:
            logging.error("title和search_querys都为空，无法进行搜索")
            return []
        
        # 如果有title，使用title作为搜索查询，否则使用search_querys
        if title not in search_querys:
            search_querys.append(title)
        
        
        # 2. 使用search_handle检索ES获取相关文档
        # 参考search_for_audit_data函数的做法
        condition_dicts = [
            {
                "data_type": "qa",
                "audit_result": [1, -1],
                "quality_level": "high"
            },
            {
                "data_type": "qa",
                "audit_result": 1
            }
        ]
        result_dict = {}
        for search_query in search_querys:
            results, doc_num = search_handle.search_data_by_query(
                search_query, 
                index_names=es_index, 
                condition_dicts=condition_dicts, 
                size=40,
                use_synonyms=True
            )
            for doc in results:
                if doc['similarity'] < 0.4:
                    continue
                if doc.get('_id') not in result_dict:
                    result_dict[doc.get('_id')] = doc
        
        results = list(result_dict.values())        
        
        logging.info(f"检索到 {len(results)} 个相关文档")
        
        # 3. 对每个文档调用dify模型判断是否需要修改
        modified_docs = []
        
        for doc in results:
            try:
                # 去除embedding和index相关字段，避免数据过大
                clean_doc = {k: v for k, v in doc.items() 
                           if k not in ['embedding', 'indexes', 'vector']}
                
                # 构建dify模型的输入
                doc_title = clean_doc.get('title', '')
                doc_content = clean_doc.get('content', '')
                
                # 构建inputs参数
                inputs = {
                    'new_title': title,
                    'new_content': content,
                    'old_title': doc_title,
                    'old_content': doc_content
                }
                if sub_prompt:
                    inputs['sub_prompt'] = sub_prompt
                
                # 构建paragraph参数
                paragraph = "请判断原文档是否需要根据最新知识进行修改。" # 暂时没用到
                
                # 调用dify模型
                dify_result = dify_model.request_dify(paragraph, other_inputs=inputs)
                
                if not dify_result:
                    logging.warning(f"dify模型返回空结果，跳过文档: {doc.get('_id', 'unknown')}")
                    continue
                
                # 解析dify返回结果
                dify_result = dify_result.strip()
                if '\t' in dify_result:
                    is_modify_str, modify_content = dify_result.split('\t', 1)
                    
                    # 转换is_modify为bool值
                    is_modify = is_modify_str.strip().lower() in ['是', 'yes', 'true', '1']
                    
                    # 添加修改结果到文档
                    clean_doc['is_modify'] = is_modify
                    clean_doc['modify_content'] = modify_content.strip()                        
                    modified_docs.append(clean_doc)
                else:
                    # 如果没有找到符合格式的结果，使用默认处理
                    logging.warning(f"dify返回结果格式不符合预期: {dify_result}")
                    clean_doc['is_modify'] = False
                    clean_doc['modify_content'] = ''
                    modified_docs.append(clean_doc)
                if is_need_print:
                    print(f'{clean_doc["_id"]}\t{clean_doc["title"]}\t{clean_doc["content"]}\t{clean_doc["is_modify"]}\t{clean_doc["modify_content"]}')
                    
            except Exception as e:
                logging.error(f"处理文档时发生错误: {str(e)}")
                continue
        
        logging.info(f"成功处理 {len(modified_docs)} 个文档")
        return modified_docs
        
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"traceback: {tb}")
        logging.error(f"gen_modify_es_qa_knowledge_by_dify_model函数执行失败: {str(e)}")
        logging.error(f"doc: {doc}")
        return []


def gen_reselect_qa_knowledge_input(qa_infos):
    """
    生成召回提示词
    """
    paragraph = ""
    for index, qa_info in enumerate(qa_infos):
        paragraph += f"{index+1}.问题：{qa_info['title']}\n答案：{qa_info['content']}\n"
    return paragraph



class ModifyKnowledge():
    def __init__(self, search_handle):
        self.search_handle = search_handle
        self.recall_model = DifyWorkFlowRequest(api_base=GLOBAL_CONFIG.get("dify_api_base"), api_key=GLOBAL_CONFIG.get('recall_qa_api_key'))
        self.modify_model = DifyWorkFlowRequest(api_base=GLOBAL_CONFIG.get("dify_api_base"), api_key=GLOBAL_CONFIG.get('modify_qa_api_key'))

    def modify_knowledge(self, es_index, new_query_info, old_query_info, search_querys, write_db_id=None):
        """
        修改知识库中的旧知识，将其改为新知识
        """
        #召回所有相关知识
        search_querys_final = list()
        if search_querys:
            search_querys_final.extend(search_querys)
        if new_query_info.get('title'):
            search_querys_final.append(new_query_info['title'])
        if new_query_info['content']:
            if len(new_query_info['content']) > 1000:
                search_content = new_query_info['content'][:1000]
            else:
                search_content = new_query_info['content']
            search_querys_final.append(search_content)
        #    search_querys_final.append(new_query_info['content'])
        if old_query_info.get('title'):
            search_querys_final.append(old_query_info['title'])
        #if old_query_info['content']:
        #    search_querys_final.append(old_query_info['content'])

        condition_dicts = [
            {
                "data_type": "qa",
                "audit_result": [1, -1],
                "quality_level": "high"
            },
            {
                "data_type": "qa",
                "audit_result": 1
            }
        ]
        result_dict = {}

        results, doc_num = self.search_handle.search_data_by_multi_query(
            search_querys_final, 
            index_names=es_index, 
            condition_dicts=condition_dicts, 
            size=40,
            use_synonyms=True
        )
        for doc in results:
            if doc['similarity'] < 0.4:
                continue
            if doc.get('_id') not in result_dict:
                result_dict[doc.get('_id')] = doc
        
        reselect_qa_knowledge_list = self.reselect_qa_knowledge(list(result_dict.values()), new_query_info)
        modify_qa_infos = self.batch_gen_new_knowledge(reselect_qa_knowledge_list, new_query_info)
        return modify_qa_infos


    def reselect_qa_knowledge(self, qa_knowledge_list, new_qa_info):
        """
        """
        if not qa_knowledge_list:
            return []
        qa_paragraph = gen_reselect_qa_knowledge_input(qa_knowledge_list)
        new_knowledge = f"{new_qa_info['content']}" if not new_qa_info.get('title') else f"问题:{new_qa_info['title']}\n答案:{new_qa_info['content']}"
        recall_model_result = self.recall_model.request_dify(None, other_inputs={'old_qa_knowledge': qa_paragraph, 'new_knowledge': new_knowledge})
        dify_result_split = recall_model_result.split("###")
        final_result = []
        for index, dify_result_split_item in enumerate(dify_result_split):
            if not dify_result_split_item.strip() or len(dify_result_split_item.strip()) < 2:
                continue
            dify_result_split_item_split = dify_result_split_item.strip().split(" ")
            if dify_result_split_item_split[-1] == "0":
                continue
            model_query = dify_result_split_item_split[0]
            model_query = model_query.replace("：", ":").split("问题:")[-1].strip()[2:]
            select_qa_info  = qa_knowledge_list[index]
            if model_query not in select_qa_info['title']:
                continue
            final_result.append(select_qa_info)
        return final_result
        
    def copy_qa_info(self, qa_info):
        """
        拷贝QA信息，忽略所有名称包含'embedding'的key
        
        Args:
            qa_info: 待拷贝的QA信息字典
            
        Returns:
            Dict: 过滤后的QA信息副本
        """
        if not qa_info:
            return {}
        copy_qa_info = {}
        for k, v in qa_info.items():
            if 'embedding' in k.lower():
                continue
            if 'indexes' in k.lower():
                continue
            
            copy_qa_info[k] = v
        return copy_qa_info


    def batch_gen_new_knowledge(self, wait_modify_qa_infos, new_qa_info, max_workers=5):
        """
        并发批量生成新知识
        
        Args:
            wait_modify_qa_infos: 待修改的QA信息列表
            new_qa_info: 新的QA信息
            max_workers: 最大并发数量，默认为5
            
        Returns:
            List[Dict]: 修改后的QA信息列表
        """
        def process_single_qa(wait_qa_info):
            """处理单个QA的内部函数"""
            try:
                input_text = f"问题:{wait_qa_info['title']}\n答案:{wait_qa_info['content']}"
                new_knowledge = self.modify_model.request_dify(
                    None, 
                    other_inputs={'old_qa_knowledge': input_text, 'new_knowledge': new_qa_info['content']}
                )
                if "不需要修改" not in new_knowledge:
                    new_knowledge = new_knowledge.replace("需要修改", "").strip()
                    modify_qa_info = self.copy_qa_info(wait_qa_info)
                    modify_qa_info['content'] = new_knowledge
                    return modify_qa_info
                else:
                    return None
            except Exception as e:
                logging.error(f"处理QA时发生错误: {str(e)}, title: {wait_qa_info.get('title', 'unknown')}")
                # 返回原始信息以保持数据完整性
                return wait_qa_info
        
        modify_qa_infos = []
        
        # 使用线程池并发处理
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_qa = {
                executor.submit(process_single_qa, qa_info): qa_info 
                for qa_info in wait_modify_qa_infos
            }
            
            # 按完成顺序收集结果
            for future in as_completed(future_to_qa):
                try:
                    result = future.result()
                    if result:
                        modify_qa_infos.append(result)
                except Exception as e:
                    qa_info = future_to_qa[future]
                    logging.error(f"获取并发任务结果失败: {str(e)}, title: {qa_info.get('title', 'unknown')}")
                    # 添加原始信息以保持数据完整性
                    #modify_qa_infos.append(qa_info)
        
        return modify_qa_infos


    def write_modify_qa_infos_to_es(self, modify_qa_infos, new_qa_info, es_index, allow_insert=False):
        """
        将修改后的QA信息写入ES
        """
        has_correction = False

        if new_qa_info.get('title'):
            new_qa_info["data_type"] = "qa"
        elif new_qa_info.get('content'):
            new_qa_info["data_type"] = "segment"
        else:
            return False
        data_message = ""
        update_message = ""
        insert_message = ""
        for modify_qa_info in modify_qa_infos:
            multimodal_contents = modify_qa_info.get("multimodal_contents", [])  # 需要更新多模态消息          
            is_all_text = all(c['type'] == 'text' for c in multimodal_contents) if multimodal_contents else True
            if not is_all_text:
                update_message += f"问题:{modify_qa_info['title']}\t答案更新失败，失败原因: 无法更新多媒体消息"
                continue
            
            modify_qa_info["multimodal_contents"] = [{"type":"text", "content": modify_qa_info.get('content', '')}]
            is_sucess, reason = self.search_handle.insert_data(modify_qa_info, check_duplicate=False, index_name=es_index, is_update_data=True) # 都是修改
            if is_sucess:
                update_message += f"问题:{modify_qa_info['title']}\t最新答案:{modify_qa_info['content']}"
                has_correction = True
            else:
                update_message += f"问题:{modify_qa_info['title']}\t答案更新失败，失败原因:{reason}"
            
        time.sleep(1)

        # 仅当allow_insert为True且没有要修改的旧QA时，才允许插入新QA到ES
        if allow_insert and not modify_qa_infos:
            new_qa_info["audit_result"] = 1
            new_qa_info["multimodal_contents"] = [{"type":"text", "content": new_qa_info.get('content', '')}]
            new_qa_info["from_type"] = "handle_chat_modify"
            
            is_sucess, reason = self.search_handle.insert_data(new_qa_info, check_duplicate=True, index_name=es_index, is_update_data=True)        
            if is_sucess:
                insert_message += f"问题:{new_qa_info['title']}\t答案:{new_qa_info['content']}"
                has_correction = True
            else:
                insert_message += f"问题:{new_qa_info['title']}\t答案插入失败，失败原因:{reason}"
        if update_message:
            data_message = f"更新知识如下:\n{update_message}"
        if insert_message:
            data_message = f"{data_message}\n\n插入知识如下:\n{insert_message}"

        data_message = data_message.strip()
        return data_message, has_correction

    def modify_knowledge_direct_update(self, es_index, new_query_info, old_query_info, search_querys, allow_insert=False):
        """
        modify qa direct update
        allow_insert: 当为True时，且没有要修改的旧QA（wait_modify_qa_infos为空），才允许插入新QA到ES
        """
        wait_modify_qa_infos = self.modify_knowledge(es_index, new_query_info, old_query_info, search_querys, None)
        modify_message, has_correction = self.write_modify_qa_infos_to_es(wait_modify_qa_infos, new_query_info, es_index, allow_insert=allow_insert)

        return modify_message, has_correction

        
        

            
            



        

    
def test_modify_knowledge(config_path, es_index, dify_config_path, data_file, output_file):
    """
    测试gen_modify_es_qa_knowledge_by_dify_model函数
    """   
    # 示例配置（需要根据实际情况修改） 
    try:
        dify_config = json.load(open(dify_config_path, 'r'))
        base_url = dify_config.get('base_url')
        dify_api_key = dify_config.get('api_key')
        
        # 初始化SearchDataInterface
        search_handle = SearchDataInterface(config_path=config_path)
        
        # 初始化DifyWorkFlowRequest
        dify_model = DifyWorkFlowRequest(api_base=base_url, api_key=dify_api_key)
        
        # 测试数据
        with open(data_file, 'r') as f, open(output_file, 'w') as f_out:
            for line in f:
                line = line.strip()
                fields = line.split('\t')
                title = fields[0]
                content = fields[1]
                search_querys = fields[2].split('|')
                if len(fields) > 3:
                    sub_prompt = fields[3]
                else:
                    sub_prompt = ''
                results = gen_modify_es_qa_knowledge_by_dify_model(
                    search_handle=search_handle,
                    es_index=es_index,
                    dify_model=dify_model,
                    title=title,
                    content=content,
                    search_querys=search_querys, 
                    sub_prompt=sub_prompt,
                    is_need_print=True
                )
                for doc in results:
                    f_out.write(json.dumps(doc, ensure_ascii=False) + '\n')
                    #print(f'{doc["_id"]}\t{doc["title"]}\t{doc["content"]}\t{doc["is_modify"]}\t{doc["modify_content"]}')
            
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"测试失败: {str(e)}")
        logging.error(f"traceback: {tb}")


def test_modify_knowledge_by_new_qa_info(search_config_path, es_index, data_file, output_file):
    """
    """
    search_handle = SearchDataInterface(config_path=search_config_path)
    modify_knowledge = ModifyKnowledge(search_handle)
    with open(data_file, 'r') as f, open(output_file, 'w') as f_out:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            old_title = fields[0]
            old_content = fields[1]
            new_content = fields[2]
            old_qa_info = {
                'title': old_title,
                'content': old_content
            }
            new_qa_info = {
                'content': new_content
            }
            modify_qa_infos = modify_knowledge.modify_knowledge(es_index, new_qa_info, old_qa_info, search_querys=None, write_db_id=None)
            for modify_qa_info in modify_qa_infos:
                f_out.write(json.dumps(modify_qa_info, ensure_ascii=False) + '\n')

if __name__ == "__main__":
    import logging
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(name)s]: %(message)s'
    )    
    import fire
    fire.Fire()
    

