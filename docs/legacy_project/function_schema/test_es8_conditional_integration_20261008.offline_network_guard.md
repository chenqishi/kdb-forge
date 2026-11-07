# offline_network_guard

Inputs/Outputs: Autouse scoped socket.connect and requests.Session.request denial; HTTP ASGI in-process transport remains available. Return no network or model/SQL writes; restore monkeypatch after each test.
SQL and persistent side effects: none.
