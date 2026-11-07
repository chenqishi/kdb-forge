"""Legacy import alias; no independent business implementation."""
from kdb.compat.entrypoints import legacy_entry
legacy_entry(__name__, 'kdb.services.forge_compat.modify.service', globals())
