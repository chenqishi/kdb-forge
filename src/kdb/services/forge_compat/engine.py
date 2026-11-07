"""Original forge engine name with its independent strict-count wire protocol.

All retrieval, routing, indexing and non-strict counting use the published engine.
"""
from kdb.retrieval.engines.es8_search_interface import EsSearchInterfaceES8
from kdb.retrieval.engines.es_count_utils import complete_count


class RoutedLegacyEngine(EsSearchInterfaceES8):
    def count_by_query(self, index_name, query, require_complete=False):
        if not require_complete:
            return super().count_by_query(index_name, query, require_complete=False)
        response = self.get_client_by_index(index_name).count(
            index=index_name,
            query=query,
            ignore_unavailable=False,
            allow_no_indices=False,
            expand_wildcards="none",
        )
        return complete_count(response)
