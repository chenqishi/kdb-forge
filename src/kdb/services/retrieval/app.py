#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-10-16
"""
import string
import sys
import os
import re
import json
import time
import math
import logging
import copy
import traceback
import codecs
from datetime import datetime
from datetime import timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
import httpx
import json
from typing import List, Dict, Optional, Union, Any
import asyncio
import pathlib
from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
from contextlib import asynccontextmanager
from kdb.retrieval.modification.modify_knowledge import ModifyKnowledge

# 在文件顶部添加日志配置
# 配置根日志记录器，使所有模块的日志都能输出
logging.basicConfig(
    level=logging.INFO,
    force=True,
    format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# 确保 search_index_data_interface 模块的日志也能输出
#logging.getLogger('knowledge_interface_tools.search_index_data_interface').setLevel(logging.INFO)
#logging.getLogger('knowledge_interface_tools.es_search_interface').setLevel(logging.INFO)

# 当前模块的 logger
logger = logging.getLogger(__name__)

# 在 app = FastAPI() 之前添加全局配置
def init_config(config_path: str = "./config/config_for_search_index.json") -> dict:
    try:
        search_data_interface = SearchDataInterface(config_path=config_path)
        return search_data_interface
    except FileNotFoundError:
        logger.error(f"配置文件 {config_path} 不存在")
        raise
    except json.JSONDecodeError:
        logger.error(f"配置文件 {config_path} 格式错误")
        raise

# 全局配置
#SEARCH_DATA_INTERFACE = init_config()
SEARCH_DATA_INTERFACE = None
MODIFY_KNOWLEDGE_HANDLE = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    global SEARCH_DATA_INTERFACE, MODIFY_KNOWLEDGE_HANDLE
    if SEARCH_DATA_INTERFACE is None:
        config_path = "./config/config_for_search_index.json"
        if len(sys.argv) > 1:
            config_path = sys.argv[1]
        try:
            SEARCH_DATA_INTERFACE = init_config(config_path)
            MODIFY_KNOWLEDGE_HANDLE = ModifyKnowledge(SEARCH_DATA_INTERFACE)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"init config error, config_path: {config_path}")
            logger.error(f"traceback: {tb}")
            raise e
    yield
    # 关闭时执行
    pass

app = FastAPI(lifespan=lifespan)

class SearchRequest(BaseModel):
    text: str
    # 默认 100（原为 1000）。1000 正好落在阿里云 serverless ES 容易取消分片的区间：
    # 实测同一条 query 连打 8 次，返回条数在 628~1000 之间乱跳、探针缺失 4/8；
    # 而 top_k<=100 时条数恒定、12 次零缺失。没显式传 top_k 的调用方原本一直在打大查询，
    # 这里把默认值收到安全区。要更多结果显式传即可。
    top_k: int = 100
    score_threshold: float = -1
    index_names: str = None
    condition_dicts: List[Dict[str, Any]] = None
    search_type: str = 'qa'
    data_type: str = 'text'
    use_synonyms: bool = False

class SearchResult(BaseModel):
    id: Optional[str] = None
    dataset: Optional[str] = None
    insert_time: Optional[str] = None
    update_time: Optional[str] = None
    q: str
    a: Optional[str] = None
    ext_info: Optional[Dict[str, Any]] = None
    score: float
    
    class Config:
        extra = "allow"  # 允许额外字段

class SearchResponse(BaseModel):
    results: List[SearchResult]

# 新增WebSearch相关模型
class WebSearchRequest(BaseModel):
    text: str = ''
    page_size: int = 10000
    page_num: int = 1
    index_names: str = None
    client: str = None
    need_from_history: bool = False
    condition_dicts: List[Dict[str, Any]] = []
    score_threshold: float = 5.3
    

class WebSearchResponse(BaseModel):
    results: List[Dict[str, Any]] = []   # 直接返回原始数据字典列表
    total_count : int = 0  # 总记录数
    current_count: int = 0  # 当前请求返回的数据数量
    

class InsertRequest(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    title: str = None
    content: str = None
    multimodal_contents: Optional[List[Dict[str, Any]]] = None
    data_type: str = None
    from_type: str = None
    index_names: str
    platform: str = None
    audit_result: int = None
    client: str = None
    del_flag: int = None
    tags: Optional[List[str]] = None
    from_type_norm: str = None
    dataset: str = None
    task_id: str = None
    categoryId: str = None
    categoryName: str = None
    category_infos: Optional[List[Dict[str, Any]]] = None
    ext_info: Optional[Dict[str, Any]] = None
    refresh_imm: bool = False
    is_need_llm: bool = False
    is_update_data: bool = True
    
    class Config:
        allow_population_by_field_name = True
        extra = "allow"  # 允许额外字段
    
    @property
    def _id(self) -> Optional[str]:
        """为了兼容性，允许使用 _id 访问 id 字段"""
        return self.id
    
    def get_ext_info_with_extra_fields(self, defined_fields: List[str] = None) -> Dict[str, Any]:
        """
        合并显式ext_info和业务扩展字段，不混入请求控制参数或修改请求对象。
        """
        declared_fields = type(self).model_fields
        excluded_fields = set(defined_fields or ()) | set(declared_fields)
        excluded_fields.update(field.alias for field in declared_fields.values() if field.alias)
        final_ext_info = copy.deepcopy(self.ext_info or {})
        for field_name, field_value in self.model_dump(exclude_none=True).items():
            if field_name not in excluded_fields:
                final_ext_info[field_name] = copy.deepcopy(field_value)
        return final_ext_info

class InsertResponse(BaseModel):
    success: bool
    message: str = ""

class DeleteRequest(BaseModel):
    id: str = Field(..., description="数据ID")
    index_names: str = Field(..., description="索引名称")
    refresh_imm: bool = Field(False, description="是否立即刷新使删除立即生效")

class DeleteResponse(BaseModel):
    success: bool
    message: str = ""

# 新增ValueCollectionRequest和Response模型
class ValueCollectionRequest(BaseModel):
    index_name: str = Field(..., description="索引名称")
    field_name: str = Field(..., description="字段名称")
    size: int = Field(10000, description="返回值的数量限制")
    include_doc_count: bool = Field(False, description="是否包含文档数量")
    extra_query: Optional[Dict[str, Any]] = Field(None, description="额外的查询条件")

class ValueCollectionResponse(BaseModel):
    success: bool
    values: Union[List[str], List[Dict[str, Any]]] = []
    total_count: int = 0
    message: str = ""

class FromTypeCountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index_name: Optional[str] = Field("", strict=True, description="单个原物理索引名；空名返回0")
    from_type: str = Field("chat_auto", strict=True, min_length=1, description="精确来源类型，默认chat_auto")
    start: Optional[datetime] = None
    end: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_index_name(cls, values):
        if isinstance(values, dict) and "indexName" in values:
            values = dict(values)
            alias = values.pop("indexName")
            if "index_name" in values and values["index_name"] != alias:
                raise ValueError("index_name与indexName不能冲突")
            values["index_name"] = alias
        return values

    @field_validator("index_name")
    @classmethod
    def validate_index_name(cls, value):
        if value and (value in {"_all", ".", ".."} or value.startswith(("-", "+", "_"))
                      or any(char.isspace() or char in '\\/*?"<>|,#:[]' for char in value)
                      or len(value.encode("utf-8")) > 255):
            raise ValueError("index_name必须是单个原物理索引名")
        return value

    @field_validator("start", "end", mode="before")
    @classmethod
    def validate_local_time(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value):
                raise ValueError("时间格式必须为yyyy-MM-dd HH:mm:ss")
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        if isinstance(value, datetime) and value.tzinfo is None and not value.microsecond:
            return value
        raise ValueError("时间必须为不带时区的本地时间，精确到秒")

class FromTypeCountResponse(BaseModel):
    success: bool
    count: int = 0
    message: str = ""

# ---------------- 按来源文件名批量下架知识 ----------------
# 详见 docs/按文件名删除知识服务_方案.md

class ListFileNamesRequest(BaseModel):
    index_name: str = Field(..., description="索引名称，必填")
    keyword: Optional[str] = Field(None, description="文件名关键词筛选，为空则列全部")
    size: int = Field(200, ge=1, le=1000, description="最多返回多少个文件名")
    from_type_norm: Optional[str] = Field(None, description="来源类型精确筛选；不传、null、空串或仅空白时不限制来源")

class ListFileNamesResponse(BaseModel):
    success: bool
    values: List[Dict[str, Any]] = []
    total_count: int = 0
    message: str = ""

class PreviewDeleteByFileRequest(BaseModel):
    index_name: str = Field(..., description="索引名称，必填")
    file_names: List[str] = Field(..., description="要删除的来源文件名，可多个")
    match_mode: str = Field("exact", description="exact(默认)|fuzzy，严格二选一，无兜底")
    data_types: Optional[List[str]] = Field(None, description="限定 data_type，默认 qa+segment 全删")
    audit_results: Optional[List[int]] = Field(None, description="限定审核状态，默认不限")
    sample_size: int = Field(10, ge=0, le=50, description="返回几条样例供人工确认")

class PreviewDeleteByFileResponse(BaseModel):
    success: bool
    total_count: int = 0
    by_file: List[Dict[str, Any]] = []
    type_count: Dict[str, int] = {}
    samples: List[Dict[str, Any]] = []
    warnings: List[str] = []
    message: str = ""

class DeleteByFileRequest(BaseModel):
    """入参与 PreviewDeleteByFileRequest 一致（除样例条数），区别只是这个真删。"""
    index_name: str = Field(..., description="索引名称，必填")
    file_names: List[str] = Field(..., description="要删除的来源文件名，可多个")
    match_mode: str = Field("exact", description="exact(默认)|fuzzy，严格二选一，无兜底")
    data_types: Optional[List[str]] = Field(None, description="限定 data_type，默认 qa+segment 全删")
    audit_results: Optional[List[int]] = Field(None, description="限定审核状态，默认不限")

class DeleteByFileResponse(BaseModel):
    success: bool
    deleted_count: int = 0
    snapshot_path: Optional[str] = None
    message: str = ""

# 新增条件更新相关模型
class UpdateByConditionRequest(BaseModel):
    index_name: str = Field(..., description="索引名称")
    update_fields: Dict[str, Any] = Field(..., description="要更新的字段和值的映射，格式为 {field_name: new_value}")
    conditions: List[Dict[str, Any]] = Field(..., description="查询条件列表，每个条件为 {field_name: value} 格式")
    
class UpdateByConditionResponse(BaseModel):
    success: bool
    updated_count: int = 0
    message: str = ""

# 新增知识修改相关模型
class ModifyKnowledgeRequest(BaseModel):
    es_index: str = Field(..., description="ES索引名称")
    new_query_info: Dict[str, Any] = Field(..., description="新查询信息，包含title和content")
    old_query_info: Dict[str, Any] = Field(default={}, description="旧查询信息，包含title和content；modify_knowledge接口必填，modify_knowledge_direct_update接口可选")
    search_querys: Optional[List[str]] = Field(None, description="搜索查询列表")
    write_db_id: Optional[str] = Field(None, description="写入数据库ID（仅modify_knowledge使用）")
    allow_insert: bool = Field(False, description="是否允许插入新QA到ES，仅当为True且没有要修改的旧QA时才插入")

class ModifyKnowledgeResponse(BaseModel):
    success: bool
    has_correction: bool = False
    message: str = ""
    modify_qa_infos: Optional[List[Dict[str, Any]]] = None

async def query_remote_service(text: str, index_names: str, condition_dicts: List[Dict[str, Any]], size: int=10, search_type: str='qa', data_type: str='text', use_synonyms: bool=False) -> Dict:
    logger.info(f"query_remote search params: {text}, {index_names}, {condition_dicts}, {size}, {search_type}, {data_type}, {use_synonyms}")
    raw_result, total_num = SEARCH_DATA_INTERFACE.search_data_by_query(query=text, index_names=index_names, condition_dicts=condition_dicts, size=size, search_type=search_type, data_type=data_type, use_synonyms=use_synonyms)
    if raw_result is None:
        return None, 0
    else:
        return raw_result, total_num
    
async def web_remote_service(text: str, index_names: str, condition_dicts: List[Dict[str, Any]], client: str = None, page_num: int=1, page_size: int=10000, score_threshold: float=None) -> Dict:
    logger.info(f"query_remote search params: {text}, {index_names}, {condition_dicts}, {page_num}, {page_size}, {score_threshold}")
    raw_result, total_num = SEARCH_DATA_INTERFACE.web_search_data(query=text,client=client, index_names=index_names, condition_dicts=condition_dicts, page_num=page_num, page_size=page_size, score_threshold=score_threshold)
    if raw_result is None:
        return None, 0
    else:
        return raw_result, total_num

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
        success = SEARCH_DATA_INTERFACE.update_data_value(
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

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    if not request.text:
        raise HTTPException(status_code=400, detail="文本参数不能为空")
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            ptime = time.time()
            raw_result, total_num = await query_remote_service(
                text=request.text, 
                index_names=request.index_names, 
                condition_dicts=request.condition_dicts, 
                size=request.top_k,
                search_type=request.search_type,
                data_type=request.data_type,
                use_synonyms=request.use_synonyms
            )
            
            if raw_result is None:
                raise HTTPException(status_code=400, detail="检索结果错误")
            logger.info(f"query_remote search time: {time.time() - ptime}")
            results = []
            for item in raw_result:
                # 从搜索结果中提取相关字段
                data_id = str(item.get("_id") or item.get("id") or "")
                dataset = item.get("dataset") or item.get("_index")
                insert_time = item.get("insert_time")
                update_time = item.get("update_time")
                score = item.get("similarity", 0.0)
                title = item.get("title", "")
                content = item.get("content", "")
                ext_info = item.get("ext_info", {})
                # 知识所属类目。索引里存的是完整结构（cate1_name/cate2_name/category_path/
                # category_ids 等），其中 category_path 形如「业务地区-巴西」，可直接展示。
                # 消费方（全类目检索时给每条知识标注类目，避免 LLM 张冠李戴）需要它，
                # 此前一直因为下面是手工列字段而被丢掉，数据本身一路都在。
                primary_category = item.get("primary_category")
                if item.get('synonyms_title'):
                    synonyms_title = '|'.join(item.get('synonyms_title'))
                    synonyms_title  = synonyms_title.replace('\n', '|')
                    synonyms_title = f"{title}|同义question:{synonyms_title}"
                else:
                    synonyms_title = title
                

                # 根据数据类型决定如何构建结果
                if item.get("data_type") == "qa" or item.get('title'):
                    combined_text = f"{synonyms_title}\n{content}"  
                    results.append(SearchResult(**{
                        "id": data_id,
                        "dataset": dataset,
                        "insert_time": insert_time,
                        "update_time": update_time,
                        "q": title,
                        "a": content,
                        "content": combined_text,
                        "score": score,
                        "ext_info": ext_info,
                        "synonyms_title": synonyms_title,
                        "metadata": ext_info,
                        "primary_category": primary_category,
                    }))
                else:
                    # 对于其他类型，将title和content组合
                    combined_text = f"{content}"
                    results.append(SearchResult(**{
                        "id": data_id,
                        "dataset": dataset,
                        "insert_time": insert_time,
                        "update_time": update_time,
                        "q": "",
                        "content": combined_text,
                        "score": score,
                        "ext_info": ext_info,
                        "synonyms_title": synonyms_title,
                        "metadata": ext_info,
                        "primary_category": primary_category,
                    }))
            
            # 按 score_threshold 过滤
            if request.score_threshold > -1:
                results = [r for r in results if r.score > request.score_threshold]
            
            # 按 score 排序并取 top_k
            results = sorted(results, key=lambda x: x.score, reverse=True)[:request.top_k]
            logger.info(f"search time: {time.time() - ptime}")
            return SearchResponse(results=results)
            
        except Exception as e:
            tb = traceback.format_exc()
            logger.error('traceback:\n{}'.format(tb))
            logger.error('raw result is %s', raw_result if 'raw_result' in locals() else 'None')
            retry_count += 1
            if retry_count == max_retries:
                return SearchResponse(results=[SearchResult(q="检索结果错误", score=0.0)])
            await asyncio.sleep(1)  # 重试前等待1秒

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
        
        success, message = SEARCH_DATA_INTERFACE.insert_data(filter_insert_data, index_name=index_names, check_duplicate=True, is_update_data=is_update_data, refresh_imm=refresh_imm, is_need_llm=is_need_llm)
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

@app.post("/insert", response_model=InsertResponse)
async def insert(request: InsertRequest):
    """
    插入数据接口
    """
    if not request.index_names:
        raise HTTPException(status_code=400, detail="index_names不能为空")
    
    try:
        ptime = time.time()
        
        # 将原始扩展信息传入处理链；后层无法恢复已漏传的请求字段。
        final_ext_info = request.get_ext_info_with_extra_fields(defined_fields=SEARCH_DATA_INTERFACE.doc_schema_field)
        category_infos = None
        if not request.category_infos and request.categoryId and request.categoryName:
            category_ids = request.categoryId.split(',')
            category_names = request.categoryName.split(',')
            if len(category_ids) != len(category_names):
                raise HTTPException(status_code=400, detail="categoryId和categoryName数量不一致")
            category_infos = []
            for category_id, category_name in zip(category_ids, category_names):
                category_infos.append({
                    'category_id': str(category_id),
                    'category_name': category_name,
                    'score': 1.0,
                    'source': 'manual'
                })
        elif request.category_infos:
            category_infos = request.category_infos
            for category_info in category_infos:
                category_info['category_id'] = str(category_info['category_id']) # 防止int型号
        data_type = request.data_type
        from_type = request.from_type
        if not request.id: # 非更新操作
            if not data_type:
                data_type = "qa"
            if not from_type:
                from_type = "chat"
        
        success, message = await insert_to_service(
            _id=request.id,
            title=request.title,
            content=request.content,
            multimodal_contents=request.multimodal_contents,
            data_type=data_type,
            from_type=from_type,
            index_names=request.index_names,
            platform=request.platform,
            audit_result=request.audit_result,
            client=request.client,
            del_flag=request.del_flag,
            from_type_norm=request.from_type_norm,
            tags=request.tags,
            dataset=request.dataset,
            task_id=request.task_id,
            category_infos=category_infos,
            ext_info=final_ext_info if final_ext_info or request.ext_info is not None else None,
            refresh_imm=request.refresh_imm,
            is_need_llm=request.is_need_llm,
            is_update_data=request.is_update_data
        )
        
        logger.info(f"insert time: {time.time() - ptime}")
        
        if success:
            return InsertResponse(
                success=True,
                message=f"数据已插入: {request.title}"
            )
        else:
            return InsertResponse(
                success=False,
                message=f"{message}"
            )
            
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"处理插入请求失败: {str(e)}")
        logger.error(f"traceback: {tb}")
        return InsertResponse(
            success=False,
            message=f"插入失败: {str(e)}"
        )

@app.post("/delete", response_model=DeleteResponse)
async def delete(request: DeleteRequest):
    """
    删除数据接口
    """
    try:
        ptime = time.time()
        success = SEARCH_DATA_INTERFACE.delete_data(
            data_id=request.id, 
            index_names=request.index_names,
            refresh=request.refresh_imm
        )
        logger.info(f"delete time: {time.time() - ptime}, id: {request.id}, index: {request.index_names}, refresh: {request.refresh_imm}, success: {success}")
        
        return DeleteResponse(
            success=success,
            message=f"数据{'删除成功' if success else '删除失败'}: {request.id}"
        )
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"删除数据失败: {str(e)}")
        logger.error(f"traceback: {tb}")
        return DeleteResponse(
            success=False,
            message=f"删除失败: {str(e)}"
        )

@app.post("/web_search", response_model=WebSearchResponse)
async def web_search(request: WebSearchRequest):
    """
    Web搜索接口 - 返回原始数据，不进行转换和过滤
    """
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            ptime = time.time()
            # 处理查询条件，加入from_file_name
            condition_dicts = request.condition_dicts or []            
            raw_result, total_num = await web_remote_service(
                text=request.text, 
                index_names=request.index_names, 
                client=request.client,
                condition_dicts=condition_dicts, 
                page_num=request.page_num,
                page_size=request.page_size,
                score_threshold=request.score_threshold
            )
            
            if raw_result is None:
                raise HTTPException(status_code=400, detail="检索结果错误")
            
            logger.info(f"web_search query_remote time: {time.time() - ptime}")
            
            # 过滤掉包含embedding的字段，然后返回数据
            results = []
            for item in raw_result:
                if isinstance(item, dict):
                    # 创建新字典，排除包含"embedding"的键
                    filtered_item = {k: v for k, v in item.items() if 'embedding' not in k.lower()}
                    filtered_item['indexes'] = [x['text'] for x in item.get('indexes', [])]
                    if not request.need_from_history and "from_chat_history" in filtered_item.get('ext_info', {}):                        
                        filtered_item['ext_info'].pop('from_chat_history')
                    
                    results.append(filtered_item)
                else:
                    results.append(item)        
            results = sorted(results, key=lambda x: x.get('score', 0.0), reverse=True)
            logger.info(f"web_search total time: {time.time() - ptime}")
            return WebSearchResponse(results=results, total_count=total_num, current_count=len(results))
            
        except Exception as e:
            tb = traceback.format_exc()
            logger.error('web_search traceback:\n{}'.format(tb))
            logger.error('web_search raw result is %s', raw_result if 'raw_result' in locals() else 'None')
            retry_count += 1
            if retry_count == max_retries:
                error_results = [{"error": "检索结果错误", "score": 0.0}]
                return WebSearchResponse(results=error_results, total_count=0, current_count=0)
            await asyncio.sleep(1)  # 重试前等待1秒

@app.post("/get_value_collection", response_model=ValueCollectionResponse)
async def get_value_collection(request: ValueCollectionRequest):
    """
    获取指定索引中指定字段的值集合
    """
    if not request.index_name:
        raise HTTPException(status_code=400, detail="index_name不能为空")
    
    if not request.field_name:
        raise HTTPException(status_code=400, detail="field_name不能为空")
    
    try:
        ptime = time.time()
        logger.info(f"get_value_collection params: index_name={request.index_name}, field_name={request.field_name}, size={request.size}, include_doc_count={request.include_doc_count}, extra_query={request.extra_query}")
        extra_query = request.extra_query
        if not extra_query:
            extra_query = {"term": {
                "del_flag": 0 }}
        # 调用search_index_data_interface的get_unique_values方法
        values = SEARCH_DATA_INTERFACE.get_unique_values(
            index_name=request.index_name,
            field_name=request.field_name,
            size=request.size,
            include_doc_count=request.include_doc_count,
            extra_query=request.extra_query
        )
        
        if values is None:
            raise HTTPException(status_code=500, detail="获取字段值集合失败")
        
        total_count = len(values)
        logger.info(f"get_value_collection time: {time.time() - ptime}, total_count: {total_count}")
        
        return ValueCollectionResponse(
            success=True,
            values=values,
            total_count=total_count,
            message=f"成功获取字段 {request.field_name} 的值集合，共 {total_count} 个值"
        )
        
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"get_value_collection 异常: {str(e)}")
        logger.error(f"traceback: {tb}")
        return ValueCollectionResponse(
            success=False,
            values=[],
            total_count=0,
            message=f"获取值集合失败: {str(e)}"
        )

@app.post("/get_from_type_count", response_model=FromTypeCountResponse)
async def get_from_type_count(request: FromTypeCountRequest):
    """按原索引名精确统计high来源知识，不查询source或创建索引。"""
    if not request.index_name:
        return FromTypeCountResponse(success=True)
    try:
        if SEARCH_DATA_INTERFACE is None:
            raise RuntimeError("Search interface not initialized")
        count = await asyncio.to_thread(
            SEARCH_DATA_INTERFACE.get_from_type_count, request.index_name,
            request.from_type, request.start, request.end,
        )
        return FromTypeCountResponse(success=True, count=count)
    except Exception:
        logger.exception("get_from_type_count failed: index=%s", request.index_name)
        return FromTypeCountResponse(success=False, message="获取来源知识数量失败")

@app.post("/list_file_names", response_model=ListFileNamesResponse)
async def list_file_names(request: ListFileNamesRequest):
    """列出未删除知识的来源文件，可选按 from_type_norm 筛选。

    文件列表的来源范围不代表删除权限，删除接口仍保留原来源白名单。
    """
    try:
        ptime = time.time()
        values = SEARCH_DATA_INTERFACE.list_file_names(
            index_name=request.index_name, keyword=request.keyword, size=request.size,
            from_type_norm=request.from_type_norm)
        logger.info("list_file_names time: %s, index=%s, keyword=%s, got=%d",
                    time.time() - ptime, request.index_name, request.keyword, len(values))
        return ListFileNamesResponse(
            success=True, values=values, total_count=len(values),
            message="共 %d 个来源文件" % len(values))
    except Exception as e:
        logger.error("list_file_names 异常: %s", str(e))
        logger.error("traceback: %s", traceback.format_exc())
        return ListFileNamesResponse(success=False, message="获取文件名列表失败: %s" % str(e))


@app.post("/preview_delete_by_file", response_model=PreviewDeleteByFileResponse)
async def preview_delete_by_file(request: PreviewDeleteByFileRequest):
    """预览按文件名删除会命中哪些知识。只读，必须先调这个才能删。"""
    if not request.file_names:
        raise HTTPException(status_code=400, detail="file_names 不能为空")
    if request.match_mode not in ("exact", "fuzzy"):
        raise HTTPException(status_code=400, detail="match_mode 只能是 exact 或 fuzzy")
    try:
        ptime = time.time()
        r = SEARCH_DATA_INTERFACE.preview_delete_by_file(
            index_name=request.index_name, file_names=request.file_names,
            match_mode=request.match_mode, data_types=request.data_types,
            audit_results=request.audit_results, sample_size=request.sample_size)
        logger.info("preview_delete_by_file time: %s, index=%s, mode=%s, total=%d",
                    time.time() - ptime, request.index_name, request.match_mode,
                    r["total_count"])
        return PreviewDeleteByFileResponse(
            success=True, total_count=r["total_count"], by_file=r["by_file"],
            type_count=r["type_count"], samples=r["samples"], warnings=r["warnings"],
            message="预计软删除 %d 条，确认后用相同参数调用 /delete_by_file" % r["total_count"])
    except Exception as e:
        logger.error("preview_delete_by_file 异常: %s", str(e))
        logger.error("traceback: %s", traceback.format_exc())
        return PreviewDeleteByFileResponse(success=False, message="预览失败: %s" % str(e))


@app.post("/delete_by_file", response_model=DeleteByFileResponse)
async def delete_by_file(request: DeleteByFileRequest):
    """按来源文件名批量软删除知识（qa + segment）。删前自动写快照，可回滚。"""
    if not request.file_names:
        raise HTTPException(status_code=400, detail="file_names 不能为空")
    if request.match_mode not in ("exact", "fuzzy"):
        raise HTTPException(status_code=400, detail="match_mode 只能是 exact 或 fuzzy")
    try:
        ptime = time.time()
        r = SEARCH_DATA_INTERFACE.delete_by_file(
            index_name=request.index_name, file_names=request.file_names,
            match_mode=request.match_mode, data_types=request.data_types,
            audit_results=request.audit_results)
        logger.info("delete_by_file time: %s, index=%s, files=%s, success=%s, deleted=%d",
                    time.time() - ptime, request.index_name, request.file_names,
                    r["success"], r["deleted_count"])
        return DeleteByFileResponse(**r)
    except Exception as e:
        logger.error("delete_by_file 异常: %s", str(e))
        logger.error("traceback: %s", traceback.format_exc())
        return DeleteByFileResponse(success=False, message="删除失败: %s" % str(e))


@app.post("/update_by_condition", response_model=UpdateByConditionResponse)
async def update_by_condition(request: UpdateByConditionRequest):
    """
    根据条件更新数据接口
    根据指定条件更新索引中文档的字段值
    """
    if not request.index_name:
        raise HTTPException(status_code=400, detail="index_name不能为空")
    
    if not request.update_fields:
        raise HTTPException(status_code=400, detail="update_fields不能为空")
    
    if not request.conditions:
        raise HTTPException(status_code=400, detail="conditions不能为空")
    
    try:
        ptime = time.time()
        success, updated_count, message = await update_by_condition_service(
            index_name=request.index_name,
            update_fields=request.update_fields,
            conditions=request.conditions
        )
        
        logger.info(f"update_by_condition time: {time.time() - ptime}")
        
        return UpdateByConditionResponse(
            success=success,
            updated_count=updated_count,
            message=message
        )
            
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"处理条件更新请求失败: {str(e)}")
        logger.error(f"traceback: {tb}")
        return UpdateByConditionResponse(
            success=False,
            updated_count=0,
            message=f"条件更新失败: {str(e)}"
        )

@app.post("/modify_knowledge_direct_update", response_model=ModifyKnowledgeResponse)
async def modify_knowledge_direct_update(request: ModifyKnowledgeRequest):
    """
    直接更新知识库接口
    调用modify_knowledge_direct_update函数，修改知识库中的旧知识并直接写入ES
    """
    if not request.es_index:
        raise HTTPException(status_code=400, detail="es_index不能为空")
    
    if not request.new_query_info:
        raise HTTPException(status_code=400, detail="new_query_info不能为空")
    
    
    try:
        ptime = time.time()
        logger.info(f"modify_knowledge_direct_update params: es_index={request.es_index}, new_query_info={request.new_query_info}, old_query_info={request.old_query_info}, search_querys={request.search_querys}, allow_insert={request.allow_insert}")
        
        modify_message, has_correction = MODIFY_KNOWLEDGE_HANDLE.modify_knowledge_direct_update(
            es_index=request.es_index,
            new_query_info=request.new_query_info,
            old_query_info=request.old_query_info,
            search_querys=request.search_querys,
            allow_insert=request.allow_insert
        )
        
        logger.info(f"modify_knowledge_direct_update time: {time.time() - ptime}")
        return ModifyKnowledgeResponse(
            success=True,
            message=modify_message or "知识修改完成",
            has_correction=has_correction
        )
            
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"处理知识直接更新请求失败: {str(e)}")
        logger.error(f"traceback: {tb}")
        return ModifyKnowledgeResponse(
            success=False,
            message=f"知识直接更新失败: {str(e)}"
        )

@app.post("/modify_knowledge", response_model=ModifyKnowledgeResponse)
async def modify_knowledge(request: ModifyKnowledgeRequest):
    """
    修改知识库接口
    调用modify_knowledge函数，修改知识库中的旧知识，返回修改后的QA信息列表
    """
    if not request.es_index:
        raise HTTPException(status_code=400, detail="es_index不能为空")
    
    if not request.new_query_info:
        raise HTTPException(status_code=400, detail="new_query_info不能为空")
    
    if not request.old_query_info:
        raise HTTPException(status_code=400, detail="old_query_info不能为空")
    
    try:
        ptime = time.time()
        logger.info(f"modify_knowledge params: es_index={request.es_index}, new_query_info={request.new_query_info}, old_query_info={request.old_query_info}, search_querys={request.search_querys}, write_db_id={request.write_db_id}")
        
        modify_qa_infos = MODIFY_KNOWLEDGE_HANDLE.modify_knowledge(
            es_index=request.es_index,
            new_query_info=request.new_query_info,
            old_query_info=request.old_query_info,
            search_querys=request.search_querys,
            write_db_id=request.write_db_id
        )
        
        logger.info(f"modify_knowledge time: {time.time() - ptime}, modify_qa_infos count: {len(modify_qa_infos) if modify_qa_infos else 0}")
        
        return ModifyKnowledgeResponse(
            success=True,
            message=f"成功处理 {len(modify_qa_infos) if modify_qa_infos else 0} 条知识",
            modify_qa_infos=modify_qa_infos
        )
            
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"处理知识修改请求失败: {str(e)}")
        logger.error(f"traceback: {tb}")
        return ModifyKnowledgeResponse(
            success=False,
            message=f"知识修改失败: {str(e)}",
            modify_qa_infos=None
        )

if __name__ == "__main__":
    
    pathlib.Path("./config").mkdir(exist_ok=True)
    #global SEARCH_DATA_INTERFACE 
    config_path = sys.argv[1]
    try:
        SEARCH_DATA_INTERFACE = init_config(config_path)
        MODIFY_KNOWLEDGE_HANDLE = ModifyKnowledge(SEARCH_DATA_INTERFACE)
    except:
        tb = traceback.format_exc()
        logger.error(f"init config error, config_path: {config_path}")
        logger.error(f"traceback: {tb}")
        exit(1)
    import uvicorn
    # 多进程：每个 worker 独立跑一个事件循环，独立初始化 SEARCH_DATA_INTERFACE
    # （uvicorn 用 multiprocessing spawn 拉起 worker，sys.argv 会被 preparation data 带过去，
    #  所以上面的 sys.argv[1] 在子进程里同样有效，已实测确认）。
    #
    # 为什么需要：单进程下所有 handler 都是 async def 包同步阻塞 IO，全部在事件循环上串行，
    # 吞吐恒定 ~0.78 req/s，延迟随并发线性增长（并发8 时 p50 达 10.6s）。
    # 实测 workers=4 后并发4 吞吐 2.5 倍、p50 降 67%。
    #
    # 为什么是 4：机器 8 核；实测需求峰值 1.90 req/s（10 秒窗口）、瞬时最多 3 req/s，
    # 4 个 worker 约 1.5~1.8 req/s 够用且留余量。再往上加受阿里云 ES 服务端并发天花板限制
    # （该查询形态并发 4 时约 1.87 req/s，并发 8 不再增长），加了也吃不到。
    # 内存代价：单进程 342MB → 4 worker 约 1GB。
    #
    # 回滚不需要改代码：SEARCH_SERVICE_WORKERS=1 重启即可。
    workers = int(os.environ.get("SEARCH_SERVICE_WORKERS", "4"))
    logger.info(f"启动 uvicorn，workers={workers}")
    uvicorn.run("kdb.services.retrieval.app:app", host="0.0.0.0", port=8003,
                reload=False, workers=workers) # 提交git时reload记得设为False
