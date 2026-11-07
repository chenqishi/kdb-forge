"""Guard ordinary pytest collection; supported shell runner guards even --noconftest."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'scripts/testing'))
from offline_guard import install,prepare_paths
install(ROOT)
OFFLINE_TEST_METADATA=prepare_paths(ROOT)
