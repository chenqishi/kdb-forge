"""Elasticsearch 8.x client routing and legacy search-engine adapter."""

from kdb.es.client_router import IndexClientRouter
from kdb.es.engine import RoutedLegacyEngine

__all__ = ["IndexClientRouter", "RoutedLegacyEngine"]
