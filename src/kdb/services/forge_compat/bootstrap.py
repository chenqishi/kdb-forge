"""Construct the forge protocol adapter over the current retrieval engine."""


def build_legacy_engine(config_path=None, index_name=None, **kwargs):
    """Construct the existing routed engine with unchanged caller options."""
    from kdb.services.forge_compat.engine import RoutedLegacyEngine
    return RoutedLegacyEngine(config_path=config_path, index_name=index_name, **kwargs)
