# Legacy shell private defaults

Inputs: original script argv/cwd/environment; original literal api_key assignment.
Outputs: source an ignored, mode-0600 private fragment at the original assignment point. The fragment contains the same api_key assignment bytes, retaining shell quoting and expansion semantics; existing subsequent commands and exit paths remain unchanged. No key values appear in source or audit output. Missing private files cause the shell native source failure.
SQL: no direct SQL in this adapter; downstream original operations unchanged.
Scope: control_script/insert_audit_excel_image.sh, control_script/insert_audit_excel_image_hard.sh, tmp_shell/tmp.sh. These operations are not executed for audit.

Historical shell tools under control_script_bak_20250130: inline literal --password values are loaded at the same command argument position from ignored raw private files. The values contain no newlines, so command substitution removes no meaningful trailing bytes. Existing continuation, argv quoting and shell interpreter are retained.
