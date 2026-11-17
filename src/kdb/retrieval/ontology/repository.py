"""Parameterized MySQL storage using the shared connector and explicit write transactions."""
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from kdb.shared.config.paths import project_path

from .errors import (OntologyError, ONTOLOGY_DB_UNAVAILABLE, ONTOLOGY_INTERNAL_ERROR,
                     ONTOLOGY_NAME_CONFLICT, ONTOLOGY_VALIDATION_FAILED)
from .schema import DEFAULT_PAGE_SIZE, TABLE_NAME
from .validation import ValidatedDocument, compact_json

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()
_CONNECTOR = None
TABLE = "`%s`" % TABLE_NAME
META_COLUMNS = ("`ontology_id`, `client`, `product`, `name`, `alias_name`, `description`, "
                "`status`, `revision`, `create_time`, `update_time`")
FULL_COLUMNS = "`id`, " + META_COLUMNS + ", `del_flag`, `data_json`"


def get_connector(config_path: Optional[str] = None):
    """One lazily initialized shared MySQLConnector per ontology worker process."""
    global _CONNECTOR
    if _CONNECTOR is None:
        with _LOCK:
            if _CONNECTOR is None:
                from kdb.shared.database.mysql import MySQLConnector
                path = config_path or os.environ.get("KDB_MYSQL_CONFIG") or str(project_path("config", "mysql_conn_config.json"))
                _CONNECTOR = MySQLConnector(path)
    return _CONNECTOR


@dataclass
class OntologyRow:
    ontology_id: str
    client: str
    product: str
    name: str
    alias_name: List[str]
    description: str
    status: str
    revision: int
    create_time: str
    update_time: str
    del_flag: int = 0
    data_json: Dict[str, Any] = field(default_factory=dict)


def _load_json(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    return json.loads(value)


def fmt_dt(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def to_row(raw: Dict[str, Any]) -> OntologyRow:
    return OntologyRow(
        ontology_id=raw["ontology_id"], client=raw["client"] or "", product=raw["product"] or "",
        name=raw["name"], alias_name=_load_json(raw["alias_name"], []), description=raw["description"] or "",
        status=raw["status"], revision=int(raw["revision"]), create_time=fmt_dt(raw["create_time"]),
        update_time=fmt_dt(raw["update_time"]), del_flag=int(raw.get("del_flag", 0)),
        data_json=_load_json(raw.get("data_json"), {}))


def escape_like(value: str) -> str:
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def _db_error(exc):
    errno = getattr(exc, "errno", None)
    if errno in (3140, 1406, 1366):
        reason = {3140: "invalid_json", 1406: "too_long", 1366: "invalid_type"}[errno]
        logger.error("ontology MySQL rejected document; errno=%s session charset=utf8mb4", errno)
        return OntologyError(ONTOLOGY_VALIDATION_FAILED, 422, "数据库拒绝文档内容",
                             [{"path": "$", "reason": reason, "message": "文档不满足存储约束"}])
    if errno in (1040, 1045, 1049, 1205, 1213, 2002, 2003, 2006, 2013, 2055) or isinstance(exc, (OSError, ImportError)):
        return OntologyError(ONTOLOGY_DB_UNAVAILABLE, 503, "数据库不可用，请稍后重试")
    logger.exception("ontology database operation failed; errno=%s", errno)
    return OntologyError(ONTOLOGY_INTERNAL_ERROR, 500, "本体存储操作失败")


class OntologyRepository:
    def __init__(self, connector=None):
        self._connector = connector

    def _run(self, fn, write=False):
        conn = cursor = None
        try:
            connector = self._connector or get_connector()
            conn = connector.get_connection()
            if conn is None:
                raise OntologyError(ONTOLOGY_DB_UNAVAILABLE, 503, "数据库连接不可用")
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SET NAMES utf8mb4")
            if write:
                # Gap-lock duplicate detection must not depend on a deployment's default isolation.
                conn.start_transaction(isolation_level="REPEATABLE READ")
            result = fn(cursor)
            if write:
                conn.commit()
            return result
        except Exception:
            if conn is not None and write:
                try:
                    conn.rollback()
                except Exception:
                    logger.warning("ontology rollback failed", exc_info=True)
            raise
        finally:
            for resource in (cursor, conn):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        logger.warning("ontology connection cleanup failed", exc_info=True)

    def _tx(self, fn):
        for attempt in range(2):
            try:
                return self._run(fn, write=True)
            except OntologyError:
                raise
            except Exception as exc:
                if getattr(exc, "errno", None) == 1213 and attempt == 0:
                    continue
                raise _db_error(exc) from exc

    def _read_call(self, fn):
        try:
            return self._run(fn)
        except OntologyError:
            raise
        except Exception as exc:
            raise _db_error(exc) from exc

    def _read(self, sql: str, params: tuple):
        def read(cursor):
            cursor.execute(sql, params)
            return list(cursor.fetchall())
        return self._read_call(read)

    def select_ontology_by_id(self, ontology_id: str) -> Optional[OntologyRow]:
        rows = self._read("SELECT %s FROM %s WHERE `ontology_id` = %%s" % (FULL_COLUMNS, TABLE), (ontology_id,))
        return to_row(rows[0]) if rows else None

    def _check_name(self, cursor, vd, exclude=None):
        sql = ("SELECT `ontology_id`, `status`, `revision` FROM " + TABLE +
               " WHERE `client` = %s AND `product` = %s AND `name` = %s AND `del_flag` = 0")
        params = [vd.client, vd.product, vd.name]
        if exclude is not None:
            sql += " AND `ontology_id` <> %s"
            params.append(exclude)
        cursor.execute(sql + " FOR UPDATE", tuple(params))
        rows = cursor.fetchall()
        if rows:
            existing = rows[0]
            raise OntologyError(ONTOLOGY_NAME_CONFLICT, 409, "同一业务键已存在本体",
                                [{"existing_ontology_id": existing["ontology_id"],
                                  "status": existing["status"], "revision": int(existing["revision"])}])

    def insert_ontology(self, vd: ValidatedDocument, status: str) -> str:
        def insert(cursor):
            self._check_name(cursor, vd)
            for attempt in range(2):
                ontology_id = uuid4().hex
                try:
                    cursor.execute(
                        "INSERT INTO " + TABLE + " (`ontology_id`, `client`, `product`, `name`, "
                        "`alias_name`, `description`, `data_json`, `status`) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (ontology_id, vd.client, vd.product, vd.name, compact_json(vd.alias_name),
                         vd.description, compact_json(vd.document), status))
                    return ontology_id
                except Exception as exc:
                    if getattr(exc, "errno", None) != 1062 or attempt:
                        raise
        return self._tx(insert)

    def update_ontology_document(self, ontology_id: str, revision: int, vd: ValidatedDocument, status: str) -> int:
        def replace(cursor):
            self._check_name(cursor, vd, exclude=ontology_id)
            cursor.execute(
                "UPDATE " + TABLE + " SET `name` = %s, `alias_name` = %s, `description` = %s, "
                "`data_json` = %s, `status` = %s, `revision` = `revision` + 1, "
                "`update_time` = CURRENT_TIMESTAMP(3) WHERE `ontology_id` = %s AND `revision` = %s AND `del_flag` = 0",
                (vd.name, compact_json(vd.alias_name), vd.description, compact_json(vd.document), status, ontology_id, revision))
            return cursor.rowcount
        return self._tx(replace)

    def update_ontology_status(self, ontology_id: str, revision: int, status: str) -> int:
        def update(cursor):
            cursor.execute(
                "UPDATE " + TABLE + " SET `status` = %s, `revision` = `revision` + 1, "
                "`update_time` = CURRENT_TIMESTAMP(3) WHERE `ontology_id` = %s AND `revision` = %s AND `del_flag` = 0",
                (status, ontology_id, revision))
            return cursor.rowcount
        return self._tx(update)

    def delete_ontology(self, ontology_id: str, revision: Optional[int]) -> int:
        def delete(cursor):
            sql = ("UPDATE " + TABLE + " SET `del_flag` = 1, `revision` = `revision` + 1, "
                   "`update_time` = CURRENT_TIMESTAMP(3) WHERE `ontology_id` = %s AND `del_flag` = 0")
            params = (ontology_id,)
            if revision is not None:
                sql += " AND `revision` = %s"
                params += (revision,)
            cursor.execute(sql, params)
            return cursor.rowcount
        return self._tx(delete)

    def list_ontologies(self, client=None, product=None, status=None, q=None, deep=False,
             include_deleted=False, limit=DEFAULT_PAGE_SIZE, offset=0) -> Tuple[List[OntologyRow], int]:
        where = [] if include_deleted else ["`del_flag` = 0"]
        params = []
        for column, value in (("client", client), ("product", product), ("status", status)):
            if value is not None:
                where.append("`%s` = %%s" % column)
                params.append(value)
        score, score_params = "", []
        order = "`update_time` DESC, `id` DESC"
        if q:
            like = escape_like(q)
            contains, prefix = "%" + like + "%", like + "%"
            search = ["`name` LIKE %s ESCAPE '!'", "`description` LIKE %s ESCAPE '!'",
                      "LOWER(CAST(`alias_name` AS CHAR)) LIKE %s ESCAPE '!'"]
            params.extend((contains, contains, "%" + escape_like(q.lower()) + "%"))
            if deep:
                search.append("CAST(`data_json` AS CHAR) LIKE %s ESCAPE '!'")
                params.append(contains)
            where.append("(" + " OR ".join(search) + ")")
            score = (", (CASE WHEN `name` = %s THEN 100 "
                     "WHEN JSON_CONTAINS(`alias_name`, JSON_QUOTE(%s)) THEN 90 "
                     "WHEN `name` LIKE %s ESCAPE '!' THEN 70 "
                     "WHEN `name` LIKE %s ESCAPE '!' THEN 50 ELSE 20 END) AS `q_score`")
            score_params = [q, q, prefix, contains]
            order = "`q_score` DESC, " + order
        where_sql = " AND ".join(where) or "1=1"

        def read(cursor):
            cursor.execute("SELECT COUNT(*) AS total FROM " + TABLE + " WHERE " + where_sql, tuple(params))
            total = int(cursor.fetchone()["total"])
            cursor.execute("SELECT " + META_COLUMNS + score + " FROM " + TABLE + " WHERE " + where_sql +
                           " ORDER BY " + order + " LIMIT %s OFFSET %s", tuple(score_params + params + [limit, offset]))
            return [to_row(row) for row in cursor.fetchall()], total
        return self._read_call(read)

    def select_ontology(self, client: str, product: str, name: Optional[str]) -> Optional[OntologyRow]:
        sql = ("SELECT " + FULL_COLUMNS +
               ", ((`client` = %s AND %s != '') * 2 + (`product` = %s AND %s != '')) AS `scope_rank` "
               "FROM " + TABLE + " WHERE `del_flag` = 0 AND `status` = 'active' "
               "AND (`client` = %s OR `client` = '')")
        params = [client, client, product, product, client]
        # The documented client-only request can fall back to that client's latest industry row.
        if client and not product:
            sql += " AND (`product` = %s OR `client` = %s)"
            params.extend((product, client))
        else:
            sql += " AND (`product` = %s OR `product` = '')"
            params.append(product)
        if name:
            sql += " AND `name` = %s"
            params.append(name)
        sql += " ORDER BY `scope_rank` DESC, (`product` = '') DESC, `update_time` DESC, `id` DESC LIMIT 1"
        rows = self._read(sql, tuple(params))
        return to_row(rows[0]) if rows else None
