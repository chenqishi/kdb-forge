"""Reused old-project offline ES/query boundary; no actual ES/model requests."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/es8_conditional_boundary_20261008.py')
import copy
import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import Mock
import numpy as np
from knowledge_interface_tools.es8_client_router import IndexClientRouter
from knowledge_interface_tools.es8_search_interface import EsSearchInterfaceES8
from knowledge_interface_tools.es_search_interface import EsSearchInterface, EsSearchInterfaceOri
from knowledge_interface_tools import search_index_data_interface as business_module
class Indices:
    def __init__(self, mapping=None, exists=True):
        self.mapping = mapping or {}
        self.exists_value = exists
        self.put_mappings = []

    def exists(self, **kwargs):
        return self.exists_value

    def create(self, **kwargs):
        self.exists_value = True
        self.mapping = {kwargs["index"]: {"mappings": kwargs["mappings"]}}
        return {"acknowledged": True}

    def get_mapping(self, **kwargs):
        return self.mapping

    def put_mapping(self, **kwargs):
        self.put_mappings.append(kwargs)
        return {"acknowledged": True}


class Client:
    def __init__(self, name, responses=None, mapping=None):
        self.name = name
        self.indices = Indices(mapping=mapping)
        self.responses = list(responses or [])
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        if self.responses:
            return self.responses.pop(0)
        index = str(kwargs["index"]).split(",")[0]
        return {
            "_shards": {"failed": 0},
            "hits": {"total": {"value": 0}, "hits": []},
            "_index": index,
        }

    def open_point_in_time(self, **kwargs):
        self.calls.append(("open_point_in_time", kwargs))
        return {"id": "pit-1"}

    def close_point_in_time(self, **kwargs):
        self.calls.append(("close_point_in_time", kwargs))
        return {"succeeded": True}

    def count(self, **kwargs):
        self.calls.append(("count", kwargs))
        return {"count": 0, "_shards": {"failed": 0}}

    def update(self, **kwargs):
        self.calls.append(("update", kwargs))
        return {"result": "created"}

    def index(self, **kwargs):
        self.calls.append(("index", kwargs))
        return {"result": "created"}

    def delete(self, **kwargs):
        self.calls.append(("delete", kwargs))
        return {"result": "deleted"}


def make_engine(clients, *, auto_update_mapping=False, ensure_index=False, routes=None, vector_fields=None):
    routes = routes or {"a": "serverless", "b": "paas", "c": "serverless"}

    def factory(config):
        return clients[config["hosts"][0]]

    router = IndexClientRouter(
        config={
            "default_provider": "serverless",
            "providers": {"serverless": {"hosts": ["serverless"]}, "paas": {"hosts": ["paas"]}},
            "index_routes": routes,
        },
        client_factory=factory,
    )
    return EsSearchInterfaceES8(
        router=router, index_name="a", vector_fields=vector_fields or {"indexes_embedding": 3},
        ensure_index=ensure_index, extra_params={"auto_update_mapping": auto_update_mapping},
    )


def values_at(source, path):
    values = [source]
    for part in path.split("."):
        if part == "keyword":
            continue
        next_values = []
        for value in values:
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and part in item:
                        next_values.append(item[part])
            elif isinstance(value, dict) and part in value:
                next_values.append(value[part])
        values = next_values
    return [item for value in values for item in (value if isinstance(value, list) else [value])]


def matches(doc, query):
    """Small deterministic ES boundary; not an ANN/BM25 quality simulation."""
    if not query or "match_all" in query:
        return True
    if "function_score" in query:
        return matches(doc, query["function_score"].get("query"))
    if "ids" in query:
        return doc["_id"] in query["ids"]["values"]
    if "term" in query or "terms" in query:
        kind = "term" if "term" in query else "terms"
        field, expected = next(iter(query[kind].items()))
        values = [doc["_id"]] if field == "_id" else values_at(doc["_source"], field)
        wanted = expected if kind == "terms" else [expected]
        return any(value in wanted for value in values)
    if "bool" in query:
        body = query["bool"]
        required = body.get("must", []) + body.get("filter", [])
        excluded = body.get("must_not", [])
        should = body.get("should", [])
        minimum = body.get("minimum_should_match", 0 if required else int(bool(should)))
        return all(matches(doc, item) for item in required) and not any(matches(doc, item) for item in excluded) and sum(matches(doc, item) for item in should) >= minimum
    if "nested" in query:
        path = query["nested"]["path"]
        return bool(doc["_source"].get(path))
    if "exists" in query:
        return bool(values_at(doc["_source"], query["exists"]["field"]))
    # The fixture deliberately does not model linguistic relevance.
    return True


def order_docs(docs, sort):
    """Independent stable multi-key reference, using Python field sorting."""
    out = list(docs)
    specs = sort if isinstance(sort, list) else [sort] if sort is not None else ["_score"]
    for spec in reversed(specs):
        field, options = (spec, "desc" if spec == "_score" else "asc") if isinstance(spec, str) else next(iter(spec.items()))
        direction = options.get("order", "asc") if isinstance(options, dict) else options
        null_position = options.get("missing", "_last") if isinstance(options, dict) else "_last"
        # Dictionary .get avoids fabricating values for a missing field.
        keyed = [(doc["_score"] if field == "_score" else doc["_source"].get(field), doc) for doc in out]
        missing = [doc for value, doc in keyed if value is None]
        present = [doc for value, doc in sorted((item for item in keyed if item[0] is not None), key=lambda item: item[0], reverse=direction == "desc")]
        out = missing + present if null_position == "_first" else present + missing
    return out


def filter_source(source, option=None, excludes=()):
    source = copy.deepcopy(source)
    if option is False:
        return None
    includes = option.get("includes") if isinstance(option, dict) else option if isinstance(option, list) else None
    excludes = list(excludes) + (option.get("excludes", []) if isinstance(option, dict) else [])
    if includes:
        source = {key: value for key, value in source.items() if key in includes or any(field.startswith(key + ".") for field in includes)}
    for field in excludes:
        parts = field.split(".")
        if len(parts) == 1:
            source.pop(field, None)
        elif isinstance(source.get(parts[0]), list):
            for item in source[parts[0]]:
                item.pop(parts[1], None)
        elif isinstance(source.get(parts[0]), dict):
            source[parts[0]].pop(parts[1], None)
    return source


def response(hits=(), total=None, relation="eq", failed=0):
    return {"_shards": {"total": 1, "successful": int(not failed), "failed": failed},
            "hits": {"total": {"value": len(hits) if total is None else total, "relation": relation}, "hits": list(hits)}}


class BodyClient:
    def __init__(self, docs=()):
        self.docs = copy.deepcopy(list(docs))
        self.calls = []
        self.error = None
        self.responses = []
        self.pit_indexes = "a"
        self.pit_counter = 0
        self.closed_pits = []
        self.closed_scrolls = []
        self.indices = types.SimpleNamespace(get_mapping=Mock(return_value={
            name: {"mappings": {}} for name in ("a", "b", "c")}))

    def search(self, **kwargs):
        self.calls.append(("search", copy.deepcopy(kwargs)))
        if self.error:
            raise self.error
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return copy.deepcopy(item)
        body = kwargs.get("body", kwargs)
        names = kwargs.get("index", self.pit_indexes)
        names = names.split(",") if isinstance(names, str) else names
        docs = [copy.deepcopy(doc) for doc in self.docs if doc["_index"] in names and matches(doc, body.get("query"))]
        if body.get("min_score") is not None:
            docs = [doc for doc in docs if doc["_score"] >= body["min_score"]]
        docs = order_docs(docs, body.get("sort"))
        sort = body.get("sort")
        for doc in docs:
            if sort:
                specs = sort if isinstance(sort, list) else [sort]
                doc["sort"] = [doc["_score"] if (field := spec if isinstance(spec, str) else next(iter(spec))) == "_score" else doc["_source"].get(field) for spec in specs]
        if body.get("search_after") is not None:
            positions = [n for n, doc in enumerate(docs) if doc.get("sort") == body["search_after"]]
            docs = docs[positions[0] + 1:] if positions else docs
        offset, size = body.get("from_", body.get("from", 0)), body.get("size", 10)
        selected = docs[offset:offset + size]
        for doc in selected:
            original = doc["_source"]
            # Wire inner_hits are derived from fixture source and the actual
            # request filter. They do not model approximate neighbor quality.
            stack = [body.get("query", {})]
            while stack:
                node = stack.pop()
                if isinstance(node, list):
                    stack.extend(node)
                elif isinstance(node, dict):
                    if "nested" in node and "inner_hits" in node["nested"]:
                        nested = node["nested"]
                        path, spec = nested["path"], nested["inner_hits"]
                        inner = []
                        for n, item in enumerate(original.get(path, [])[:spec.get("size", 3)]):
                            inner_source = {key: copy.deepcopy(value) for key, value in item.items() if f"{path}.{key}" in spec["_source"]["includes"]}
                            inner.append({"_nested": {"field": path, "offset": n}, "_source": inner_source})
                        doc.setdefault("inner_hits", {})[spec["name"]] = {"hits": {"hits": inner}}
                    stack.extend(node.values())
            src = filter_source(original, body.get("source", body.get("_source")), body.get("source_excludes", []))
            if src is None:
                doc.pop("_source")
            else:
                doc["_source"] = src
        return response(selected, total=len(docs))

    def update(self, **kwargs):
        self.calls.append(("update", copy.deepcopy(kwargs)))
        if self.error:
            raise self.error
        return {"result": "updated"}

    def msearch(self, body):
        return {"responses": [self.search(index=body[i]["index"], body=body[i + 1]) for i in range(0, len(body), 2)]}

    def index(self, **kwargs):
        self.calls.append(("index", copy.deepcopy(kwargs)))
        if self.error:
            raise self.error
        return {"result": "created"}

    def update_by_query(self, **kwargs):
        self.calls.append(("update_by_query", copy.deepcopy(kwargs)))
        if self.error:
            raise self.error
        if getattr(self, "simulate_conflict", False):
            if kwargs.get("conflicts") == "proceed":
                return {"updated": 0, "total": 1, "version_conflicts": 1, "failures": []}
            raise RuntimeError("synthetic version conflict abort")
        return {"updated": 1, "total": 1, "version_conflicts": 0, "failures": []}

    def count(self, **kwargs):
        self.calls.append(("count", copy.deepcopy(kwargs)))
        return {"count": 1, "_shards": {"failed": 0}}

    def get(self, **kwargs):
        self.calls.append(("get", copy.deepcopy(kwargs)))
        return {"_id": kwargs["id"], "_source": copy.deepcopy(self.docs[0]["_source"])}

    def delete(self, **kwargs):
        self.calls.append(("delete", copy.deepcopy(kwargs)))
        return {"result": "deleted"}

    def open_point_in_time(self, **kwargs):
        self.pit_indexes = kwargs["index"]
        self.calls.append(("open_point_in_time", copy.deepcopy(kwargs)))
        return {"id": "pit-1"}

    def close_point_in_time(self, **kwargs):
        self.closed_pits.append(kwargs["id"])
        return {"succeeded": True}

    def scroll(self, **kwargs):
        self.calls.append(("scroll", copy.deepcopy(kwargs)))
        return response([])

    def clear_scroll(self, **kwargs):
        self.closed_scrolls.append(kwargs["scroll_id"])
        return {"succeeded": True}

    def close(self):
        pass


class EmbeddingStub:
    def text2embedding(self, text):
        return np.asarray([1.0, 0.0, 0.0])


def make_business(monkeypatch, tmp_path, clients, old=None):
    # Real constructors and factory handoff; only external clients/tools change.
    monkeypatch.setattr(IndexClientRouter, "_create_client", staticmethod(lambda cfg: clients[cfg["hosts"][0]]))
    monkeypatch.setattr(business_module, "EmbeddingTools", lambda *_: EmbeddingStub())
    monkeypatch.setattr(business_module.simility_tools, "SimilityTools", lambda *_: object())
    monkeypatch.setattr(business_module, "gen_keyword_by_title_content", lambda *_args, **_kwargs: [{"word": "fixture"}])
    es_path = tmp_path / "es.json"
    es_path.write_text(json.dumps({"es_version": "8.17", "index_name": "a", "vector_fields": {"indexes_embedding": 3},
                                   "default_provider": "serverless", "providers": {"serverless": {"hosts": ["serverless"]}, "paas": {"hosts": ["paas"]}},
                                   "index_routes": {"a": "serverless", "b": "paas", "c": "serverless"},
                                   "extra_params": {"ensure_index_on_init": False, "auto_update_mapping": False}}))
    cfg_path = tmp_path / "business.json"
    cfg_path.write_text(json.dumps({"search_engine_config_path": str(es_path), "multimodal_prefix": "https://fixture.invalid/", "check_duplicate": False}))
    iface = business_module.SearchDataInterface(search_engine=old, config_path=str(cfg_path))
    if old is None:
        assert isinstance(iface.engine, EsSearchInterface)
        assert isinstance(iface.engine._impl, EsSearchInterfaceES8)
    return iface


def data_rows(n=6):
    return [{"_index": name, "_id": str(i), "_score": float(i % 7),
             "_source": {"rank": i, "group": i % 3, "title": "fixture", "content": "content", "del_flag": 0,
                         "data_type": "qa", "audit_result": 2, "quality_level": "high", "ext_info": {"from_file_name": "f.pdf"},
                         "indexes": [{"text": "fixture", "embedding": [1, 0, 0]}],
                         "title_embedding": [0, 1, 0], "content_embedding": [1, 0, 0], "synonyms_title": ["fixture"]}}
            for name in ["a", "b", "c"] for i in range(n)]


def service_module(monkeypatch, iface):
    # These handlers never use ModifyKnowledge. Replace only its DB/LLM boundary.
    external = types.ModuleType("knowledge_clear_tool.modify_knowledge")
    external.ModifyKnowledge = object
    monkeypatch.setitem(sys.modules, external.__name__, external)
    path = Path(__legacy_source_file__).resolve().parents[1] / "knowledge_database_search_service/src/knowledge_database_search_es.py"
    spec = importlib.util.spec_from_file_location("_es817_contract_service", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    module.SEARCH_DATA_INTERFACE = iface
    return module
