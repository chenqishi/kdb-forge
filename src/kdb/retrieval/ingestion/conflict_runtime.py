"""Configuration and construction shared by the CLI and existing service adapters."""
import json
import os
from pathlib import Path

from kdb.shared.config.paths import project_path


def load_config(path=None):
    path = path or os.environ.get('KDB_DEDUP_CONFIG')
    if not path:
        raise ValueError('configure KDB_DEDUP_CONFIG or provide a dedup config path')
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('dedup configuration exceeds 1 MiB')
    with path.open(encoding='utf-8') as handle:
        config = json.load(handle)
    for name in ('llm', 'rerank'):
        settings = config.get(name) or {}
        if settings.get('api_key_env'):
            settings['api_key'] = os.environ.get(settings.pop('api_key_env'))
        config[name] = settings
    return config


def build_job(index, *, config_path=None, search_config_path=None, journal=None, interface=None):
    from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
    from kdb.retrieval.ingestion.conflict_store import KnowledgeStore
    from kdb.retrieval.ingestion.conflict_models import ModelGateway
    from kdb.retrieval.ingestion.conflict_jobs import DedupJob
    config = load_config(config_path)
    search_path = search_config_path or config.get('search_config_path')
    if interface is None:
        if not search_path:
            raise ValueError('search_config_path is required')
        interface = SearchDataInterface(config_path=search_path)
    store = KnowledgeStore(interface, index, journal or project_path('private', 'dedup', index + '.journal.jsonl'))
    return DedupJob(store, ModelGateway(config), **config.get('strategy', {}))
