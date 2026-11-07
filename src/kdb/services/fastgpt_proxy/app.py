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
from kdb.shared.config.private_values import private_value as _private_value
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
from pydantic import BaseModel
import httpx
import json
from typing import List, Dict, Optional, Union
import asyncio
import pathlib

# 在 app = FastAPI() 之前添加全局配置
def init_config(config_path: str = "./config/config.json") -> dict:
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.warning(f"配置文件 {config_path} 不存在，使用默认配置")
        return {"knowledge_base_url": "http://120.79.121.72:4000/api/v1/chat/completions"}
    except json.JSONDecodeError:
        logging.error(f"配置文件 {config_path} 格式错误")
        raise

# 全局配置
CONFIG = init_config()

app = FastAPI()

class SearchRequest(BaseModel):
    text: str
    top_k: int = 1000
    score_threshold: float = -1
    api_key: str = _private_value('7651402af9aa2029f6e02e2f')

class SearchResult(BaseModel):
    q: str
    a: Optional[str] = None
    score: float

class SearchResponse(BaseModel):
    results: List[SearchResult]

async def query_remote_service(text: str, api_key=_private_value('7651402af9aa2029f6e02e2f')) -> Dict:
    url = CONFIG["knowledge_base_url"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "stream": False,
        "detail": True,
        "messages": [
            {
                "role": "user",
                "content": text
            }
        ]
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)
    
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="远程服务请求失败")
    
    return response.json()

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    if not request.text:
        raise HTTPException(status_code=400, detail="文本参数不能为空")
    
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            raw_result = await query_remote_service(request.text, request.api_key)
            
            quote_list = None
            for one_data in raw_result["responseData"]:
                if "quoteList" in one_data:
                    quote_list = one_data["quoteList"]
                    break
            if quote_list is None:
                logging.error("no quote list found in raw result")
                retry_count += 1
                if retry_count == max_retries:
                    logging.error("no quote list found in raw result")
                    return SearchResponse(results=[SearchResult(q="检索结果错误", score=0.0)])
                continue
            
            results = []
            for quote in quote_list:
                embedding_score = next((score["value"] for score in quote["score"] if score["type"] == "embedding"), None)
                if embedding_score is not None:
                    results.append(SearchResult(q=quote["q"], a=quote.get("a", None), score=embedding_score))
            
            # 按 score_threshold 过滤
            filtered_results = [r for r in results if r.score > request.score_threshold]
            
            # 按 score 排序并取 top_k
            sorted_results = sorted(filtered_results, key=lambda x: x.score, reverse=True)[:request.top_k]
            
            return SearchResponse(results=sorted_results)
            
        except Exception as e:
            tb = traceback.format_exc()
            logging.error('traceback:\n{}'.format(tb))
            logging.error('raw result is %s', raw_result if 'raw_result' in locals() else 'None')
            retry_count += 1
            if retry_count == max_retries:
                return SearchResponse(results=[SearchResult(q="检索结果错误", score=0.0)])
            await asyncio.sleep(1)  # 重试前等待1秒

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')    
    pathlib.Path("./config").mkdir(exist_ok=True)
    import uvicorn
    uvicorn.run("knowledge_database_search:app", host="0.0.0.0", port=8000, reload=True)
