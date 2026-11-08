from fastapi import HTTPException
from kdb.entrypoints.http.retrieval.models import DeleteByFileRequest
from kdb.entrypoints.http.retrieval.models import DeleteByFileResponse
from kdb.entrypoints.http.retrieval.models import DeleteRequest
from kdb.entrypoints.http.retrieval.models import DeleteResponse
from kdb.entrypoints.http.retrieval.models import FromTypeCountRequest
from kdb.entrypoints.http.retrieval.models import FromTypeCountResponse
from kdb.entrypoints.http.retrieval.models import InsertRequest
from kdb.entrypoints.http.retrieval.models import InsertResponse
from kdb.entrypoints.http.retrieval.models import ListFileNamesRequest
from kdb.entrypoints.http.retrieval.models import ListFileNamesResponse
from kdb.entrypoints.http.retrieval.models import ModifyKnowledgeRequest
from kdb.entrypoints.http.retrieval.models import ModifyKnowledgeResponse
from kdb.entrypoints.http.retrieval.models import PreviewDeleteByFileRequest
from kdb.entrypoints.http.retrieval.models import PreviewDeleteByFileResponse
from kdb.entrypoints.http.retrieval.models import SearchRequest
from kdb.entrypoints.http.retrieval.models import SearchResponse
from kdb.entrypoints.http.retrieval.models import SearchResult
from kdb.entrypoints.http.retrieval.models import UpdateByConditionRequest
from kdb.entrypoints.http.retrieval.models import UpdateByConditionResponse
from kdb.entrypoints.http.retrieval.models import ValueCollectionRequest
from kdb.entrypoints.http.retrieval.models import ValueCollectionResponse
from kdb.entrypoints.http.retrieval.models import WebSearchRequest
from kdb.entrypoints.http.retrieval.models import WebSearchResponse
from kdb.retrieval.application.queries import query_remote_service
from kdb.retrieval.application.queries import web_remote_service
from kdb.retrieval.application.writes import insert_to_service
from kdb.retrieval.application.writes import update_by_condition_service
import asyncio
import kdb.retrieval.application.runtime as runtime_state
import logging
import time
import traceback
logger = logging.getLogger('kdb.entrypoints.http.retrieval.app')

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


async def insert(request: InsertRequest):
    """
    插入数据接口
    """
    if not request.index_names:
        raise HTTPException(status_code=400, detail="index_names不能为空")
    
    try:
        ptime = time.time()
        
        # 将原始扩展信息传入处理链；后层无法恢复已漏传的请求字段。
        final_ext_info = request.get_ext_info_with_extra_fields(defined_fields=runtime_state.SEARCH_DATA_INTERFACE.doc_schema_field)
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


async def delete(request: DeleteRequest):
    """
    删除数据接口
    """
    try:
        ptime = time.time()
        success = runtime_state.SEARCH_DATA_INTERFACE.delete_data(
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
        values = runtime_state.SEARCH_DATA_INTERFACE.get_unique_values(
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


async def get_from_type_count(request: FromTypeCountRequest):
    """按原索引名精确统计high来源知识，不查询source或创建索引。"""
    if not request.index_name:
        return FromTypeCountResponse(success=True)
    try:
        if runtime_state.SEARCH_DATA_INTERFACE is None:
            raise RuntimeError("Search interface not initialized")
        count = await asyncio.to_thread(
            runtime_state.SEARCH_DATA_INTERFACE.get_from_type_count, request.index_name,
            request.from_type, request.start, request.end,
        )
        return FromTypeCountResponse(success=True, count=count)
    except Exception:
        logger.exception("get_from_type_count failed: index=%s", request.index_name)
        return FromTypeCountResponse(success=False, message="获取来源知识数量失败")


async def list_file_names(request: ListFileNamesRequest):
    """列出未删除知识的来源文件，可选按 from_type_norm 筛选。

    文件列表的来源范围不代表删除权限，删除接口仍保留原来源白名单。
    """
    try:
        ptime = time.time()
        values = runtime_state.SEARCH_DATA_INTERFACE.list_file_names(
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


async def preview_delete_by_file(request: PreviewDeleteByFileRequest):
    """预览按文件名删除会命中哪些知识。只读，必须先调这个才能删。"""
    if not request.file_names:
        raise HTTPException(status_code=400, detail="file_names 不能为空")
    if request.match_mode not in ("exact", "fuzzy"):
        raise HTTPException(status_code=400, detail="match_mode 只能是 exact 或 fuzzy")
    try:
        ptime = time.time()
        r = runtime_state.SEARCH_DATA_INTERFACE.preview_delete_by_file(
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


async def delete_by_file(request: DeleteByFileRequest):
    """按来源文件名批量软删除知识（qa + segment）。删前自动写快照，可回滚。"""
    if not request.file_names:
        raise HTTPException(status_code=400, detail="file_names 不能为空")
    if request.match_mode not in ("exact", "fuzzy"):
        raise HTTPException(status_code=400, detail="match_mode 只能是 exact 或 fuzzy")
    try:
        ptime = time.time()
        r = runtime_state.SEARCH_DATA_INTERFACE.delete_by_file(
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
        
        modify_message, has_correction = runtime_state.MODIFY_KNOWLEDGE_HANDLE.modify_knowledge_direct_update(
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
        
        modify_qa_infos = runtime_state.MODIFY_KNOWLEDGE_HANDLE.modify_knowledge(
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


def register_routes(app):
    """Register the original handlers on the single entrypoint app."""
    app.post('/search', response_model=SearchResponse)(search)
    app.post('/insert', response_model=InsertResponse)(insert)
    app.post('/delete', response_model=DeleteResponse)(delete)
    app.post('/web_search', response_model=WebSearchResponse)(web_search)
    app.post('/get_value_collection', response_model=ValueCollectionResponse)(get_value_collection)
    app.post('/get_from_type_count', response_model=FromTypeCountResponse)(get_from_type_count)
    app.post('/list_file_names', response_model=ListFileNamesResponse)(list_file_names)
    app.post('/preview_delete_by_file', response_model=PreviewDeleteByFileResponse)(preview_delete_by_file)
    app.post('/delete_by_file', response_model=DeleteByFileResponse)(delete_by_file)
    app.post('/update_by_condition', response_model=UpdateByConditionResponse)(update_by_condition)
    app.post('/modify_knowledge_direct_update', response_model=ModifyKnowledgeResponse)(modify_knowledge_direct_update)
    app.post('/modify_knowledge', response_model=ModifyKnowledgeResponse)(modify_knowledge)
