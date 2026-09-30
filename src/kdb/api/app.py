#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""kdb-forge HTTP 服务入口（薄 FastAPI）。

提供 ES8.17 检索 `/search`、`/web_search` 与知识写入路由；检索路由需要独立 HTTP Basic 认证。

运行：
    KDB_FORGE_CONFIG=config/config_search_runtime.local.json uvicorn kdb.api.app:app --host 127.0.0.1 --port 8012
"""

from __future__ import annotations

from fastapi import FastAPI

from kdb.api.knowledge_routes import router as knowledge_router
from kdb.api.search_routes import router as search_router

app = FastAPI(title="kdb-forge", version="0.1.0")
app.include_router(knowledge_router)
app.include_router(search_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "kdb-forge"}
