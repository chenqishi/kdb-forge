#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""kdb-forge HTTP 服务入口（薄 FastAPI）。

只暴露知识写入能力给 sell_agent。候选检索仍走现有 :8003/search（不在本服务）。

运行：
    KDB_FORGE_CONFIG=config/config_test.json uvicorn kdb.api.app:app --host 0.0.0.0 --port 8010
"""

from __future__ import annotations

from fastapi import FastAPI

from kdb.api.knowledge_routes import router as knowledge_router

app = FastAPI(title="kdb-forge", version="0.1.0")
app.include_router(knowledge_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "kdb-forge"}
