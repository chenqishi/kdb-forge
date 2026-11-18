"""Real MySQL verification in an explicitly configured disposable test database.

Run directly with Python (unittest), not via the mandatory offline pytest runner.
KDB_ONTOLOGY_TEST_MYSQL=1 and KDB_MYSQL_CONFIG pointing to a *_test/test database
are both required. Cleanup only touches names created by the individual test.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import unittest
from uuid import uuid4

from kdb.retrieval.ontology.errors import OntologyError
from kdb.retrieval.ontology.repository import OntologyRepository
from kdb.retrieval.ontology.service import OntologyService
from kdb.retrieval.ontology.validation import document_size, validate_document

ROOT = Path(__file__).resolve().parents[3]
OFFLINE = getattr(sys.modules.get("offline_guard"), "_INSTALLED", False)
ENABLED = os.environ.get("KDB_ONTOLOGY_TEST_MYSQL") == "1" and not OFFLINE


@unittest.skipUnless(ENABLED, "requires standalone runner, KDB_ONTOLOGY_TEST_MYSQL=1 and an explicit test DB")
class MySQLRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kdb.shared.database.mysql import MySQLConnector
        path = Path(os.environ["KDB_MYSQL_CONFIG"])
        if path.stat().st_size > 65536:
            raise RuntimeError("test configuration exceeds 64KB")
        config = json.loads(path.read_text())
        if not re.fullmatch(r"test|[a-z0-9_]+_test", config.get("database", "")):
            raise RuntimeError("Integration tests require database=test or a *_test database")
        cls.connector = MySQLConnector(str(path))
        conn = cls.connector.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            migration = (ROOT / "migrations/20261117_ontology.sql").read_text()
            cursor.execute(migration)
            cursor.execute(migration)  # Idempotent migration.
            upgrade = (ROOT / "migrations/20261118_ontology_review_status.sql").read_text()
            for _ in range(2):
                for statement in upgrade.split(";"):
                    if statement.strip():
                        cursor.execute(statement)
                        if cursor.with_rows:
                            cursor.fetchall()
            conn.commit()
            cursor.execute("SELECT VERSION() AS version, DATABASE() AS db, @@character_set_server AS charset, "
                           "@@session.time_zone AS time_zone, @@transaction_isolation AS isolation, @@max_connections AS max_connections")
            print("MySQL test environment: " + json.dumps(cursor.fetchone(), ensure_ascii=False))
        finally:
            cursor.close(); conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.connector._close_pool()

    def setUp(self):
        self.prefix = "ontology_it_" + uuid4().hex
        self.client = "ont_test_" + uuid4().hex
        self.repo = OntologyRepository(self.connector)
        self.service = OntologyService(self.repo)
        self.doc = {"schema_version": "1.0", "name": self.prefix, "object_types": [
            {"name": "消息", "identity": ["消息ID"], "attributes": [{"name": "消息ID", "data_type": "string"}]}]}

    def tearDown(self):
        conn = self.connector.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM dops_ontology WHERE LEFT(name, %s) = %s", (len(self.prefix), self.prefix))
            conn.commit()
        finally:
            cursor.close(); conn.close()

    def create(self, client="", product="", name=None, status="active", document=None, review_status="approved"):
        doc = deepcopy(self.doc if document is None else document)
        doc.update(client=client, product=product, name=name or self.prefix)
        meta = self.service.insert_ontology({"data_json": doc, "status": status, "review_status": review_status})["ontology"]
        self.assertNotIn("data_json", meta)
        return self.service.get_ontology(meta["ontology_id"], review_status="all")["ontology"]

    def resolve(self, client="", product="", name=None):
        return self.service.select_ontology(client, product, name or self.prefix)

    def assert_error(self, code, fn):
        with self.assertRaises(OntologyError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_D01_global_insert_and_schema(self):
        row = self.create()
        self.assertEqual(row["revision"], 1)
        self.assertEqual(self.repo.select_ontology_by_id(row["ontology_id"]).data_json, row["data_json"])
        conn = self.connector.get_connection(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SHOW INDEX FROM dops_ontology")
            indexes = cursor.fetchall()
            self.assertEqual({r["Key_name"] for r in indexes if not r["Non_unique"]}, {"PRIMARY", "uk_ontology_id"})
            self.assertTrue({"idx_scope_name", "idx_scope_status", "idx_update_time"} <= {r["Key_name"] for r in indexes})
        finally:
            cursor.close(); conn.close()

    def test_D02_business_key_conflict(self):
        first = self.create(self.client, "ecommerce")
        error = self.assert_error("ONTOLOGY_NAME_CONFLICT", lambda: self.create(self.client, "ecommerce"))
        self.assertEqual(error.details[0]["existing_ontology_id"], first["ontology_id"])

    def test_D03_repeated_delete_recreate(self):
        ids = set()
        for _ in range(3):
            row = self.create(self.client, "ecommerce")
            ids.add(row["ontology_id"])
            self.service.delete_ontology(row["ontology_id"], 1)
            repeated = self.service.delete_ontology(row["ontology_id"], 1)
            self.assertEqual(repeated["ontology"]["revision"], 2)
            self.assertEqual(repeated["message"], "本体已删除")
        self.assertEqual(len(ids), 3)

    def test_D04_inactive_reserves_key_but_does_not_resolve(self):
        self.create(self.client, "ecommerce", status="inactive")
        self.assert_error("ONTOLOGY_NAME_CONFLICT", lambda: self.create(self.client, "ecommerce"))
        self.create(self.client, "ecommerce", name=self.prefix + "other", status="inactive")
        self.assertIsNone(self.resolve(self.client, "ecommerce")["ontology"])

    def test_D05_customer_over_industry_without_merge(self):
        self.create(product="ecommerce")
        row = self.create(self.client, "ecommerce")
        resolved = self.resolve(self.client, "ecommerce")
        self.assertEqual(resolved["ontology"]["ontology_id"], row["ontology_id"])
        self.assertEqual(resolved["scope"], "client_product")
        self.assertFalse(resolved["fallback"])

    def test_D06_delete_customer_falls_back(self):
        industry = self.create(product="ecommerce")
        customer = self.create(self.client, "ecommerce")
        self.service.delete_ontology(customer["ontology_id"])
        self.assertEqual(self.resolve(self.client, "ecommerce")["ontology"]["ontology_id"], industry["ontology_id"])

    def test_D07_client_only_prefers_generic_and_can_fall_back_to_industry(self):
        specific = self.create(self.client, "ecommerce")
        self.assertTrue(self.resolve(self.client)["fallback"])
        generic = self.create(self.client)
        self.assertEqual(self.resolve(self.client)["ontology"]["ontology_id"], generic["ontology_id"])
        self.assertFalse(self.resolve(self.client)["fallback"])
        self.service.delete_ontology(generic["ontology_id"])
        self.assertEqual(self.resolve(self.client)["ontology"]["ontology_id"], specific["ontology_id"])

    def test_D08_replace_updates_version_time_and_projection(self):
        row = self.create()
        doc = row["data_json"]
        doc.update(name=self.prefix + " renamed", alias_name=["别名"], description="修改后")
        time.sleep(0.003)
        result = self.service.update_ontology(row["ontology_id"], {"data_json": doc, "revision": 1})["ontology"]
        self.assertEqual(result["revision"], 2)
        self.assertGreater(result["update_time"], row["update_time"])
        stored = self.repo.select_ontology_by_id(row["ontology_id"])
        self.assertEqual((stored.name, stored.alias_name, stored.description), (doc["name"], doc["alias_name"], doc["description"]))

    def test_D09_stale_replace_returns_zero_and_service_conflict(self):
        row = self.create()
        vd = validate_document(row["data_json"])
        self.assertEqual(self.repo.update_ontology_document(row["ontology_id"], 1, vd, "active"), 1)
        self.assertEqual(self.repo.update_ontology_document(row["ontology_id"], 1, vd, "active"), 0)
        error = self.assert_error("ONTOLOGY_REVISION_CONFLICT", lambda: self.service.update_ontology(row["ontology_id"], {"data_json": vd.document, "revision": 1}))
        self.assertEqual(error.details, [{"current_revision": 2}])

    def test_D10_delete_stale_revision(self):
        row = self.create()
        self.service.update_ontology_status(row["ontology_id"], {"status": "inactive", "revision": 1})
        self.assert_error("ONTOLOGY_REVISION_CONFLICT", lambda: self.service.delete_ontology(row["ontology_id"], 1))
        self.assertEqual(self.repo.select_ontology_by_id(row["ontology_id"]).del_flag, 0)

    def test_D11_large_chinese_and_emoji_roundtrip(self):
        doc = deepcopy(self.doc)
        doc["object_types"][0]["attributes"] = [{"name": "消息ID" if i == 0 else "字段%s" % i,
            "description": "中文🙂" * 100, "data_type": "string"} for i in range(200)]
        doc["object_types"].append(dict(deepcopy(doc["object_types"][0]), name="第二类"))
        row = self.create(document=doc)
        read = self.repo.select_ontology_by_id(row["ontology_id"])
        self.assertGreater(row["document_bytes"], 300000)
        self.assertEqual(document_size(read.data_json), row["document_bytes"])
        self.assertEqual(read.data_json, row["data_json"])

    def test_D12_projection_and_duplicate_audits(self):
        self.create(self.client)
        conn = self.connector.get_connection(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT ontology_id FROM dops_ontology WHERE name = %s AND del_flag = 0 AND "
                           "(JSON_UNQUOTE(data_json->'$.name') != name OR JSON_UNQUOTE(data_json->'$.client') != client "
                           "OR JSON_UNQUOTE(data_json->'$.product') != product OR JSON_UNQUOTE(data_json->'$.description') != description "
                           "OR NOT (data_json->'$.alias_name' = alias_name))", (self.prefix,))
            self.assertEqual(cursor.fetchall(), [])
            cursor.execute("SELECT client,product,name,COUNT(*) AS cnt FROM dops_ontology WHERE name = %s AND del_flag=0 "
                           "GROUP BY client,product,name HAVING cnt>1", (self.prefix,))
            self.assertEqual(cursor.fetchall(), [])
        finally:
            cursor.close(); conn.close()

    def test_D13_two_empty_gap_creates_exactly_one_winner(self):
        barrier = threading.Barrier(2)
        local = threading.local()
        class RacingRepository(OntologyRepository):
            def _check_name(inner, cursor, vd, exclude=None):
                super()._check_name(cursor, vd, exclude)
                if not getattr(local, "checked", False):
                    local.checked = True
                    barrier.wait(timeout=10)
        repo = RacingRepository(self.connector)
        doc = dict(self.doc, client=self.client)
        vd = validate_document(doc)
        def create():
            try:
                return repo.insert_ontology(vd, "active")
            except OntologyError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: create(), range(2)))
        self.assertEqual(results.count("ONTOLOGY_NAME_CONFLICT"), 1, results)
        self.assertEqual(len([r for r in results if len(r) == 32]), 1)
        self.assertEqual(self.repo.list_ontologies(client=self.client, review_status=None)[1], 1)

    def test_D14_rename_collision_keeps_both_documents(self):
        first = self.create(self.client)
        second = self.create(self.client, name=self.prefix + "other")
        changed = dict(second["data_json"], name=first["name"])
        self.assert_error("ONTOLOGY_NAME_CONFLICT", lambda: self.service.update_ontology(second["ontology_id"], {"data_json": changed, "revision": 1}))
        self.assertEqual(self.repo.select_ontology_by_id(second["ontology_id"]).name, second["name"])
        self.assertEqual(self.repo.select_ontology_by_id(first["ontology_id"]).revision, 1)

    def test_D15_same_name_different_product_and_global(self):
        self.create()
        for product in ("ecommerce", "retail"):
            row = self.create(self.client, product)
            self.assertEqual(self.resolve(self.client, product)["ontology"]["ontology_id"], row["ontology_id"])

    def test_search_escaping_ranking_and_deep_only_hits(self):
        doc = dict(self.doc, alias_name=["alias"], description="literal !%_ token")
        doc["object_types"][0]["attributes"].append({"name": "internal_unique_term", "data_type": "string"})
        created = self.create(self.client, document=doc)
        self.assertEqual(self.repo.list_ontologies(client=self.client, q="!%_")[1], 1)
        self.assertEqual(self.repo.list_ontologies(client=self.client, q="internal_unique_term")[1], 0)
        self.assertEqual(self.repo.list_ontologies(client=self.client, q="internal_unique_term", deep=True)[1], 1)
        self.assertEqual(self.repo.list_ontologies(client=self.client, q="alias")[0][0].ontology_id, created["ontology_id"])

    def test_collation_and_same_status_patch(self):
        row = self.create(self.client, name=self.prefix + " Café")
        self.assert_error("ONTOLOGY_NAME_CONFLICT", lambda: self.create(self.client, name=self.prefix + " CAFE"))
        result = self.service.update_ontology_status(row["ontology_id"], {"status": "active", "revision": 1})
        self.assertEqual(result["ontology"]["revision"], 2)

    def test_review_defaults_approval_edit_and_partial_status_updates(self):
        doc = dict(self.doc, client=self.client)
        row = self.service.insert_ontology({"data_json": doc})["ontology"]
        oid = row["ontology_id"]
        self.assertEqual((row["status"], row["review_status"]), ("active", "pending"))
        self.assertEqual(self.repo.list_ontologies(client=self.client)[1], 0)
        self.assert_error("ONTOLOGY_NOT_FOUND", lambda: self.service.get_ontology(oid))
        self.assertIsNone(self.resolve(self.client)["ontology"])
        self.assertEqual(self.service.get_ontology(oid, review_status="pending")["ontology"]["ontology_id"], oid)
        approved = self.service.update_ontology_status(oid, {"revision": 1, "review_status": "approved"})["ontology"]
        self.assertEqual((approved["status"], approved["review_status"], approved["revision"]), ("active", "approved", 2))
        self.assertEqual(self.resolve(self.client)["ontology"]["ontology_id"], oid)
        self.assertEqual(self.repo.list_ontologies(client=self.client)[1], 1)
        self.service.update_ontology_status(oid, {"revision": 2, "status": "inactive"})
        self.assertEqual(self.repo.select_ontology_by_id(oid).review_status, "approved")
        self.assertIsNone(self.resolve(self.client)["ontology"])
        self.assertEqual(self.repo.list_ontologies(client=self.client)[1], 1)
        self.service.update_ontology(oid, {"revision": 3, "data_json": dict(doc, description="changed")})
        stored = self.repo.select_ontology_by_id(oid)
        self.assertEqual((stored.status, stored.review_status, stored.revision), ("inactive", "pending", 4))
        self.assert_error("ONTOLOGY_REVISION_CONFLICT", lambda: self.service.update_ontology_status(oid, {"revision": 3, "review_status": "approved"}))
        self.service.delete_ontology(oid, 4)
        self.assertEqual(self.repo.list_ontologies(client=self.client, review_status=None)[1], 0)
        self.assertEqual(self.repo.list_ontologies(client=self.client, include_deleted=True)[1], 0)
        self.assertEqual(self.repo.list_ontologies(client=self.client, include_deleted=True, review_status=None)[1], 1)

    def test_review_search_counts_and_pagination_share_filters(self):
        expected = {}
        for review in ("pending", "approved", "rejected"):
            for status in ("active", "inactive"):
                row = self.create(self.client, name=self.prefix + review + status, status=status, review_status=review)
                expected[(review, status)] = row["ontology_id"]
        for review in ("pending", "approved", "rejected"):
            rows, count = self.repo.list_ontologies(client=self.client, review_status=review, limit=1, offset=1)
            self.assertEqual(count, 2)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].review_status, review)
            rows, count = self.repo.list_ontologies(client=self.client, review_status=review, status="inactive", q=self.prefix)
            self.assertEqual(count, 1)
            self.assertEqual(rows[0].ontology_id, expected[(review, "inactive")])
        self.assertEqual(self.repo.list_ontologies(client=self.client)[1], 2)
        self.assertEqual(self.repo.list_ontologies(client=self.client, review_status=None)[1], 6)

    def test_legacy_review_migration_preserves_rows_and_is_idempotent(self):
        table = "ontology_migration_" + uuid4().hex
        conn = self.connector.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("CREATE TABLE `" + table + "` LIKE dops_ontology")
            cursor.execute("ALTER TABLE `" + table + "` DROP INDEX idx_scope_status, DROP COLUMN review_status, "
                           "ADD INDEX idx_scope_status (client,product,status,del_flag)")
            for status, deleted in (("active", 0), ("draft", 0), ("draft", 1)):
                cursor.execute("INSERT INTO `" + table + "` (ontology_id,name,alias_name,data_json,status,del_flag) "
                               "VALUES (%s,%s,%s,%s,%s,%s)",
                               (uuid4().hex, self.prefix + status + str(deleted), "[]", json.dumps(self.doc), status, deleted))
            conn.commit()
            migration = (ROOT / "migrations/20261118_ontology_review_status.sql").read_text().replace("dops_ontology", table)
            for run in range(2):
                for statement in migration.split(";"):
                    if statement.strip():
                        cursor.execute(statement)
                        if cursor.with_rows:
                            cursor.fetchall()
                conn.commit()
                cursor.execute("SELECT status,review_status,revision,del_flag,data_json FROM `" + table + "` ORDER BY id")
                rows = cursor.fetchall()
                self.assertEqual([(r["status"], r["revision"], r["del_flag"]) for r in rows],
                                 [("active", 1, 0), ("inactive", 2, 0), ("inactive", 2, 1)])
                self.assertEqual([r["review_status"] for r in rows], ["pending" if run == 0 else "approved", "pending", "pending"])
                self.assertTrue(all(json.loads(r["data_json"]) == self.doc for r in rows))
                cursor.execute("UPDATE `" + table + "` SET review_status='approved' WHERE status='active'")
                conn.commit()
            cursor.execute("SHOW INDEX FROM `" + table + "` WHERE Key_name='idx_scope_status'")
            self.assertEqual([r["Column_name"] for r in cursor.fetchall()], ["client", "product", "status", "review_status", "del_flag"])
        finally:
            cursor.execute("DROP TABLE IF EXISTS `" + table + "`")
            conn.commit()
            cursor.close(); conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
