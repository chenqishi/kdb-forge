"""Public retrieval-only FastAPI application.

The write API continues to run in ``kdb.api.app`` on its private service port.
"""

from __future__ import annotations

from fastapi import FastAPI

from kdb.api.search_routes import router as search_router

app = FastAPI(title="kdb-forge-retrieval", version="0.1.0")
app.include_router(search_router)


@app.get("/health")
def health() -> dict:
    """Return process health without requiring retrieval credentials."""
    return {"status": "ok", "service": "kdb-forge-retrieval"}
