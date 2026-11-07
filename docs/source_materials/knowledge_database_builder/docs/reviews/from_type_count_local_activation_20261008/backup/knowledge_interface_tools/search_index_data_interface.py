from gettext import install
import json
import hashlib
import copy
import os
import re
import time
from typing import Dict, Any, List, Tuple, Optional, Union, Protocol

from pydantic import InstanceOf
from commons.embedding_tools import AliEmbedding as EmbeddingTools
from knowledge_interface_tools.es_search_interface import EsSearchInterface
from commons import simility_tools
from commons.simility_tools import cosine_similarity
from commons.keywords_tools import gen_keyword_by_title_content
from knowledge_interface_tools.knowledge_tools import (get_from_norm_type,
                                                       build_default_category_infos,
                                                       build_default_primary_category)
import logging
from datetime import datetime
import traceback
import requests
from urllib.parse import quote
from commons.common_utils import clear_none_value
logger = logging.getLogger(__name__)



def gen_data_id(data: Dict[str, Any]) -> str:
    """
    生成数据的唯一ID，使用title、content和data_type的组合进行MD5计算
    Args:
        data: 输入的数据字典
    Returns:
        str: 生成的唯一ID
    """
    # 获取字段值，不存在则使用空字符串
    title = data.get('title', '')
    content = data.get('content', '')
    data_type = data.get('data_type', '')
    
    # 组合字符串并计算MD5
    id_str = f"{title}_{content}_{data_type}"
    return hashlib.md5(id_str.encode('utf-8')).hexdigest()

class SearchEngine(Protocol):
    """检索引擎接口协议，定义了检索引擎需要实现的基本方法"""
    def insert(self, data: Dict[str, Any], index_name: str = None) -> bool: ...
    def update(self, data_id: str, data: Dict[str, Any], index_name: str = None) -> bool: ...
    def delete(self, data_id: str, index_name: str = None) -> bool: ...
    def search(self, query: Dict[str, Any], size: Optional[int] = None, index_name: str = None) -> List[Dict[str, Any]]: ...
    def search_multi(self, query: Dict[str, Any], index_names: Optional[Union[str, List[str]]] = None, size: int = 10, page_num: int = 1) -> Tuple[List[Dict[str, Any]], int]: ...
    def search_multi_by_page(self, query: Dict[str, Any], index_names: Optional[Union[str, List[str]]] = None, size: int = 10, page_num: int = 1) -> Tuple[List[Dict[str, Any]], int]: ...
    def get(self, data_id: str, index_name: str = None) -> Optional[Dict[str, Any]]: ...

class SearchDataInterface(object):
    """检索数据接口类，用于管理检索库的数据操作"""
    
    def __init__(self, search_engine: SearchEngine=None, config_path: str=None, **kwargs):
        """
        初始化接口
        Args:
            search_engine: 实现了基本检索操作的搜索引擎实例
        """
        config = json.load(open(config_path, 'r', encoding='utf-8'))
        if not search_engine:
            search_engine = self.load_search_engine(config.get('search_engine_config_path', ''), **kwargs)
        self.simility_tools = simility_tools.SimilityTools(config.get('simility_config_path', ''))
        self.engine = search_engine
        self.embedding_tools = EmbeddingTools(config.get('embedding_config_path', ''))
        self.is_need_llm = config.get('is_need_llm', False)
        self.check_duplicate = config.get('check_duplicate', True)
        self.all_client_category_dict = {}
        self.category_service_url = config.get('category_service_url', '')
        
        self.category_update_time_interval = config.get('category_update_time_interval', 36000)
        self.category_update_time_dict = {} # 记录每个client的类目字典更新时间
        self.doc_schema_field = {
                'title', 'synonyms_title', 'content', 'data_type', 'platform',
                'audit_result', 'quality_level', 'keywords', 'tags', 'indexes',
                'insert_time', 'update_time', 'from_type', 'ext_info', '_id',
                'title_embedding', 'content_embedding', 'image_indexes', 'del_flag', 'from_type_norm', 'category_infos', "client", 'primary_category', 'dataset',
                'task_id', 'flag', 'multimodal_contents', 'index_name'   # 将embedding字段加入schema
            }
        self.multimodal_prefix = config.get('multimodal_prefix', '')
        
        # 如果配置中包含client，则初始化加载该client的类目字典
        if config.get('client'):
            self.load_category_map_dict(config['client'])

    def load_search_engine(self, config_path: str, **kwargs) -> SearchEngine:
        """
        加载搜索引擎
        Args:
            config_path: 搜索引擎配置文件路径
            **kwargs: 其他参数
        Returns:
            SearchEngine: 搜索引擎实例
        """
        # EsSearchInterface需要的参数列表
        es_params = [
            'hosts',
            'index_name',
            'username',
            'password',
            'vector_fields'
        ]
        
        # 从kwargs中提取ES相关参数
        es_kwargs = {
            key: kwargs.pop(key) 
            for key in es_params 
            if key in kwargs
        }
        
        # 如果提供了config_path，添加到参数中
        if config_path:
            es_kwargs['config_path'] = config_path
        
        # 其他未被提取的kwargs参数会作为extra_params传入
        if kwargs:
            es_kwargs['extra_params'] = kwargs
        
        return EsSearchInterface(**es_kwargs)

    def load_category_map_dict(self, client: str, user=None) -> Dict[str, Any]:
        """
        加载类目字典
        Args:
            client: 客户端标识
            user: 用户标识(可选)
        Returns:
            Dict[str, Any]: 类目字典，包含name_map_dict和id_map_dict
        """
        try:
            if client in self.category_update_time_dict and time.time() - self.category_update_time_dict[client] < self.category_update_time_interval:
                return 
            if not self.category_service_url:
                return 

            # 构造请求参数（GET 请求通过 URL 参数传递）
            params = {"client": client}
            if user:
                params["user"] = user
            
            # 发送 GET 请求获取类目数据
            # 示例: GET http://127.0.0.1:8166/rufit-ai/intranet/knowledge/qaCategory/tree?client=rufit_demo
            response = requests.get(self.category_service_url, params=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
            # 检查响应状态
            if response.status_code != 200:
                logging.error(f"获取类目数据失败: {result.get('message', '未知错误')}")
                return {'name_map_dict': {}, 'id_map_dict': {}}
            
            # 获取类目数据
            category_data = result.get('data', [])
            
            # 构造反映射字典
            leaf_category_map_dict = {
                'name_map_dict': {},
                'id_map_dict': {}
            }
            
            def traverse_category(node: Dict[str, Any], parent_chain: List[Dict[str, Any]]):
                """
                递归遍历类目树，构造反映射字典
                Args:
                    node: 当前类目节点
                    parent_chain: 父节点链(包含所有祖先节点的信息，不包含当前节点)
                """
                # 获取当前节点信息
                category_id = node.get('categoryId')
                category_name = node.get('categoryName')
                level = node.get('level', 0)
                
                # 构建当前节点的信息
                current_info = {
                    'category_name': category_name,
                    'category_id': category_id,
                    'level': level
                }
                
                # 构造包含当前节点的完整链（parent_chain + 当前节点）
                current_chain = parent_chain + [current_info]
                
                # 将当前节点及其完整链添加到字典中
                # current_chain 包含从根节点到当前节点的完整路径（包含自己）
                
                # name_map_dict 的 key 使用全路径（用"-"连接）
                if category_name:
                    category_path = '-'.join([n['category_name'] for n in current_chain])
                    leaf_category_map_dict['name_map_dict'][category_path] = current_chain
                
                # id_map_dict 的 key 仍然使用单一的 ID
                if category_id:
                    leaf_category_map_dict['id_map_dict'][category_id] = current_chain
                
                # 获取子节点
                children = node.get('children', [])
                
                # 递归处理所有子节点
                for child in children:
                    traverse_category(child, current_chain)
            
            # 遍历所有顶层类目
            for category in category_data:
                traverse_category(category, [])
            
            logging.info(f"成功加载client={client}的类目字典，"
                        f"name_map共{len(leaf_category_map_dict['name_map_dict'])}项，"
                        f"id_map共{len(leaf_category_map_dict['id_map_dict'])}项")
            self.category_update_time_dict[client] = time.time()
            self.all_client_category_dict[client] = leaf_category_map_dict
            return True
            
        except requests.RequestException as e:
            logging.error(f"请求类目服务失败: {str(e)}")
            return 
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"加载类目字典失败: {tb}")
            return 


    def map_cate_name_to_id(self, client, category_name):
        """
        """
        if category_name not in self.all_client_category_dict.get(client, {}).get('name_map_dict', {}):
            self.load_category_map_dict(client)
        nodes = self.all_client_category_dict.get(client, {}).get('name_map_dict', {}).get(category_name, [])
        if nodes:
            return nodes[-1]['category_id']
        return None

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
    
    def get_category_parent_chain(self, client: str, cate_id: str=None, cate_name: str=None) -> List[Dict[str, Any]]:
        """
        获取类目父节点链
        Args:
            client: 客户端标识
            cate_id: 类目ID
        Returns:
            List[Dict[str, Any]]: 类目父节点链
        """
        parent_chain = []
        if not cate_id and not cate_name:
            return parent_chain
        if cate_id:
            parent_chain = self.all_client_category_dict.get(client, {}).get('id_map_dict', {}).get(cate_id, [])
        elif cate_name:
            parent_chain = self.all_client_category_dict.get(client, {}).get('name_map_dict', {}).get(cate_name, [])
        if parent_chain:
            return parent_chain
        self.load_category_map_dict(client) # 允许进行一次加载
        if cate_id:
            parent_chain = self.all_client_category_dict.get(client, {}).get('id_map_dict', {}).get(cate_id, [])
        elif cate_name:
            parent_chain = self.all_client_category_dict.get(client, {}).get('name_map_dict', {}).get(cate_name, [])
        if parent_chain:
            return parent_chain
        return []

    @staticmethod
    def _category_name_occurs(text: str, category_name: str) -> bool:
        """在自然语言里匹配类目名；短英文名必须有词边界，避免 Bol 命中 symbol。"""
        text = str(text or '')
        category_name = str(category_name or '').strip()
        if not text or not category_name:
            return False
        if re.fullmatch(r'[A-Za-z0-9 .&/()_-]+', category_name):
            return re.search(
                rf'(?<![A-Za-z0-9]){re.escape(category_name)}(?![A-Za-z0-9])',
                text,
                flags=re.I,
            ) is not None
        return category_name.casefold() in text.casefold()

    def infer_payoneer_olive_category(self, client: str, data: Dict[str, Any]):
        """用实时类目树从平台字段、标签和问题中识别 Payoneer Olive 平台类目。"""
        client_norm = str(client or '').strip().lower().replace('_', '').replace('-', '')
        if client_norm != 'payoneerolive':
            return None, None

        if not self.all_client_category_dict.get(client, {}).get('name_map_dict'):
            self.load_category_map_dict(client)
        name_map = self.all_client_category_dict.get(client, {}).get('name_map_dict', {})
        if not name_map:
            return None, None

        ext_info = data.get('ext_info') if isinstance(data.get('ext_info'), dict) else {}
        explicit_values = [
            ext_info.get('marketplace'),
            ext_info.get('model_platform'),
        ]
        tags = ext_info.get('tags') or data.get('tags') or []
        if not isinstance(tags, list):
            tags = [tags]
        title = str(data.get('title') or '')

        matches = []
        for category_path, chain in name_map.items():
            if not chain:
                continue
            leaf_name = str(chain[-1].get('category_name') or '').strip()
            if not leaf_name or leaf_name == '默认分组':
                continue
            score = 0
            source = None
            if any(str(value or '').strip().casefold() == leaf_name.casefold()
                   for value in explicit_values):
                score, source = 300, 'model_platform'
            elif any(self._category_name_occurs(tag, leaf_name) for tag in tags):
                score, source = 200, 'model_tag'
            elif self._category_name_occurs(title, leaf_name):
                score, source = 100, 'question_text'
            if score:
                # 同等来源时优先更具体的长类目，如 TikTok Shop-美国ACCU。
                matches.append((score, len(category_path), category_path, chain, source))

        if not matches:
            return None, None
        _, _, _, chain, source = sorted(matches, reverse=True)[0]
        leaf = chain[-1]
        category_info = {
            'category_id': str(leaf.get('category_id') or ''),
            'category_name': leaf.get('category_name'),
            'score': 0.9,
            'source': source,
        }
        return chain, category_info
        


    def join_multimodal_contents(self, multimodal_contents: list[Dict[str, Any]]) -> str:
        """
        拼接多模态内容
        Args:
            data: 待拼接的多模态内容
        Returns:
            str: 拼接后的内容
        """
        content = ""
        for file_info in multimodal_contents:
            if file_info.get("type") == "text":
                content = f"{content}\n{file_info.get('content')}"  if content else file_info.get('content')
            elif file_info.get("type") in ["image", "video", "audio", "file"]:
                address = f'[multimodal_prefix]{file_info["path"]}' if file_info.get("path") else file_info.get("url")
                if not address:
                    continue
                content = f"{content}\n{address}"  if content else address
        return content

    def render_multimodal_urls(self, doc: Dict[str, Any]) -> None:
        """
        检索返回时把 content 里的 [multimodal_prefix] 占位符实时拼成真实 URL，
        并在内部存储的地址后面带上 filename 参数，供文件服务返回正确的下载文件名。
        形如: https://file.marsmind.cc/boot-admin/xxx/1234.xls?filename=test_name.xls
        只处理内部 path，外链（multimodal_contents 里只有 url 的条目）入库时就没有占位符，不受影响。
        Args:
            doc: 一条检索结果，原地修改 doc['content']
        """
        if not doc:
            return
        content = doc.get('content')
        if not isinstance(content, str) or '[multimodal_prefix]' not in content:
            return

        # 按 path 长度倒序替换，避免某个 path 是另一个 path 的前缀时先替短的把长的截断
        multimodal_contents = doc.get('multimodal_contents') or []
        path_name_pairs = []
        for file_info in multimodal_contents:
            if not isinstance(file_info, dict):
                continue
            path = file_info.get('path')
            file_name = file_info.get('fileName')
            if path and file_name:
                path_name_pairs.append((path, file_name))
        path_name_pairs.sort(key=lambda pair: len(pair[0]), reverse=True)

        for path, file_name in path_name_pairs:
            placeholder = f'[multimodal_prefix]{path}'
            if placeholder not in content:
                continue
            separator = '&' if '?' in path else '?'
            full_url = f'{self.multimodal_prefix}{path}{separator}filename={quote(file_name, safe="")}'
            content = content.replace(placeholder, full_url)

        # 兜底：multimodal_contents 里没登记、或没有 fileName 的占位符，仍然只替换前缀
        doc['content'] = content.replace('[multimodal_prefix]', self.multimodal_prefix)

    def process_one_data(self, data: Dict[str, Any], index_name: str = None) -> bool:
        """
        处理单条数据,为数据增加必要的embedding和提取关键词。
        Args:
            data: 待处理的数据
        Returns:
            bool: 处理是否成功
        """
        try:
            # 定义schema中的字段
            schema_fields = self.doc_schema_field
                
            # 初始化ext_info
            ext_info = data.get('ext_info', {})
            
            # 将非schema字段移动到ext_info
            for field in list(data.keys()):
                if field not in schema_fields:
                    ext_info[field] = data.pop(field)
            
            # 更新ext_info
            data['ext_info'] = ext_info

            # 确保audit_result字段存在且值合法
            if 'is_audit' in data:  # 处理旧数据
                data['audit_result'] = data.pop('is_audit')
            if 'audit_result' not in data and '_id' not in data and not data.get('_id'):
                data['audit_result'] = -1  # 默认未审核
            if data.get('audit_result') is not None and data['audit_result'] not in [-1, 0, 1, 2]:
                logging.warning(f"数据{data.get('_id')}的audit_result值非法: {data['audit_result']}, 设置为默认值-1")
                data['audit_result'] = -1

            # 确保quality_level字段存在且值合法
            if 'quality_level' not in data and '_id' not in data:
                data['quality_level'] = 'mid'  # 默认中等质量
            elif '_id' not in data and data.get('quality_level') not in ['high', 'mid', 'low']:
                logging.warning(f"数据{data.get('_id')}的quality_level值非法: {data['quality_level']}, 设置为默认值mid")
                data['quality_level'] = 'mid'

            # 1. 处理indexes
            if 'indexes' not in data:
                data['indexes'] = []

            if 'image_indexes' not in data:
                data['image_indexes'] = []

            # image_indexes 的文本直接放到indexes中，进行数据冗余存储，todo：后续重构索引库时需要优化，避免重新存储
            for idx in data.get('image_indexes', []):
                if 'text' in idx:
                    data['indexes'].append({'text': idx['text']})
            # 如果title不为空且不在indexes中，添加到indexes
            if data.get('title') and not any(idx.get('text') == data['title'] for idx in data.get('indexes', [])):
                data['indexes'].append({'text': data['title']})
            
            # 如果有同义title，也添加到indexes中
            if data.get('synonyms_title'):
                if not isinstance(data['synonyms_title'], list):
                    logging.warning(f"数据{data.get('_id')}的synonyms_title不是列表格式，将被忽略")
                    data['synonyms_title'] = []
                else:
                    for syn_title in data['synonyms_title']:
                        if not isinstance(syn_title, str):
                            logging.warning(f"数据{data.get('_id')}的synonyms_title包含非字符串元素，将被忽略")
                            continue
                        if not any(idx.get('text') == syn_title for idx in data['indexes']):
                            data['indexes'].append({'text': syn_title})
            
            # 2. 为indexes中的每个text生成embedding。
            # 空 text 送 DashScope 会 400，异常一路上抛导致**整条数据**入库失败，
            # 所以这里跳过空索引并把它从 indexes 里剔掉，而不是拖垮整条。
            data['indexes'] = [idx for idx in data['indexes']
                               if not ('text' in idx and not str(idx.get('text') or '').strip())]
            for idx in data['indexes']:
                if 'text' in idx and 'embedding' not in idx:
                    embedding = self.embedding_tools.text2embedding(idx['text'])
                    if embedding is not None:
                        idx['embedding'] = embedding.tolist()

            data['image_indexes'] = [idx for idx in data['image_indexes']
                                     if not ('text' in idx and not str(idx.get('text') or '').strip())]
            for idx in data['image_indexes']:
                if 'text' in idx and 'embedding' not in idx:
                    embedding = self.embedding_tools.text2embedding(idx['text'])
                    if embedding is not None:
                        idx['embedding'] = embedding.tolist()

            if "multimodal_contents" in data and data.get('multimodal_contents'): 
                data["content"] = self.join_multimodal_contents(data.get('multimodal_contents')) # 有多模态内容时，content为多模态内容拼接后的内容
            # 3. 分别处理title_embedding和content_embedding
            if data.get('title') and 'title_embedding' not in data:
                title_embedding = self.embedding_tools.text2embedding(data['title'])
                if title_embedding is not None:
                    data['title_embedding'] = title_embedding.tolist()
                    
            if data.get('content') and 'content_embedding' not in data:
                content_embedding = self.embedding_tools.text2embedding(data['content'])
                if content_embedding is not None:
                    data['content_embedding'] = content_embedding.tolist()
            
            # 4. 处理keywords
            if not data.get('keywords') and (data.get('title') or data.get('content')):
                try:
                    keywords = gen_keyword_by_title_content(data.get('title', ''), data.get('content', ''), topK=5)
                    keywords = [word_info['word'] for word_info in keywords]                
                    if keywords:
                        data['keywords'] = keywords
                except ImportError:
                    logging.warning("关键词生成工具未实现，跳过关键词生成")


            # indexes和image_indexes 不会允许在更新时清空，因为不能检索，只能是根据其它字段自动生成，或指定有的数据。后面最好的做法其实是招回旧数据进行合并，再生成新的indexes和image_indexes，现在会导致一些更新异常，todo:后续需要召回旧数据进行合并
            if "indexes" in data and not data.get('indexes'):
                del data['indexes']
            if "image_indexes" in data and not data.get('image_indexes'):
                del data['image_indexes']
            
            # 5. 确保data_type为qa或doc时才有title字段
            if data.get('data_type') == 'segment':
                data.pop('title', None)
                data.pop('synonyms_title', None)
            elif data.get('data_type') in ['qa', 'doc']:
                if not data.get('title'):
                    logging.warning(f"数据{data.get('_id')}的data_type为{data.get('data_type')}，但缺少title字段")
            
            # 处理时间字段
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 处理insert_time
            # 三种情况分开：新数据没带就补当前时间；更新（有 _id）没带就不写，让 ES 保留原值；
            # 带了但不是字符串才纠正。注意不能写成 `if 'insert_time' not in data and '_id' not in data
            # ... elif not isinstance(data['insert_time'], str)` —— 「有 _id 且没带 insert_time」
            # 会走进 elif 直接 KeyError，整条数据处理失败。
            if 'insert_time' not in data:
                if '_id' not in data:
                    data['insert_time'] = current_time
            elif not isinstance(data['insert_time'], str):
                logging.warning(f"数据{data.get('_id')}的insert_time格式错误，设置为当前时间")
                data['insert_time'] = current_time
                
            # 处理update_time
            data['update_time'] = current_time
            
            # 处理from_type
            if 'from_type' not in data and '_id' not in data:
                logging.warning(f"数据{data.get('_id')}缺少from_type字段")
                data['from_type'] = 'unknown'
            elif 'from_type' in data and not isinstance(data['from_type'], str):
                logging.warning(f"数据{data.get('_id')}的from_type不是字符串类型，将被转换")
                data['from_type'] = str(data['from_type'])
            if 'from_type_norm' not in data and '_id' not in data:
                data['from_type_norm'] = get_from_norm_type(data)
            if 'tags' not in data and '_id' not in data:
                data['tags'] = data.get('keywords', [])
            if 'del_flag' not in data and '_id' not in data: # 如果_id存在，则之前应该已经有数据了
                data['del_flag'] = 0
            else:
                logging.info(f"数据{data.get('_id')}的del_flag值非法: {data.get('del_flag')}, 设置为默认值0")
            logging.info(f"数据{data.get('_id')}的category_infos: {data.get('category_infos')}")
            valid_category_infos = []
            if 'category_infos' in data and data.get('category_infos'): # 多个类目来源应该获取旧数据合并后选取多个score > 0 的
                for category_info in data.get('category_infos', []):
                    if not isinstance(category_info, dict):
                        continue
                    category_info = dict(category_info)
                    # webhook/模型可以只传平台名作为 category_name，
                    # category_id 由当前 client 的类目树解析，不再强制上游同时传 ID。
                    if category_info.get('category_id') in (None, '') and category_info.get('categoryId') not in (None, ''):
                        category_info['category_id'] = category_info.pop('categoryId')
                    if category_info.get('category_name') in (None, '') and category_info.get('categoryName') not in (None, ''):
                        category_info['category_name'] = category_info.pop('categoryName')
                    if category_info.get('category_id') not in (None, ''):
                        category_info['category_id'] = str(category_info['category_id'])
                    if category_info.get('category_name') not in (None, ''):
                        category_info['category_name'] = str(category_info['category_name']).strip()
                    if category_info.get('category_id') or category_info.get('category_name'):
                        valid_category_infos.append(category_info)
                data['category_infos'] = valid_category_infos
            # 获取client，优先从data中获取，否则从配置或platform获取。
            client = data.get('client') or data.get('ext_info', {}).get('client') or data.get('platform')
            primary_category_info = None
            parent_chain = []
            if client:
                # 不能只尝试最高分一项：模型可能先给一个不在类目树里的平台名，
                # 后续候选仍有可能有效。显式 category_id/name 仍按最高分优先。
                for category_info in sorted(
                        valid_category_infos, key=lambda x: x.get('score', 0), reverse=True):
                    candidate_chain = self.get_category_parent_chain(
                        client,
                        cate_id=category_info.get('category_id'),
                        cate_name=category_info.get('category_name'),
                    )
                    if candidate_chain:
                        primary_category_info = category_info
                        parent_chain = candidate_chain
                        break

                model_sources = {'model_platform', 'model_tag', 'question_text'}
                has_manual_category = any(
                    str(item.get('source') or 'manual') not in model_sources
                    for item in valid_category_infos
                )
                if not parent_chain and not has_manual_category:
                    parent_chain, inferred_info = self.infer_payoneer_olive_category(client, data)
                    if parent_chain and inferred_info:
                        primary_category_info = inferred_info
                        # 走到这里说明原有模型候选均未命中类目树；不要把无效高分候选一同写入 ES。
                        valid_category_infos = [inferred_info]
                        data['category_infos'] = valid_category_infos

            if parent_chain and primary_category_info:
                leaf_category = parent_chain[-1]
                primary_category_info.setdefault('category_id', str(leaf_category.get('category_id') or ''))
                primary_category_info.setdefault('category_name', leaf_category.get('category_name'))
                category_names = [node['category_name'] for node in parent_chain]
                primary_category = {
                    'category_path': '-'.join(category_names),
                    'category_ids': [node['category_id'] for node in parent_chain],
                }
                for i, node in enumerate(parent_chain):
                    level_num = i + 1
                    primary_category[f'cate{level_num}_name'] = node['category_name']
                    primary_category[f'cate{level_num}_id'] = node['category_id']
                data['primary_category'] = primary_category
                logging.debug(f"构造primary_category成功: {primary_category}")
            elif valid_category_infos:
                logging.warning(f"类目未在client={client}的类目树中找到, data_id: {data.get('_id')}")
                # 模型候选不存在时清掉无效值，让下面统一落默认分组；人工显式值保留便于排查。
                if not any(str(item.get('source') or 'manual') not in {'model_platform', 'model_tag', 'question_text'}
                           for item in valid_category_infos):
                    data.pop('category_infos', None)

                

            # 没有任何类目来源时兜底到「默认分组」（category_id=1，各 client 类目树里都真实存在）。
            # 不补的话文档连 primary_category 字段都没有，前端按类目 ID/名称筛整批都筛不出来，
            # 也进不了任何分组统计（群聊自动学习 chat_auto 链路就是这样漏的）。
            # 只对新数据生效：更新旧数据不写，避免把已有真实类目覆盖成默认分组。
            if '_id' not in data and not data.get('primary_category'):
                data['primary_category'] = build_default_primary_category()
                if not data.get('category_infos'):
                    data['category_infos'] = build_default_category_infos()

            if not data.get("dataset") and index_name:
                data['dataset'] = index_name
            if '_id'  in data: # 已有数据，更新清空None值，即不更新这些字段（indexes、image_indexes、primary_category不能指定清空）
                clear_none_value(data, is_local=True)
            if '_id' not in data: # 最后再确保_id存在
                data['_id'] = gen_data_id(data)
                
            return True
        
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"traceback: {tb}")
            logging.error(f"处理数据失败: {str(e)}")
            return False
    
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
    
    def search_data(self, query: Dict[str, Any], 
                   size: Optional[int] = None, index_names: Optional[Union[str, List[str]]] = None) -> List[Dict[str, Any]]:
        """
        搜索数据
        Args:
            query: 查询条件
            size: 返回结果数量限制
        Returns:
            List[Dict]: 搜索结果列表
        """
        return self.engine.search(query, size, index_names=index_names)
    
    def update_data_value(self, index_name: str, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]]) -> bool:
        """
        更新数据
        """
        return self.engine.update_value(index_name, update_value_dict, conditions)
    
    def get_unique_values(self, index_name: str, field_name: str, size: int = 10000, include_doc_count: bool = False, extra_query: Optional[Dict[str, Any]] = None) -> Union[List[str], List[Dict[str, Any]]]:
        """
        获取指定字段的唯一值集合
        """
        return self.engine.get_unique_values(index_name, field_name, size, include_doc_count, extra_query)

    # ================= 按来源文件名批量下架知识 =================
    #
    # 设计与实测依据见 docs/按文件名删除知识服务_方案.md。三条硬约束：
    #   1) 只作用于非对话来源（FROM_TYPE_SCOPE 白名单），对话学来的知识不在范围内
    #   2) match_mode 严格二选一，exact 查不到不转模糊、fuzzy 不达阈值不退回精确
    #   3) 一律软删 del_flag=1，删前写快照

    # 只处理"来源于文件/网页/免审录入"的知识。
    # 必须用白名单而不是 must_not=auto_learning：存量里 auto_learning 还有中文旧写法
    # "自动学习"（实测 payoneer_olive 有 334 条），黑名单会让它漏网被删。
    FROM_TYPE_SCOPE = ["document", "html", "manual"]

    FILE_NAME_FIELD = "ext_info.from_file_name"
    FILE_NAME_KEYWORD = "ext_info.from_file_name.keyword"

    # 文档重跑后，新知识用新文件名入库，但它取代的是另一个名字的旧文档
    # （实测 wayfair：库里旧名带分类前缀「基础运营_管理我的团队页面.docx」，
    #   新包同一篇叫「管理"我的团队 (My Team)"页面.docx」，纯文件名对不上）。
    # 重跑入库时把前身文件名写进 ext_info.supersedes_file_name，
    # 删除时两个字段一起匹配 —— 这样前端删旧文件名能连新知识一起删掉，反之亦然。
    SUPERSEDES_FIELD_KEYWORD = "ext_info.supersedes_file_name.keyword"

    # .keyword 的 ignore_above，超过就不会被索引成 keyword，term 查询永远查不到且不报错
    KEYWORD_IGNORE_ABOVE = 256
    # index.max_wildcard_length，本集群为 50；留 2 个字符给前后的 *
    MAX_WILDCARD_FRAGMENT = 48
    # 模糊匹配采纳阈值
    DICE_THRESHOLD = 0.9

    @staticmethod
    def _bigrams(text: str) -> set:
        s = (text or "").strip().lower()
        return set(s[i:i + 2] for i in range(len(s) - 1)) or ({s} if s else set())

    @classmethod
    def dice_similarity(cls, a: str, b: str) -> float:
        """Dice 系数（按字符二元组）。两串完全相同为 1.0。"""
        A, B = cls._bigrams(a), cls._bigrams(b)
        if not A or not B:
            return 1.0 if (a or "") == (b or "") else 0.0
        return 2 * len(A & B) / (len(A) + len(B))

    @staticmethod
    def _escape_wildcard(text: str) -> str:
        """转义 wildcard 语法字符，避免文件名里的 * ? 被当成通配。"""
        return (text or "").replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")

    def _scope_filters(self) -> List[Dict[str, Any]]:
        """所有查询共用的基础过滤：未删除 + 非对话来源。"""
        return [
            {"term": {"del_flag": 0}},
            {"terms": {"from_type_norm": list(self.FROM_TYPE_SCOPE)}},
        ]

    def _build_file_query(self, file_names: List[str],
                          data_types: Optional[List[str]] = None,
                          audit_results: Optional[List[int]] = None) -> Dict[str, Any]:
        """构造「这些文件名 + 可选类型/审核状态」的 ES query。文件名一律精确匹配。

        文件名同时匹配 from_file_name 与 supersedes_file_name（OR）：
        文档重跑后新知识换了文件名，传旧名时要能连新知识一起删掉，否则旧的删了新的还在，
        等于没更新干净。两个字段任一命中即算该文件的知识。
        """
        must: List[Dict[str, Any]] = self._scope_filters()
        names = list(file_names)
        must.append({"bool": {"should": [
            {"terms": {self.FILE_NAME_KEYWORD: names}},
            {"terms": {self.SUPERSEDES_FIELD_KEYWORD: names}},
        ], "minimum_should_match": 1}})
        if data_types:
            must.append({"terms": {"data_type": list(data_types)}})
        if audit_results:
            must.append({"terms": {"audit_result": list(audit_results)}})
        return {"bool": {"must": must}}

    def list_file_names(self, index_name: str, keyword: str = None,
                        size: int = 200) -> List[Dict[str, Any]]:
        """列出范围内真实存在的来源文件名及其条数、类型分布。

        前端第一步用它，让用户从真实存在的名字里挑，从根上避免"文件名写错"。
        """
        must = self._scope_filters()
        if keyword:
            frag = self._escape_wildcard(keyword)[:self.MAX_WILDCARD_FRAGMENT]
            must.append({"wildcard": {self.FILE_NAME_KEYWORD:
                                      {"value": "*%s*" % frag, "case_insensitive": True}}})
        buckets = self.engine.agg_terms(
            index_name, {"bool": {"must": must}}, self.FILE_NAME_KEYWORD, size=size,
            sub_aggs={"by_type": {"terms": {"field": "data_type", "size": 10}}},
        )
        return [{"value": b["key"], "doc_count": b["doc_count"],
                 "type_count": (b.get("sub") or {}).get("by_type", {})}
                for b in buckets]

    def resolve_file_name(self, index_name: str, name: str,
                          match_mode: str = "exact") -> Dict[str, Any]:
        """把用户输入的文件名解析成库里真实存在的文件名。

        match_mode 严格二选一，没有兜底：
          - exact：只做 keyword 精确匹配；查不到就是查不到，不会转模糊
          - fuzzy：只做模糊召回 + Dice 判定；达不到阈值就是没找到，不会退回精确

        返回 {matched, matched_name, doc_count, dice, reason}
        """
        name = (name or "").strip()
        if not name:
            return {"matched": False, "matched_name": None, "doc_count": 0,
                    "dice": 0.0, "reason": "文件名为空"}

        # .keyword 的 ignore_above 会让超长文件名根本没被索引，term 查不到且不报错。
        # 必须显式拦下来，否则用户以为删了、其实一条没删。
        if len(name) > self.KEYWORD_IGNORE_ABOVE:
            return {"matched": False, "matched_name": None, "doc_count": 0, "dice": 0.0,
                    "reason": "文件名超过 %d 字符，未被索引为 keyword，无法按文件名匹配"
                              % self.KEYWORD_IGNORE_ABOVE}

        if match_mode == "exact":
            cnt = self.engine.count_by_query(
                index_name, self._build_file_query([name]))
            if cnt > 0:
                return {"matched": True, "matched_name": name, "doc_count": cnt,
                        "dice": 1.0, "reason": None}
            return {"matched": False, "matched_name": None, "doc_count": 0, "dice": 0.0,
                    "reason": "精确匹配无结果"}

        if match_mode != "fuzzy":
            return {"matched": False, "matched_name": None, "doc_count": 0, "dice": 0.0,
                    "reason": "match_mode 只能是 exact 或 fuzzy"}

        # fuzzy：下面几路都只负责「把候选捞全」，最终判定一律交给 Dice。
        #
        # 为什么不能只用 wildcard + match：
        #   - wildcard `*name*` 要求输入是真实名字的子串。用户多打一个字符
        #     （Text.docxx vs Text.docx）就不再是子串，捞不到。
        #   - 文件名字段的分词把 "text.docx" 切成**一个** token，
        #     所以 match 查 "text.docxx" 同样对不上。
        # 结果是"输错一个字"这种最典型的场景反而召不回。故再加两路：
        #   - fuzzy 查询：对 token 做编辑距离，救「多打/打错几个字符」
        #   - 前缀片段 wildcard：用输入的前一段做 `*frag*`，救「尾巴写错/写多」
        esc = self._escape_wildcard(name)
        frag = esc[:self.MAX_WILDCARD_FRAGMENT]
        # 取前 60% 作为前缀片段（至少 4 字符），让尾部写错时仍能命中
        prefix_len = max(4, min(len(esc) * 3 // 5, self.MAX_WILDCARD_FRAGMENT))
        prefix = esc[:prefix_len]
        shoulds = [
            {"wildcard": {self.FILE_NAME_KEYWORD:
                          {"value": "*%s*" % frag, "case_insensitive": True}}},
            {"match": {self.FILE_NAME_FIELD: {"query": name}}},
            {"match": {self.FILE_NAME_FIELD: {"query": name, "fuzziness": "AUTO"}}},
        ]
        if prefix and prefix != frag:
            shoulds.append({"wildcard": {self.FILE_NAME_KEYWORD:
                                         {"value": "*%s*" % prefix, "case_insensitive": True}}})
        query = {"bool": {
            "must": self._scope_filters(),
            "should": shoulds,
            "minimum_should_match": 1,
        }}
        buckets = self.engine.agg_terms(index_name, query, self.FILE_NAME_KEYWORD, size=80)
        best = None
        for b in buckets:
            score = self.dice_similarity(name, b["key"])
            if best is None or score > best[0]:
                best = (score, b["key"], b["doc_count"])
        if best and best[0] >= self.DICE_THRESHOLD:
            return {"matched": True, "matched_name": best[1], "doc_count": best[2],
                    "dice": round(best[0], 4), "reason": None}
        return {"matched": False, "matched_name": None, "doc_count": 0,
                "dice": round(best[0], 4) if best else 0.0,
                "reason": "模糊匹配最高相似度 %.4f 未达阈值 %s"
                          % (best[0] if best else 0.0, self.DICE_THRESHOLD)}

    def preview_delete_by_file(self, index_name: str, file_names: List[str],
                               match_mode: str = "exact",
                               data_types: Optional[List[str]] = None,
                               audit_results: Optional[List[int]] = None,
                               sample_size: int = 10) -> Dict[str, Any]:
        """预览按文件名删除会命中什么。只读，不改任何数据。"""
        by_file, warnings, resolved = [], [], []
        for raw in file_names:
            r = self.resolve_file_name(index_name, raw, match_mode)
            entry = {"input_name": raw, "matched": r["matched"],
                     "matched_name": r["matched_name"], "dice": r["dice"],
                     "count": r["doc_count"], "type_count": {}, "audit_count": {}}
            if not r["matched"]:
                entry["reason"] = r["reason"]
                warnings.append("「%s」未匹配到：%s" % (raw, r["reason"]))
            else:
                if match_mode == "fuzzy" and r["matched_name"] != raw:
                    warnings.append("「%s」模糊匹配到「%s」(相似度 %.4f，%d 条)，请确认"
                                    % (raw, r["matched_name"], r["dice"], r["doc_count"]))
                q = self._build_file_query([r["matched_name"]], data_types, audit_results)
                entry["count"] = self.engine.count_by_query(index_name, q)
                for b in self.engine.agg_terms(index_name, q, "data_type", size=10):
                    entry["type_count"][b["key"]] = b["doc_count"]
                for b in self.engine.agg_terms(index_name, q, "audit_result", size=10):
                    entry["audit_count"][str(b["key"])] = b["doc_count"]
                resolved.append(r["matched_name"])
            by_file.append(entry)

        total, type_count, samples = 0, {}, []
        if resolved:
            q = self._build_file_query(resolved, data_types, audit_results)
            total = self.engine.count_by_query(index_name, q)
            for b in self.engine.agg_terms(index_name, q, "data_type", size=10):
                type_count[b["key"]] = b["doc_count"]
            if sample_size:
                samples = self.engine.sample_by_query(
                    index_name, q, size=sample_size,
                    includes=["title", "content", "data_type", "audit_result",
                              "ext_info.from_file_name", "from_type_norm"])
                for s in samples:
                    s["content"] = (s.get("content") or "")[:120]

        return {"total_count": total, "by_file": by_file, "type_count": type_count,
                "samples": samples, "warnings": warnings,
                "resolved_names": resolved}

    def delete_by_file(self, index_name: str, file_names: List[str],
                       match_mode: str = "exact",
                       data_types: Optional[List[str]] = None,
                       audit_results: Optional[List[int]] = None,
                       snapshot_dir: str = "data/deleted_snapshots") -> Dict[str, Any]:
        """按文件名软删除（del_flag=1）。删前写快照，可回滚。

        入参与 preview_delete_by_file 完全一致，区别只是这个真删、那个不删。
        是否要让用户先看预览再确认，由前端流程决定，服务端不强制。
        """
        preview = self.preview_delete_by_file(
            index_name, file_names, match_mode, data_types, audit_results, sample_size=0)
        resolved = preview["resolved_names"]
        if not resolved:
            return {"success": False, "deleted_count": 0, "snapshot_path": None,
                    "message": "没有匹配到任何文件名，未执行删除；" + "；".join(preview["warnings"])}

        query = self._build_file_query(resolved, data_types, audit_results)
        snapshot_path = self._dump_snapshot(index_name, query, snapshot_dir)
        result = self.engine.update_by_query(index_name, query, {"del_flag": 1})
        msg = "已软删除 %d 条" % result["updated"]
        if result.get("version_conflicts"):
            msg += "（版本冲突 %d 条已跳过）" % result["version_conflicts"]
        return {"success": True, "deleted_count": result["updated"],
                "snapshot_path": snapshot_path, "message": msg}

    def _dump_snapshot(self, index_name: str, query: Dict[str, Any],
                       snapshot_dir: str) -> Optional[str]:
        """删除前把命中文档落盘（不含向量），供回滚。分批取，避免大结果集被分片取消。"""
        try:
            os.makedirs(snapshot_dir, exist_ok=True)
            path = os.path.join(
                snapshot_dir,
                "%s_%s.jsonl" % (index_name, datetime.now().strftime("%Y%m%d_%H%M%S")))
            total = self.engine.count_by_query(index_name, query)
            written, page_size = 0, 500
            with open(path, "w", encoding="utf-8") as fh:
                while written < total:
                    body = {"query": query, "from": written, "size": page_size,
                            "_source": {"excludes": ["*embedding*", "indexes.embedding"]},
                            "sort": ["_doc"]}
                    resp = self.engine._search_with_shard_check(index_name, body)
                    hits = resp.get("hits", {}).get("hits", [])
                    if not hits:
                        break
                    for h in hits:
                        fh.write(json.dumps(dict(h.get("_source") or {}, _id=h.get("_id")),
                                            ensure_ascii=False) + "\n")
                    written += len(hits)
            logger.info("删除快照已写入 %s，共 %d 条", path, written)
            return path
        except Exception as e:
            logger.error("写删除快照失败: %s", str(e))
            raise
    
    def get_data_by_id(self, data_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取数据
        Args:
            data_id: 数据ID
        Returns:
            Optional[Dict]: 数据内容，不存在则返回None
        """
        return self.engine.get(data_id)
    
    def search_data_by_query(self, query:str, index_names:str=None, condition_dicts:List[Dict[str, Any]]=None, size:int=10, search_type:str='qa', 
                             data_type:str='text', use_synonyms=False):
        """
        根据query和attribute_dict搜索数据
        Args:
            query: 查询文本
            attribute_dict: 限制字典
        Returns:
            List[Dict]: 搜索结果列表
        """
        
        query_embedding = self.embedding_tools.text2embedding(query)
        search_query = {
            "query": query,
            "vector": {"value": query_embedding},        
        }
        if index_names:
            index_names = index_names.split(',')            
        if not condition_dicts:
            condition_dicts = []            
            condition_dicts.append({'quality_level': ['high'], 'data_type': ['qa']})
            condition_dicts.append({'audit_result': [1, 2], 'data_type': ['qa']})
        for condition_dict in condition_dicts:
            if 'audit_result' not in condition_dict:
                condition_dict['audit_result'] = [1, 2, -1]
        search_query['attribute'] = condition_dicts
        # size*2 是候选总预算：legacy 模式每索引取这么多；dual 模式每索引每路各取一半，合计不变
        candidate_docs, total_num = self.engine.search_multi(search_query, index_names=index_names, size=size * 2)
        #logger.info(f"搜索结果数量: {len(candidate_docs)}")
        for doc in candidate_docs:
            doc['similarity'] = self._cal_similarity(query, query_embedding, doc, search_type=search_type, data_type=data_type, use_synonyms=use_synonyms)
            self.render_multimodal_urls(doc)
        #candidate_docs.sort(key=lambda x: x['similarity'], reverse=True)
        return candidate_docs, total_num

    def search_data_by_multi_query(self, query_list: List[str], index_names: str=None, condition_dicts: List[Dict[str, Any]]=None, size: int=10, 
                                   search_type: str='qa', data_type: str='text', use_synonyms=False) -> Tuple[List[Dict[str, Any]], int]:
        """
        根据多个query搜索数据，使用一条ES语句实现
        Args:
            query_list: 查询文本列表
            index_names: 索引名称，多个索引用逗号分隔
            condition_dicts: 限制条件字典列表
            size: 返回结果数量
            search_type: 搜索类型，默认为'qa'
            data_type: 数据类型，默认为'text'
            use_synonyms: 是否使用同义词
        Returns:
            Tuple[List[Dict], int]: (搜索结果列表, 总数量)
        """
        if not query_list:
            logger.warning("query_list为空，返回空结果")
            return [], 0
        
        # 为每个query生成embedding
        query_embeddings = []
        for query in query_list:
            if query:  # 跳过空字符串
                embedding = self.embedding_tools.text2embedding(query)
                if embedding is not None:
                    query_embeddings.append({"value": embedding})
        
        # 构建搜索query，使用list格式传递多个query和多个vector
        search_query = {
            "query": query_list,  # 传递查询列表
            "vector": query_embeddings if query_embeddings else None,  # 传递向量列表
        }
        
        # 处理索引名称
        if index_names:
            index_names = index_names.split(',')
        
        # 设置默认条件
        if not condition_dicts:
            condition_dicts = []            
            condition_dicts.append({'quality_level': ['high'], 'data_type': ['qa']})
            condition_dicts.append({'audit_result': [1], 'data_type': ['qa']})
        
        # 确保每个条件都包含audit_result
        for condition_dict in condition_dicts:
            if 'audit_result' not in condition_dict:
                condition_dict['audit_result'] = [1, -1]
        
        search_query['attribute'] = condition_dicts
        
        # 调用底层的search_multi，它现在支持query和vector为list
        try:
            candidate_docs, total_num = self.engine.search_multi(search_query, index_names=index_names, size=size * 2)
            
            # 为每个文档计算相似度
            # 这里需要对每个query都计算一次相似度，取最大值
            for doc in candidate_docs:
                max_similarity = 0
                for i, query in enumerate(query_list):
                    if query:
                        query_embedding = query_embeddings[i]["value"] if i < len(query_embeddings) else None
                        if query_embedding is not None:
                            similarity = self._cal_similarity(query, query_embedding, doc, 
                                                            search_type=search_type, 
                                                            data_type=data_type, 
                                                            use_synonyms=use_synonyms)
                            max_similarity = max(max_similarity, similarity)
                doc['similarity'] = max_similarity
                self.render_multimodal_urls(doc)

            logger.info(f"多查询搜索完成，查询数量: {len(query_list)}, 结果数量: {len(candidate_docs)}, 总数: {total_num}")
            return candidate_docs, total_num
            
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"多查询搜索失败: {str(e)}")
            logger.error(f"traceback: {tb}")
            # 如果方法1失败，使用多线程方式（回退方案）
            logger.info("尝试使用多线程方式进行多查询搜索...")
            return self._search_data_by_multi_query_threading(query_list, index_names, condition_dicts, size, 
                                                             search_type, data_type, use_synonyms)
    
    def _search_data_by_multi_query_threading(self, query_list: List[str], index_names: str=None, 
                                             condition_dicts: List[Dict[str, Any]]=None, size: int=10,
                                             search_type: str='qa', data_type: str='text', 
                                             use_synonyms=False) -> Tuple[List[Dict[str, Any]], int]:
        """
        使用多线程方式进行多查询搜索（回退方案）
        Args:
            query_list: 查询文本列表
            index_names: 索引名称
            condition_dicts: 限制条件字典列表
            size: 返回结果数量
            search_type: 搜索类型
            data_type: 数据类型
            use_synonyms: 是否使用同义词
        Returns:
            Tuple[List[Dict], int]: (搜索结果列表, 总数量)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def search_single_query(query: str) -> Tuple[List[Dict[str, Any]], int]:
            """搜索单个query"""
            try:
                return self.search_data_by_query(query, index_names, condition_dicts, size, 
                                                search_type, data_type, use_synonyms)
            except Exception as e:
                logger.error(f"查询失败: {query}, 错误: {str(e)}")
                return [], 0
        
        # 使用线程池并发执行查询
        all_results = []
        total_nums = []
        
        with ThreadPoolExecutor(max_workers=min(len(query_list), 10)) as executor:
            future_to_query = {executor.submit(search_single_query, query): query 
                             for query in query_list if query}
            
            for future in as_completed(future_to_query):
                query = future_to_query[future]
                try:
                    results, total_num = future.result()
                    all_results.extend(results)
                    total_nums.append(total_num)
                except Exception as e:
                    logger.error(f"处理查询结果失败: {query}, 错误: {str(e)}")
        
        # 去重合并结果（根据_id去重）
        seen_ids = set()
        merged_results = []
        for doc in all_results:
            doc_id = doc.get('_id')
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                merged_results.append(doc)
        
        # 按相似度排序
        merged_results.sort(key=lambda x: x.get('similarity', 0), reverse=True)
        
        # 截取前size个结果
        final_results = merged_results[:size]
        total_num = max(total_nums) if total_nums else 0
        
        logger.info(f"多线程搜索完成，查询数量: {len(query_list)}, 去重后结果数量: {len(merged_results)}, 返回数量: {len(final_results)}")
        return final_results, total_num
        
    
    def web_search_data(self, query: str, client:str = None, index_names: str=None, condition_dicts: List[Dict[str, Any]]=None, page_size: int=None, page_num: int=1, score_threshold: float=None) -> List[Dict[str, Any]]:
        """
        根据query和attribute_dict搜索数据
        Args:
            query: 查询文本
            attribute_dict: 限制字典
        """
        if query:
            query_embedding = self.embedding_tools.text2embedding(query)
            search_query = {
                "query": query,
                "vector": {"value": query_embedding},        
            }
        else:
            search_query = {}
        if index_names:
            index_names = index_names.split(',')    
            first_index_name = index_names[0]
        else:
            first_index_name = None
        if not condition_dicts:
            condition_dicts = []
        #for condition_dict in condition_dicts:
        #    if 'tags' in condition_dict:
        #        condition_dict['keywords'] = condition_dict.pop('tags')
        
        client = client or first_index_name
        
        for condition_dict in condition_dicts:
            category_ids = []
            if 'category_names' in condition_dict:
                cate_names = condition_dict['category_names'] if isinstance(condition_dict['category_names'], list) else [condition_dict['category_names']]
                trans_ids = [self.map_cate_name_to_id(client, category_name) for category_name in cate_names]
                trans_ids = [trans_id for trans_id in trans_ids if trans_id]
                category_ids.extend(trans_ids)
                condition_dict.pop('category_names')
            if 'category_ids' in condition_dict:
                cate_ids = condition_dict['category_ids'] if isinstance(condition_dict['category_ids'], list) else [condition_dict['category_ids']]
                category_ids.extend(cate_ids)
                condition_dict.pop('category_ids')
            if category_ids:
                condition_dict['category_ids'] = category_ids
        search_query['attribute'] = condition_dicts
        if not page_size:
            page_size = 10000
        candidate_docs, total_num = self.engine.search_multi_by_page(search_query, index_names=index_names, size=page_size, page_num=page_num, score_threshold=score_threshold)
        for doc in candidate_docs:
            self.render_multimodal_urls(doc)
            if "score" in doc:
                doc["score"] = min(doc["score"] / 5.0, 1.0)
            #doc['tags'] = doc.get('keywords', [])
        #candidate_docs.sort(key=lambda x: x['similarity'], reverse=True)
        return candidate_docs, total_num
    
    def _cal_title_similarity(self, query: str, query_embedding: List[float], doc: Dict[str, Any], use_synonyms=False) -> float:
        """
        计算query和data的title相似度
        """
        title_similarity = 0
        if doc.get('title') and doc.get('title_embedding'):
            title_similarity = cosine_similarity(query_embedding, doc['title_embedding'])
        if not use_synonyms:
            return title_similarity
        synonyms_titles = set(doc.get('synonyms_title', []))
        max_synonyms_similarity = 0
        for index_info in doc.get('indexes', []):
            text = index_info.get('text')
            if text and text in synonyms_titles and index_info.get('embedding'):
                synonyms_similarity = cosine_similarity(query_embedding, index_info['embedding'])
                max_synonyms_similarity = max(max_synonyms_similarity, synonyms_similarity)
        logger.debug(f"query: {query}, doc: {doc.get('title')}, title_similarity: {title_similarity}, max_synonyms_similarity: {max_synonyms_similarity}")
        return max(title_similarity, max_synonyms_similarity)
            


    
    def _cal_similarity(self, query: str, query_embedding: List[float], doc: Dict[str, Any], search_type: str='qa', data_type: str='text', use_synonyms=False) -> float:
        """
        计算query和data的相似度
        Args:
            query: 查询文本
            query_embedding: 查询文本的embedding
            doc: 数据
        """
        title_similarity = self._cal_title_similarity(query, query_embedding, doc, use_synonyms)

        if doc.get('content') and doc.get('content_embedding'):
            content_similarity = cosine_similarity(query_embedding, doc['content_embedding'])
        else:
            content_similarity = 0
        if search_type == 'qa':
            if doc.get('title'): # 有title和无title的数据不放在一块排序
                similarity = title_similarity + 0.2 * content_similarity
            else:
                similarity = content_similarity
        else:
            similarity = max(title_similarity, content_similarity)
        if 'image' in data_type: # 如果数据中有图片，考虑图片相似度的影响
            image_similarity = 0
            
            if doc.get('image_indexes'):
                for image_index in doc['image_indexes']:
                    if image_index.get('embedding'):
                        image_similarity = max(image_similarity, cosine_similarity(query_embedding, image_index['embedding']))
            similarity = max(similarity, image_similarity)
            
        logger.debug(f"query: {query}, doc: {doc.get('title')}, use_synonyms: {use_synonyms}, search_type: {search_type}, similarity: {similarity}, title_similarity: {title_similarity}, content_similarity: {content_similarity}")
        return similarity

def test_insert_letian_excel(data_file: str, config_path: str):
    """
    测试插入乐天Excel数据
    Args:
        data_file: 数据文件路径
        config_path: 配置文件路径
    """
    import json
    import logging
    from datetime import datetime
    from knowledge_interface_tools.rawdata_interface import LocalRawDataInterface
    logging.info(f'process data file: {data_file}')
    # 初始化SearchDataInterface
    logging.info(f"初始化SearchDataInterface, index_name: letian, config_path: {config_path}")
    search_interface = SearchDataInterface(config_path=config_path, index_name='RakutenFrance')
    
    # 读取数据文件
    rawdata_interface = LocalRawDataInterface(data_file)
    for data in rawdata_interface.read_data():
        # 转换数据格式  
        #raw_data = json.loads(data)
        raw_data = data
        
        # 转换数据格式
        insert_data = {
            'title': raw_data['question'],  # 使用question作为title
            'content': raw_data['answer'],  # 使用answer作为content
            'synonyms_title': raw_data.get('synonyms_query', []),  # 同义问题作为synonyms_title
            'data_type': 'qa',  # 问答类型数据
            'platform': 'RakutenFrance',  # 平台为乐天
            'audit_result': 1,  # 默认未审核
            'quality_level': 'high',  # 默认中等质量
            'from_type': 'excel',  # 来源为excel
            'insert_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'ext_info': {}  # 额外信息
        }
        for key, value in raw_data.items():
            if key not in insert_data:
                insert_data['ext_info'][key] = value
        
        # 生成_id
        insert_data['_id'] = gen_data_id(insert_data)
        
        # 插入数据
        try:
            success, message = search_interface.insert_data(insert_data)
            if success:
                logging.info(f"成功插入数据: {insert_data['_id']}")
            else:
                logging.error(f"插入数据失败: {insert_data['_id']}, message: {message}")
        except Exception as e:
            logging.error(f"插入数据异常: {str(e)}")
            raise

    
def insert_data_to_search_index(data_file: str, config_path: str, use_platform_index: bool = True, 
                                index_name_assign: str = None, data_type=None, platform=None, from_type=None, 
                                is_update_data: bool = False, 
                                is_only_title: bool = False,
                                basic_threshold: float = 0.7,
                                title_basic_threshold: float = 0.95,
                                check_duplicate: bool = None,
                                allowed_quality_levels=None,
                                required_review_decision: str = None,
                                result_file: str = None,
                                ):
    """
    批量插入search_index数据
    Args:
        data_file: 数据文件路径
        config_path: 配置文件路径
        check_duplicate: 是否做入库查重。None 表示沿用配置文件里的 check_duplicate；
            传 False 可关闭查重，用于「已在外部确认过不重复、且默认查重会误杀」的补插场景
            （例如无 title 的 segment：判重的 min(title_sim, content_sim) 恒为 -1，
             数值规则永不触发，结果全部由主题级 LLM 决定，会把同一篇文档的不同页判成重复）
        allowed_quality_levels: 可入库的质量等级，字符串时用逗号分隔。None 保持旧行为。
        required_review_decision: 要求的审核决策，None 保持旧行为。
        result_file: 可选的 JSON 统计文件，用于返回真实入库/查重/闸门数量。
    """
    import json
    import logging
    from datetime import datetime
    from knowledge_interface_tools.rawdata_interface import LocalRawDataInterface
    logging.info(f'process data file: {data_file}')
    # 初始化SearchDataInterface
    logging.info(f"初始化SearchDataInterface, index_name: letian, config_path: {config_path}")
    search_interface = SearchDataInterface(config_path=config_path, index_name='mix')
    if isinstance(is_only_title, str):
        is_only_title = is_only_title.lower() == 'true'
    if isinstance(check_duplicate, str):
        check_duplicate = check_duplicate.lower() == 'true'
    if check_duplicate is False:
        logging.warning('已关闭入库查重（check_duplicate=False），请确认待插数据已在外部去重')
    if isinstance(allowed_quality_levels, str):
        allowed_quality_levels = {
            value.strip().lower() for value in allowed_quality_levels.split(',') if value.strip()
        }
    elif allowed_quality_levels:
        allowed_quality_levels = {
            str(value).strip().lower() for value in allowed_quality_levels if str(value).strip()
        }
    required_review_decision = str(required_review_decision or '').strip().lower() or None

    result_stats = {
        'input_num': 0,
        'gate_skip_num': 0,
        'quality_gate_skip_num': 0,
        'review_gate_skip_num': 0,
        'tagged_duplicate_skip_num': 0,
        'insert_attempt_num': 0,
        'insert_success_num': 0,
        'duplicate_skip_num': 0,
        'insert_failure_num': 0,
    }

    def _write_result_file():
        if not result_file:
            return
        result_dir = os.path.dirname(result_file)
        if result_dir:
            os.makedirs(result_dir, exist_ok=True)
        temp_file = result_file + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(result_stats, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temp_file, result_file)

    # 读取数据文件
    rawdata_interface = LocalRawDataInterface(data_file)
    index_num = 0
    whole_start_time = time.time()
    for data in rawdata_interface.read_data(is_need_id=False):
        # 转换数据格式  
        logging.info(f"start read data, data_id: {data.get('_id')}")
        #raw_data = json.loads(data)
        index_num += 1
        result_stats['input_num'] += 1
        quality_level = str(data.get('quality_level') or '').strip().lower()
        review_decision = str(
            data.get('review_decision') or data.get('ext_info', {}).get('review_decision') or ''
        ).strip().lower()
        if allowed_quality_levels and quality_level not in allowed_quality_levels:
            result_stats['gate_skip_num'] += 1
            result_stats['quality_gate_skip_num'] += 1
            logging.info("质量闸门跳过 title:%s quality_level:%s", data.get('title'), quality_level)
            continue
        if required_review_decision and review_decision != required_review_decision:
            result_stats['gate_skip_num'] += 1
            result_stats['review_gate_skip_num'] += 1
            logging.info("审核闸门跳过 title:%s review_decision:%s", data.get('title'), review_decision)
            continue
        quality_info = data.get('ext_info', {}).get('quality_info', [])
        quality_info_str = '|'.join(quality_info)
        if '重复' in quality_info_str:
            result_stats['tagged_duplicate_skip_num'] += 1
            logging.info(f"数据重复 title:{data.get('title')}，content:{data.get('content')}，跳过插入")
            continue
        # 转换数据格式
        insert_data = data
        
        # 生成_id
        #if '_id' not in insert_data:
        #    insert_data['_id'] = gen_data_id(insert_data)
        if not insert_data.get('platform') and insert_data.get('client'): # 原先业务用在电商所以客户就是平台，这里进行一定兼容，适配后面非电商类数据
            insert_data['platform'] = insert_data.get('client')            
        if index_name_assign:
            index_name = index_name_assign        
        elif use_platform_index:
            index_name = insert_data.get('platform')
        else:
            index_name = None
        if 'data_type' not in insert_data and data_type:
            insert_data['data_type'] = data_type
        if 'platform' not in insert_data and platform:
            insert_data['platform'] = platform
        if 'from_type' not in insert_data and from_type:
            insert_data['from_type'] = from_type
        one_data_start_time = time.time()
        # 插入数据
        try:
            result_stats['insert_attempt_num'] += 1
            success, message = search_interface.insert_data(insert_data, index_name=index_name, 
                                                            check_duplicate=check_duplicate,
                                                            is_update_data=is_update_data, 
                                                            is_only_title=is_only_title,
                                                            basic_threshold=basic_threshold,
                                                            title_basic_threshold=title_basic_threshold)
            if success:
                result_stats['insert_success_num'] += 1
                logging.info(f"成功插入数据: {insert_data['_id']}")
            elif message == '数据重复':
                result_stats['duplicate_skip_num'] += 1
                logging.info(f"查重跳过数据: {insert_data['_id']}")
            else:
                result_stats['insert_failure_num'] += 1
                logging.error(f"插入数据失败: {insert_data['_id']}, message: {message}")
            one_data_end_time = time.time()
            logging.info(f"插入数据{index_num}条，耗时: {one_data_end_time - one_data_start_time}秒, 总耗时: {one_data_end_time - whole_start_time}秒")
        except Exception as e:
            result_stats['insert_failure_num'] += 1
            _write_result_file()
            logging.error(f"插入数据异常: {str(e)}")
            raise
    _write_result_file()
    logging.info('入库统计: %s', result_stats)
    return result_stats

def test_search_by_query(query: str, config_path: str):
    """
    测试根据query搜索数据
    Args:
        query: 查询文本
    """
    search_interface = SearchDataInterface(config_path=config_path, index_name='mix')
    index_names = 'rakutenfrance'
    results = search_interface.search_data_by_query(query, index_names=index_names, size=10)
    for result in results:
        logging.info(f"搜索结果: {result}")

def test_insert(index_names:str, config_path:str):
    """
    """
    search_interface = SearchDataInterface(config_path=config_path, index_name=index_names)
    insert_data = {
        'title': 'test',
        'content': 'content',
        'data_type': 'qa',
        'from_type': 'chat',
        'insert_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'ext_info':  {}
    }
    success, message = search_interface.insert_data(insert_data)
    logging.info(f"插入数据: {insert_data}, 成功: {success}, 消息: {message}")

def gen_audit_data(index_name: str, config_path: str, audit_result: str, quality_level: str = None, from_type: str = None):
    """
    检索所有data_type为qa且audit_result符合条件的数据，并输出到标准输出
    Args:
        index_name: 索引名称
        config_path: 配置文件路径
        audit_result: 审核结果，可以是单个值或逗号分隔的字符串
    """
    # 处理audit_result参数
    if isinstance(audit_result, str):
        audit_result = [int(result) for result in audit_result.split(',')]
    elif isinstance(audit_result, int):
        audit_result = [audit_result]
    else:
        audit_result = list(audit_result)

    if quality_level and  isinstance(quality_level, str) and quality_level != 'all':
        quality_level = quality_level.split(',')
    if quality_level and isinstance(quality_level, tuple):
        quality_level = list(quality_level)
    if from_type and isinstance(from_type, str) and from_type != 'all':
        from_type = from_type.split(',')
    if from_type and isinstance(from_type, tuple):
        from_type = list(from_type)
    # 初始化搜索接口
    search_interface = SearchDataInterface(config_path=config_path, index_name=index_name)
    
    # 构建简单的bool查询，直接使用ES原生查询格式
    query = {
        "attribute": {
            "audit_result": audit_result,
            "data_type": "qa"
        }
    }
    if quality_level and quality_level != 'all':
        query['attribute']['quality_level'] = quality_level
    if from_type and from_type != 'all':
        query['attribute']['from_type'] = from_type
    try:
        # 使用scroll API进行分批查询，设置较大的batch_size减少请求次数
        for data in search_interface.engine.scroll_search(
            query,  # 包装在query字段中
            batch_size=5000,  # 增大批次大小
            scroll_timeout='10m'  # 增加scroll超时时间
        ):
            print(json.dumps(data, ensure_ascii=False))
            
    except Exception as e:
        logging.error(f"生成审核数据失败: {str(e)}")

def search_for_audit_data(index_name: str, config_path: str, query_file: str, audit_result: str, quality_level: str = None, from_type: str = None, score_threshold: float = 0.5):
    """
    检索所有data_type为qa且audit_result符合条件的数据，并输出到标准输出
    Args:
        index_name: 索引名称
        config_path: 配置文件路径
        audit_result: 审核结果，可以是单个值或逗号分隔的字符串
    """
    search_interface = SearchDataInterface(config_path=config_path, index_name=index_name)
    if isinstance(audit_result, str):
        audit_result = [int(result) for result in audit_result.split(',')]
    elif isinstance(audit_result, int):
        audit_result = [audit_result]
    else:
        audit_result = list(audit_result)

    if quality_level and  isinstance(quality_level, str) and quality_level != 'all':
        quality_level = quality_level.split(',')
    if quality_level and isinstance(quality_level, tuple):
        quality_level = list(quality_level)
    if from_type and isinstance(from_type, str) and from_type != 'all':
        from_type = from_type.split(',')
    if from_type and isinstance(from_type, tuple):
        from_type = list(from_type)    
    attribute_dict = {
        "audit_result": audit_result,
        "data_type": "qa"
    }
    if quality_level and quality_level != 'all':
        attribute_dict['quality_level'] = quality_level
    if from_type and from_type != 'all':
        attribute_dict['from_type'] = from_type
    with open(query_file, 'r') as f:
        for line in f:
            query_text = line.strip()
            results, total_num = search_interface.search_data_by_query(query_text, index_names=index_name, condition_dicts=[attribute_dict], size=10)
            for result in results:
                score = result['similarity']
                if score < score_threshold:
                    continue
                result['search_query'] = query_text
                print(json.dumps(result, ensure_ascii=False))
if __name__ == "__main__":
    import logging
    import sys    
    import fire
    
    # 配置日志
    logging.basicConfig(
        stream=sys.stderr, 
        level=logging.DEBUG, 
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
               '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    
    fire.Fire()
