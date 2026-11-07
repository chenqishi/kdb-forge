# wrapped (remote nested node wrapper)

Inputs: native node perform_request original method and arguments. Before request enforce <=48 native HTTP reads and host/service guards. Permit only GET root, HEAD three exact existing indexes, and POST exact _search or bounded native _msearch with known read plans. Original payload unchanged. Record response metadata without body or query contents; decoded response bounded 64MiB, per-request timeout15s and no retries. Return original NodeApiResponse. No scripts, scroll/PIT, profile, writes or SQL.
