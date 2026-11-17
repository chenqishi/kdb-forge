"""Complete business ontology documents, independent of ES and HTTP."""
from .errors import OntologyError
from .models import OntologyDocument

__all__ = ["OntologyDocument", "OntologyError"]
