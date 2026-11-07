# ReadClient.__init__

Inputs: approved ES8 provider config and immutable run state. Outputs: per-worker persistent HTTP(S) connection; existing TLS verify option honored, no installed client changes. SQL/side effects: no connection until read; no writes, no secrets emitted.
