"""Public forge service module alias; one protocol adapter and published core."""
from kdb.compat.entrypoints import legacy_entry
legacy_entry(__name__, 'kdb.services.forge_compat.adapter', globals())
