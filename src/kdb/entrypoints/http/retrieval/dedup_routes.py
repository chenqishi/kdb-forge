"""Opt-in stateless MCP transport on the existing retrieval service."""
import hmac
import json
import os
from pathlib import Path

from fastapi import HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool

from kdb.retrieval.application.dedup_tools import DedupHarness
from kdb.retrieval.ingestion.conflict_runtime import build_job
import kdb.retrieval.application.runtime as runtime_state


def register_dedup_routes(app, *, config=None, job_factory=None):
    if config is None:
        path = os.environ.get('KDB_DEDUP_HARNESS_CONFIG')
        if not path:
            return
        path = Path(path)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('harness config exceeds 1 MiB')
        with path.open(encoding='utf-8') as handle:
            config = json.load(handle)
    if config.get('enabled', False) is not True:
        return
    if job_factory is None:
        job_factory = lambda index: build_job(index, config_path=config.get('dedup_config_path'),
                                              interface=runtime_state.SEARCH_DATA_INTERFACE)
    harness = DedupHarness(config, job_factory)

    def authenticate(request):
        origin = request.headers.get('origin')
        if origin and origin not in config.get('allowed_origins', []):
            raise HTTPException(403, 'origin not allowed')
        header = request.headers.get('authorization', '')
        token = header[7:] if header.startswith('Bearer ') else ''
        for principal in config.get('principals', []):
            expected = os.environ.get(principal.get('token_env', ''), '')
            if expected and token and hmac.compare_digest(token, expected):
                try:
                    harness.authorize(principal)
                except PermissionError as exc:
                    raise HTTPException(403, str(exc)) from exc
                return principal
        raise HTTPException(403, 'admin leader authentication required')

    @app.post('/knowledge_dedup/mcp', include_in_schema=False)
    async def mcp(request: Request):
        principal = authenticate(request)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 2 * 1024 * 1024:
                raise HTTPException(413, 'tool request exceeds 2 MiB')
        try:
            message = json.loads(body)
        except (ValueError, UnicodeError):
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'invalid JSON'}}
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'invalid request'}}
        method, identifier = message['method'], message.get('id')
        if method.startswith('notifications/') and 'id' not in message:
            return Response(status_code=202)
        if method == 'initialize':
            result = {'protocolVersion': '2025-03-26', 'capabilities': {'tools': {'listChanged': False}},
                      'serverInfo': {'name': 'kdb-knowledge-dedup', 'version': '1.0.0'}}
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = {'tools': harness.list_tools(principal)}
        elif method == 'tools/call':
            params = message.get('params') or {}
            try:
                output = await run_in_threadpool(harness.call, params.get('name'), params.get('arguments', {}), principal)
                failed = output.get('status') == 'failed'
                result = {'content': [{'type': 'text', 'text': json.dumps(output, ensure_ascii=False)}], 'isError': failed}
            except Exception as exc:
                result = {'content': [{'type': 'text', 'text': json.dumps({'error': str(exc)}, ensure_ascii=False)}], 'isError': True}
        else:
            return {'jsonrpc': '2.0', 'id': identifier, 'error': {'code': -32601, 'message': 'method not found'}}
        return {'jsonrpc': '2.0', 'id': identifier, 'result': result}
