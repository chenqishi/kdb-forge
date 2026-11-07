# Historical incident tools

`drain_bol.py` retains the incident response source for provenance. It stops tasks and soft-deletes knowledge and reads incident-specific absolute paths. It is outside the production import chain and must not be executed or imported for smoke. Original source remains in the protected snapshot.
