from datetime import datetime
from unittest.mock import Mock

import pytest

from kdb.retrieval.ontology.errors import OntologyError
from kdb.retrieval.ontology.repository import OntologyRepository, _load_json, to_row
from kdb.retrieval.ontology.validation import validate_document


class DriverError(Exception):
    def __init__(self, errno):
        self.errno = errno


@pytest.fixture
def sql():
    cursor = Mock(rowcount=1)
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = {"total": 0}
    conn = Mock()
    conn.cursor.return_value = cursor
    connector = Mock()
    connector.get_connection.return_value = conn
    return OntologyRepository(connector), connector, conn, cursor


def test_list_score_where_and_pagination_parameter_order(sql):
    repo, _, conn, cursor = sql
    q = "a!%_"
    repo.list_ontologies(client="wayfair", status="active", q=q, limit=20, offset=40)
    count_sql, count_params = cursor.execute.call_args_list[-2].args
    page_sql, params = cursor.execute.call_args_list[-1].args
    assert count_params == ("wayfair", "active", "approved", "%a!!!%!_%", "%a!!!%!_%", "%a!!!%!_%")
    assert params == (q, q, "a!!!%!_%", "%a!!!%!_%", *count_params, 20, 40)
    assert page_sql.count("%s") == len(params)
    assert "q_score` DESC" in page_sql and "`data_json`" not in page_sql
    assert "`del_flag` = 0" in count_sql
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


def test_list_empty_filters_and_deep_is_additional_or_match(sql):
    repo, _, _, cursor = sql
    repo.list_ontologies(client="", product=None, q="inner", deep=True, include_deleted=True)
    sql_text, params = cursor.execute.call_args_list[-1].args
    assert " OR CAST(`data_json` AS CHAR) LIKE" in sql_text
    assert "`del_flag` = 0" not in sql_text
    assert "`product` = %s" not in sql_text
    assert params[4] == ""
    repo.list_ontologies(include_deleted=True, audit_status=None)
    assert "WHERE 1=1" in cursor.execute.call_args.args[0]


def test_insert_and_duplicate_check_share_transaction(doc, sql):
    repo, _, conn, cursor = sql
    vd = validate_document(doc)
    oid = repo.insert_ontology(vd, "inactive")
    assert len(oid) == 32
    calls = cursor.execute.call_args_list
    assert calls[-2].args[0].endswith("FOR UPDATE")
    assert calls[-2].args[1] == ("", "", vd.name)
    assert calls[-1].args[1][0] == oid
    assert calls[-1].args[1][-2:] == ("inactive", "pending")
    conn.start_transaction.assert_called_once_with(isolation_level="REPEATABLE READ")
    conn.commit.assert_called_once()
    cursor.close.assert_called_once()
    conn.close.assert_called_once()


def test_conflict_rolls_back_and_no_insert(doc, sql):
    repo, _, conn, cursor = sql
    cursor.fetchall.return_value = [{"ontology_id": "a" * 32, "status": "inactive", "audit_status": "pending", "revision": 4}]
    with pytest.raises(OntologyError) as caught:
        repo.insert_ontology(validate_document(doc), "active")
    assert caught.value.details == [{"existing_ontology_id": "a" * 32, "status": "inactive", "audit_status": "pending", "revision": 4}]
    assert not any("INSERT" in call.args[0] for call in cursor.execute.call_args_list)
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


def test_put_checks_new_name_excluding_self_and_binds_version(doc, sql):
    repo, _, _, cursor = sql
    oid = "b" * 32
    doc["name"] = "new"
    assert repo.update_ontology_document(oid, 5, validate_document(doc), "inactive") == 1
    check, params = cursor.execute.call_args_list[-2].args
    assert "`ontology_id` <> %s" in check
    assert params == ("", "", "new", oid)
    update, params = cursor.execute.call_args.args
    assert params[-4:] == ("inactive", "pending", oid, 5)
    assert "`revision` = `revision` + 1" in update


@pytest.mark.parametrize("errno,status,code", [(1205, 503, "ONTOLOGY_DB_UNAVAILABLE"),
    (2003, 503, "ONTOLOGY_DB_UNAVAILABLE"), (2006, 503, "ONTOLOGY_DB_UNAVAILABLE"),
    (2055, 503, "ONTOLOGY_DB_UNAVAILABLE"), (3140, 422, "ONTOLOGY_VALIDATION_FAILED"),
    (1406, 422, "ONTOLOGY_VALIDATION_FAILED"), (1366, 422, "ONTOLOGY_VALIDATION_FAILED"),
    (9999, 500, "ONTOLOGY_INTERNAL_ERROR")])
def test_sql_errors_map_and_release(errno, status, code, sql):
    repo, _, conn, cursor = sql
    cursor.execute.side_effect = DriverError(errno)
    with pytest.raises(OntologyError) as caught:
        repo.update_ontology_status("0" * 32, 1, "active")
    assert (caught.value.http_status, caught.value.code) == (status, code)
    assert str(errno) not in caught.value.message
    cursor.close.assert_called_once()
    conn.close.assert_called_once()
    conn.rollback.assert_called_once()


def test_deadlock_retries_entire_transaction_once(sql):
    repo, _, conn, cursor = sql
    cursor.execute.side_effect = [None, DriverError(1213), None, None]
    assert repo.update_ontology_status("0" * 32, 1, "active") == 1
    assert conn.start_transaction.call_count == 2
    conn.rollback.assert_called_once()
    conn.commit.assert_called_once()
    assert conn.close.call_count == 2
    cursor.execute.side_effect = DriverError(1213)
    with pytest.raises(OntologyError) as caught:
        repo.update_ontology_status("0" * 32, 1, "active")
    assert caught.value.http_status == 503


def test_uuid_collision_regenerates_once(doc, sql):
    repo, _, conn, cursor = sql
    cursor.execute.side_effect = [None, None, DriverError(1062), None]
    oid = repo.insert_ontology(validate_document(doc), "active")
    first_id = cursor.execute.call_args_list[-2].args[1][0]
    assert oid != first_id
    conn.commit.assert_called_once()
    cursor.execute.side_effect = [None, None, DriverError(1062), DriverError(1062)]
    with pytest.raises(OntologyError) as caught:
        repo.insert_ontology(validate_document(doc), "active")
    assert caught.value.code == "ONTOLOGY_INTERNAL_ERROR"


def test_connection_cursor_and_close_failure_paths(sql):
    repo, connector, conn, cursor = sql
    connector.get_connection.return_value = None
    with pytest.raises(OntologyError) as caught:
        repo.select_ontology_by_id("0" * 32)
    assert caught.value.http_status == 503
    connector.get_connection.return_value = conn
    conn.cursor.side_effect = DriverError(2006)
    with pytest.raises(OntologyError):
        repo.select_ontology_by_id("0" * 32)
    conn.close.assert_called_once()
    conn.cursor.side_effect = None
    conn.close.reset_mock()
    cursor.close.side_effect = RuntimeError("close")
    assert repo.select_ontology_by_id("0" * 32) is None
    conn.close.assert_called_once()


def test_resolve_sql_filters_and_parameter_order(sql):
    repo, _, _, cursor = sql
    repo.select_ontology("wayfair", "ecommerce", "named")
    statement, params = cursor.execute.call_args.args
    assert params == ("wayfair", "wayfair", "ecommerce", "ecommerce", "wayfair", "ecommerce", "named")
    assert "`status` = 'active'" in statement and statement.endswith("LIMIT 1")
    assert "`audit_status` = 'approved'" in statement and "`del_flag` = 0" in statement
    assert "`id` DESC" in statement
    repo.select_ontology("wayfair", "", None)
    assert cursor.execute.call_args.args[1] == ("wayfair", "wayfair", "", "", "wayfair", "", "wayfair")


def test_json_mapping_and_millisecond_time():
    assert _load_json(b'["x"]', []) == ["x"]
    assert _load_json({"a": 1}, {}) == {"a": 1}
    raw = dict(ontology_id="a" * 32, client="", product="", name="test", alias_name='["x"]',
               description="", status="active", audit_status="approved", revision=2, create_time=datetime(2026, 1, 1, microsecond=123456),
               update_time=datetime(2026, 1, 1), del_flag=0, data_json='{"name":"test"}')
    row = to_row(raw)
    assert row.create_time == "2026-01-01 00:00:00.123"
    assert row.data_json == {"name": "test"}
    assert row.audit_status == "approved"


def test_review_filter_is_shared_by_count_and_page(sql):
    repo, _, _, cursor = sql
    for review in ("approved", "pending", "rejected", None):
        repo.list_ontologies(audit_status=review)
        count, params = cursor.execute.call_args_list[-2].args
        page, page_params = cursor.execute.call_args_list[-1].args
        assert ("`audit_status` = %s" in count) == (review is not None)
        assert count.split(" WHERE ")[1] == page.split(" WHERE ")[1].split(" ORDER BY ")[0]
        assert params == (() if review is None else (review,))
        assert page_params[:-2] == params


def test_partial_status_update_binds_both_states_with_version(sql):
    repo, _, conn, cursor = sql
    repo.update_ontology_status("b" * 32, 7, audit_status="approved")
    statement, params = cursor.execute.call_args.args
    assert params == (None, "approved", "b" * 32, 7)
    assert "`status` = COALESCE(%s, `status`)" in statement
    assert "`audit_status` = COALESCE(%s, `audit_status`)" in statement
    assert "`revision` = %s AND `del_flag` = 0" in statement
    conn.commit.assert_called_once()
