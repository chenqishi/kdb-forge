"""Same-project exports only; no external sys.path injection or fallback core."""
from kdb.compat.layout import PROJECT_ROOT
from kdb.retrieval.engines.es_search_interface import EsSearchInterface
from kdb.retrieval.application.search_index_data_interface import gen_data_id as legacy_gen_data_id
from kdb.retrieval.application.knowledge_tools import get_from_norm_type as legacy_get_from_norm_type
from kdb.shared.clients.embedding_tools import AliEmbedding
from kdb.shared.legacy_commons.simility_tools import cosine_similarity, SimilityTools as LegacySimilityTools
from kdb.shared.text.keywords_tools import gen_keyword_by_title_content as legacy_gen_keyword_by_title_content
HAS_LEGACY_GEN_DATA_ID = True
LEGACY_ROOT = str(PROJECT_ROOT)

def build_legacy_engine(config_path=None, index_name=None, **kwargs):
    from kdb.es.engine import RoutedLegacyEngine
    return RoutedLegacyEngine(config_path=config_path, index_name=index_name, **kwargs)

def ensure_legacy_on_path(root=None):
    if root and str(root) != str(PROJECT_ROOT):
        raise ValueError("external legacy workspaces are not part of the unified runtime")
    return str(PROJECT_ROOT)

def load_legacy_search_interface():
    return EsSearchInterface
