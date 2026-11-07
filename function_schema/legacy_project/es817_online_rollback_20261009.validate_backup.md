# validate_backup

Inputs: private release backup directory and its before.json. Outputs: original configuration bytes after verifying each recorded SHA256 and the actual shared legacy engine remains byte-identical. Refuse corrupt/missing backups before stopping services or replacing any configuration. No SQL or ES operations.
