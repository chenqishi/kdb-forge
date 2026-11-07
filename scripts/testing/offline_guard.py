"""Candidate-local offline boundary, installed before any test/business imports."""
import importlib.metadata
import os
from pathlib import Path
import sys
import tempfile

class OfflineBoundaryError(RuntimeError):
    """An offline test attempted external I/O or an external workspace write."""

_INSTALLED=False
_ROOTS=()
BLOCKED={}
_DENIED={'socket.connect','socket.bind','socket.sendto','socket.getaddrinfo','subprocess.Popen','os.system','os.exec','os.spawn','os.posix_spawn','os.fork','os.forkpty'}

def _inside(path):
    if isinstance(path,int):return True
    try:p=Path(os.fsdecode(path)).resolve()
    except (TypeError,ValueError):return False
    return p==Path('/dev/null') or any(p==root or root in p.parents for root in _ROOTS)

def _audit(event,args):
    deny=event in _DENIED
    if event=='open':
        mode=args[1] if len(args)>1 else None
        flags=args[2] if len(args)>2 else 0
        write=(isinstance(mode,str) and any(x in mode for x in 'wax+')) or (isinstance(flags,int) and bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)))
        deny=write and not _inside(args[0])
    elif event in {'os.mkdir','os.remove','os.rmdir','os.chmod','os.truncate','os.utime'}:deny=not _inside(args[0])
    elif event in {'os.rename','os.link'}:deny=not _inside(args[0]) or not _inside(args[1])
    elif event=='os.symlink':deny=not _inside(args[1])
    if deny:
        BLOCKED[event]=BLOCKED.get(event,0)+1
        raise OfflineBoundaryError('Offline boundary blocked '+event)

def install(root):
    global _INSTALLED,_ROOTS
    if _INSTALLED:return
    sys.dont_write_bytecode=True
    roots=[Path(root).resolve(),Path(tempfile.gettempdir()).resolve()]
    if os.environ.get('KDB_OFFLINE_OUTPUT_DIR'):roots.append(Path(os.environ['KDB_OFFLINE_OUTPUT_DIR']).resolve())
    _ROOTS=tuple(roots);sys.addaudithook(_audit);_INSTALLED=True

def prepare_paths(root):
    root=Path(root).resolve()
    paths=[root/'src',root,root/'scripts/testing']
    sdk=root/'private/test_dependencies'
    if (sdk/'elasticsearch').is_dir():paths.insert(0,sdk)
    for path in reversed(paths):
        value=str(path)
        if value not in sys.path:sys.path.insert(0,value)
    import elasticsearch
    version=tuple(elasticsearch.__version__[:2])
    if version!=(8,17):raise RuntimeError('Offline suite requires elasticsearch8.17.x; selected '+str(elasticsearch.__version__)+' from '+str(elasticsearch.__file__)+'. Install project test dependencies in an isolated environment; do not change shared packages.')
    return {'python':sys.executable,'python_version':sys.version.split()[0],'elasticsearch':'.'.join(map(str,elasticsearch.__version__)),'sdk_source':str(Path(elasticsearch.__file__).resolve()),'sdk_scope':'test-only private SDK' if sdk in Path(elasticsearch.__file__).resolve().parents else 'selected environment','network':'blocked','subprocess':'blocked'}
