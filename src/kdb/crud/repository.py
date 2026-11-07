"""Legacy module alias for the single forge repository protocol adapter."""
from kdb.compat.entrypoints import legacy_entry
legacy_entry(__name__, 'kdb.services.forge_compat.repository', globals())
