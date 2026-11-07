from kdb.shared.config.private_values import private_value as _private_value
from kdb.mining.generation.builders.knowlege_segment_builder_by_dify import gen_segment_dataset_info
from kdb.integrations.fastgpt.build_dataset_from_api_fastgpt import get_documents_name_set, build_documents, add_segment
from kdb.integrations.fastgpt.build_dataset_from_api_fastgpt import add_one_segment_and_add_indexes
from kdb.shared.text.common_utils import load_map_file
import json
import logging
import sys

def load_dataset_id_map(dataset_info_map_file):
    """
    """
    dataset_id_map = {}
    dataset_platform_index_name_map = {}
    with open(dataset_info_map_file, 'r') as f:
        for line in f:
            fields = line.strip().split('\t')
            if len(fields) == 2:
                platform, dataset_id = fields
                
                platform_index_name = platform
            else:
                platform, platform_index_name, dataset_id = fields
            dataset_id_map[platform] = dataset_id
            dataset_platform_index_name_map[platform] = platform_index_name
            


    return dataset_id_map, dataset_platform_index_name_map
    

def add_segment_to_dataset(segment_info, document_name_dict, dataset_id, api_key, need_rebuild_index=True):
    """
    """
    if need_rebuild_index:
        segment_index_info = gen_segment_dataset_info(segment_info)
    else:
        segment_index_info = segment_info
    document_name = segment_index_info['document_name']
    if document_name not in document_name_dict:
        response = build_documents(document_name, dataset_id, api_key)
        if response is None:
            logging.error('创建文档%s失败', document_name)
            return None
        document_id = response['data']
        document_name_dict[document_name] = document_id
    document_id = document_name_dict[document_name]
    add_segment(document_id, api_key, data=[segment_index_info])
    logging.info('段落数据%s\t段落索引数据%s', json.dumps(segment_info, ensure_ascii=False), json.dumps(segment_index_info, ensure_ascii=False))     
    return True   

def build_segment_dataset(segment_info_file, dataset_id, api_key ):
    """
    """
    document_name_dict = get_documents_name_set(dataset_id, api_key)
    with open(segment_info_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            segment_info = json.loads(line)
            add_segment_to_dataset(segment_info, document_name_dict, dataset_id, api_key)
            
def run_batch_build_segment_dataset(segment_info_file_batch, dataset_id, api_key):
    """
    """

    with open(segment_info_file_batch, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            segment_info_file = fields[-1]
            build_segment_dataset(segment_info_file, dataset_id, api_key)

def batch_add_segment_dataset(local_file_path, dataset_info_map_file, api_key=_private_value('f25bae8d0fc90f905d48e2fd'), start_index=0, need_rebuild_index=True):
    """
    """
    datastid_map, dataset_index_name_map = load_dataset_id_map(dataset_info_map_file)
    datasetid_document_name = {}
    index = 0
    need_rebuild_index = bool(need_rebuild_index)
    with open(local_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            segment_info = json.loads(fields[-1])
            platform = segment_info.get('platform', None)  
            platform_index_name = dataset_index_name_map.get(platform, platform)
            index += 1
            if index < start_index:
                continue
            print('process index: {}'.format(index))
            if not platform:
                continue
            platform_k = f'{platform}_segment'
            dataset_id = datastid_map[platform_k]
            if dataset_id not in datasetid_document_name:
                datasetid_document_name[dataset_id] = get_documents_name_set(dataset_id, api_key)            
            document_name_dict = datasetid_document_name[dataset_id]                
            add_segment_to_dataset(segment_info, document_name_dict, dataset_id, api_key, need_rebuild_index=need_rebuild_index)

def batch_add_qa_dataset(local_file_path, dataset_info_map_file, api_key=_private_value('81d723c8183c8bdc15d41953'), start_index=0, data_from_type='document_mining'):
    """
    """
    datastid_map, dataset_index_name_map = load_dataset_id_map(dataset_info_map_file)
    datasetid_document_name = {}
    index = 0 
    with open(local_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            qa_json = json.loads(fields[-1])
            platform = qa_json.get('platform', None)
            platform_index_name = dataset_index_name_map.get(platform, platform)
            index += 1
            if index < start_index:
                continue
            print('process index: {}'.format(index))
            if not platform:
                continue
            if data_from_type == 'document_mining':
                platform_k = f'{platform}_qa'
            elif data_from_type == 'chat_mining':
                platform_k = f'{platform}_chat'
            dataset_id = datastid_map[platform_k]
            if dataset_id not in datasetid_document_name:
                datasetid_document_name[dataset_id] = get_documents_name_set(dataset_id, api_key)
            document_name = qa_json['document_name']
            if document_name not in datasetid_document_name[dataset_id]:
                response = build_documents(document_name, dataset_id, api_key)
                document_id = response['data']
                datasetid_document_name[dataset_id][document_name] = document_id
            document_id = datasetid_document_name[dataset_id][document_name]
            logging.info(f'add qa dataset: dataset_id: {dataset_id}, document_id: {document_id}, document_name: {document_name}, qa_json: {json.dumps(qa_json, ensure_ascii=False)}')
            add_one_segment_and_add_indexes(dataset_id, document_id, api_key, qa_json['title'], qa_json['content'], platform_index_name)
            
    
    

    

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')      
    import fire
    fire.Fire({
        'run_batch_build_segment_dataset': run_batch_build_segment_dataset,
        'batch_add_qa_dataset': batch_add_qa_dataset,
        'batch_add_segment_dataset': batch_add_segment_dataset,
    })
    