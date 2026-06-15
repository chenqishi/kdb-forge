"""pytest fixtures（集成测试）。

接线：把 rebuild 的 src/ 与旧项目根加入 sys.path（无需安装即可 `import kdb` 与旧模块）。
所有测试针对独立索引 `test_case`，复用旧 ES 连接与 DashScope embedding。
"""

import json
import os
import sys

import pytest

# ---- sys.path 接线（不依赖 run_tests.sh / 安装） ----
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# 旧项目根（kdb.legacy_bridge 也会注入，这里提前确保 conftest 内 import 可用）
os.environ.setdefault(
    "KDB_LEGACY_ROOT", "/Users/chenqishi/stone_fish/knowledge_database_builder"
)

from kdb.config.loader import load_config  # noqa: E402
from kdb.crud.repository import KnowledgeRepository  # noqa: E402
from kdb.crud.service import KnowledgeService  # noqa: E402
from kdb.embedding.client import build_embedding_client  # noqa: E402
from kdb.legacy_bridge import build_legacy_engine, load_legacy_search_interface  # noqa: E402

CONFIG_PATH = os.path.join(_ROOT, "config", "config_test.json")


@pytest.fixture(scope="session")
def cfg():
    if not os.path.exists(CONFIG_PATH):
        pytest.skip(f"缺少 {CONFIG_PATH}（从 config_test.json.example 复制并填路径）")
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="session")
def test_index(cfg):
    return cfg.get("test_index_name", "test_case")


@pytest.fixture(scope="session")
def embedding_client(cfg):
    return build_embedding_client(cfg["embedding_config_path"])


@pytest.fixture(scope="session")
def engine(cfg, test_index):
    # 构造旧 EsSearchInterface（index_name 覆盖为 test_case）。
    # 其 __init__ 会连接 ES 并 ensure_index(test_case)，因此这也验证了连通性。
    return build_legacy_engine(config_path=cfg["engine_config_path"], index_name=test_index)


@pytest.fixture(scope="session")
def repo(engine, test_index):
    return KnowledgeRepository(engine=engine, default_index=test_index)


@pytest.fixture(scope="session")
def multimodal_prefix(cfg):
    """从 cfg 引用的旧 search config 中读 multimodal_prefix；缺失返回空串。
    与 KnowledgeService.from_config 的读取逻辑保持一致。
    """
    path = cfg.get("legacy_search_config_path")
    if not path or not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("multimodal_prefix", "") or ""


@pytest.fixture(scope="session")
def service(repo, embedding_client, test_index, multimodal_prefix):
    return KnowledgeService(
        repo,
        embedding_client,
        default_index=test_index,
        multimodal_prefix=multimodal_prefix,
    )


@pytest.fixture(scope="session")
def legacy_interface(cfg, test_index, embedding_client):
    """旧 SearchDataInterface（仅对齐测试用）。共享同一 embedding 实例以消除向量分叉。"""
    legacy = load_legacy_search_interface(
        cfg["legacy_search_config_path"], index_name=test_index
    )
    legacy.embedding_tools = embedding_client  # 与新实现共享同一 embedding
    legacy.check_duplicate = False  # 关闭去重的非确定性 / 外部调用
    return legacy


@pytest.fixture(scope="session", autouse=True)
def ensure_test_index(repo, test_index):
    """确保 test_case 索引存在（用权威 mapping）并预热刷新一次，降低首测搜索可见延迟。"""
    repo.ensure_index(test_index)
    # 预热：把可能挂起在 translog/缓存里的状态落盘到可搜索段
    repo._force_refresh(test_index)


@pytest.fixture()
def cleanup_ids(repo, test_index):
    """收集测试写入的 _id，测试结束后删除，避免污染 test_case 索引。"""
    ids = []
    yield ids
    for _id in ids:
        try:
            repo.delete(_id, index_name=test_index, refresh=True)
        except Exception:
            pass


# ---- 工具：应对 Aliyun ES serverless 在高频写后 get-by-id 偶发返回旧版本/None 的最终一致性窗口 ----
import time as _time  # noqa: E402


def wait_for(predicate, timeout: float = 10.0, interval: float = 0.3):
    """轮询 predicate，True 则返回；超时抛 AssertionError。返回 predicate 的真值。"""
    deadline = _time.time() + timeout
    last = None
    while _time.time() < deadline:
        last = predicate()
        if last:
            return last
        _time.sleep(interval)
    raise AssertionError(f"wait_for 超时（{timeout}s），最后一次返回值: {last!r}")


def wait_for_present(repo, _id, index_name, timeout: float = 10.0):
    """等待文档对 get 可见（应对 serverless 写入可见延迟）。"""
    def _check():
        d = repo.get(_id, index_name=index_name)
        return d if d is not None else False
    return wait_for(_check, timeout=timeout)


def wait_for_absent(repo, _id, index_name, timeout: float = 10.0):
    """等待文档对 get 不可见（应对 serverless 删除可见延迟）。"""
    def _check():
        return repo.get(_id, index_name=index_name) is None
    return wait_for(_check, timeout=timeout)


def wait_for_search_hit(repo, _id, query_dict, index_name, size=10, timeout: float = 20.0):
    """等待 search_multi 能命中目标 _id（应对搜索 refresh 延迟，比 get 更慢）。"""
    def _check():
        hits, _ = repo.search_multi(query_dict, index_name=index_name, size=size)
        for d in hits:
            if d.get("_id") == _id:
                return d
        return False
    return wait_for(_check, timeout=timeout)


def wait_for_field(repo, _id, field, expected, index_name, timeout: float = 10.0):
    """轮询 get-by-id 直到 stored[field] == expected（应对更新可见延迟）。"""
    def _check():
        d = repo.get(_id, index_name=index_name)
        if d is None:
            return False
        return d if d.get(field) == expected else False
    return wait_for(_check, timeout=timeout)
