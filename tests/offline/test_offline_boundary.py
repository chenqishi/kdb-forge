"""Exercise the real stdlib boundary without sending packets or starting a child."""
import socket
import subprocess
import sys
from pathlib import Path
import pytest
from offline_guard import OfflineBoundaryError
from offline_guard import prepare_paths

def test_connect_is_denied_before_network():
    with socket.socket() as connection:
        with pytest.raises(OfflineBoundaryError,match='socket.connect'):
            connection.connect(('127.0.0.1',9))

def test_dns_is_denied_before_lookup():
    with pytest.raises(OfflineBoundaryError,match='socket.getaddrinfo'):
        socket.getaddrinfo('offline-boundary.example.invalid',443)

def test_listen_bind_is_denied():
    with socket.socket() as connection:
        with pytest.raises(OfflineBoundaryError,match='socket.bind'):
            connection.bind(('127.0.0.1',0))

def test_subprocess_never_creates_marker(tmp_path):
    marker=tmp_path/'must-not-exist'
    with pytest.raises(OfflineBoundaryError,match='subprocess.Popen'):
        subprocess.run([sys.executable,'-c','from pathlib import Path; Path('+repr(str(marker))+').write_text("spawned")'],check=True)
    assert not marker.exists()

def test_only_candidate_and_temporary_writes_are_allowed(tmp_path):
    file=tmp_path/'allowed';file.write_text('fixture');assert file.read_text()=='fixture'
    with pytest.raises(OfflineBoundaryError,match='open'):
        Path('/dev/full').open('wb')

def test_selected_sdk_is_explicit_test_dependency():
    root=Path(__file__).resolve().parents[2];metadata=prepare_paths(root)
    assert metadata['elasticsearch'].startswith('8.17.')
    assert metadata['sdk_source'] and metadata['subprocess']=='blocked' and metadata['network']=='blocked'
    assert not any('/Users/' in value for value in sys.path)
