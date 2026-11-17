from copy import deepcopy
from datetime import datetime
from uuid import uuid4

import pytest

from kdb.retrieval.ontology.errors import OntologyError, ONTOLOGY_NAME_CONFLICT
from kdb.retrieval.ontology.repository import OntologyRow
from kdb.retrieval.ontology.service import OntologyService


@pytest.fixture
def doc():
    return {"schema_version": "1.0", "name": "最小示例", "object_types": [
        {"name": "消息", "identity": ["消息ID"], "attributes": [{"name": "消息ID", "data_type": "string"}]}]}


class MemoryRepository:
    """A service/HTTP test boundary, never a production persistence fallback."""
    def __init__(self):
        self.rows = {}
        self.calls = []

    def _conflict(self, vd, exclude=None):
        for row in self.rows.values():
            if not row.del_flag and row.ontology_id != exclude and (row.client, row.product, row.name) == (vd.client, vd.product, vd.name):
                raise OntologyError(ONTOLOGY_NAME_CONFLICT, 409, "duplicate", [{"existing_ontology_id": row.ontology_id, "status": row.status, "revision": row.revision}])

    def insert_if_absent(self, vd, status):
        self.calls.append(("insert", vd, status))
        self._conflict(vd)
        oid = uuid4().hex
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.rows[oid] = OntologyRow(oid, vd.client, vd.product, vd.name, vd.alias_name, vd.description,
                                     status, 1, now, now, 0, deepcopy(vd.document))
        return oid

    def get_by_id(self, oid):
        self.calls.append(("get", oid))
        return deepcopy(self.rows.get(oid))

    def probe(self, oid):
        return self.get_by_id(oid)

    def replace_document(self, oid, revision, vd, status):
        self.calls.append(("replace", oid))
        self._conflict(vd, oid)
        row = self.rows.get(oid)
        if row is None or row.del_flag or row.revision != revision:
            return 0
        row.name, row.alias_name, row.description = vd.name, vd.alias_name, vd.description
        row.data_json = deepcopy(vd.document)
        row.status = status
        row.revision += 1
        return 1

    def update_status(self, oid, revision, status):
        row = self.rows.get(oid)
        if row is None or row.del_flag or row.revision != revision:
            return 0
        row.status = status
        row.revision += 1
        return 1

    def soft_delete(self, oid, revision):
        row = self.rows.get(oid)
        if row is None or row.del_flag or (revision is not None and row.revision != revision):
            return 0
        row.del_flag = 1
        row.revision += 1
        return 1

    def resolve(self, client, product, name):
        self.calls.append(("resolve", client, product, name))
        rows = [r for r in self.rows.values() if not r.del_flag and r.status == "active"
                and r.client in (client, "") and (r.product in (product, "") or (client and not product and r.client == client))
                and (not name or r.name == name)]
        def rank(r):
            return (2 * bool(client and r.client == client) + bool(product and r.product == product), not r.product, r.update_time)
        return deepcopy(max(rows, key=rank)) if rows else None

    def list(self, **filters):
        self.calls.append(("list", filters))
        rows = [r for r in self.rows.values() if (filters["include_deleted"] or not r.del_flag)
                and all(filters[key] is None or getattr(r, key) == filters[key] for key in ("client", "product", "status"))]
        start = filters["offset"]
        return deepcopy(rows[start:start + filters["limit"]]), len(rows)


@pytest.fixture
def repo():
    return MemoryRepository()


@pytest.fixture
def service(repo):
    return OntologyService(repo)
