# wayfair_takeover_verify.analyze

Read-only local acceptance analysis. Inputs: preserved Claude manifests, exported ES records, downloaded production artifacts, local update DOCX, and old object URLs from the preserved mapping. Outputs: new evidence JSON/CSV/text only under the takeover directory. No production mutation, audit decision, task submission or SQL.

`norm(text)` removes whitespace for literal coverage comparison. `doc_text(path)` reads Word XML text nodes without changing the DOCX. `download_old(row)` fetches an old mapped DOCX with HTTP GET only, reuses existing sample files, extracts text and reports errors without losing evidence. Content-ID reconstruction follows existing `gen_data_id` and multimodal join semantics; duplicate quality labels are skipped exactly as insertion does. Page/block substring coverage is a diagnostic, not semantic approval. Source tail HTML detection is a candidate screen requiring inspection.
