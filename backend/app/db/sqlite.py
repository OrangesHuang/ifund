"""SQLite 后端：把统一过滤语法（PostgREST 风格 DSL）翻译成 SQL 并执行。

支持的过滤语法（``params`` 为 dict 或 list[tuple(key, val)]）：

| 语法                              | SQL 等价                         |
|-----------------------------------|----------------------------------|
| ``("col", "eq.v")``               | ``col = ?``                      |
| ``("col", "neq.v")``              | ``col != ?``                     |
| ``("col", "gt.v")`` / ``gte.``    | ``col > ?`` / ``>=``             |
| ``("col", "lt.v")`` / ``lte.``    | ``col < ?`` / ``<=``             |
| ``("col", "ilike.*kw*")``         | ``col LIKE ? COLLATE NOCASE``    |
| ``("col", "not.ilike.*kw*")``     | ``col NOT LIKE ? COLLATE NOCASE``|
| ``("col", "in.(a,b,c)")``         | ``col IN (?,?,?)``               |
| ``("col", "not.in.(a,b,c)")``     | ``col NOT IN (?,?,?)``           |
| ``("or", "(c1.eq.a,c2.ilike.*b*)")`` | ``(c1 = ? OR c2 LIKE ?)``     |
| ``("select", "a,b,c")``           | ``SELECT a,b,c``                 |
| ``("order", "col.desc,col2.asc")``| ``ORDER BY col DESC, col2 ASC``  |
| ``("limit", n)`` / ``("offset", n)`` | ``LIMIT n`` / ``OFFSET n``    |

所有值走参数化绑定（防注入）。
"""
from __future__ import annotations

import re
import sqlite3
import threading

from .base import Database, UniqueViolation

# 可按 fund_details 列排序的白名单（list_funds_with_details 用）
SORTABLE_DETAIL = {
    "scale", "return_ytd", "drawdown_ytd", "sharpe_3y", "sharpe_1y",
    "max_drawdown_3y", "max_drawdown_1y", "position_stock",
}

# 联合查询返回列（两后端结构必须一致）
_RESULT_COLS = [
    'f."id" AS id', 'f."code" AS code', 'f."name" AS name', 'f."type" AS type',
    'f."fund_type" AS fund_type', 'd."scale" AS scale',
    'd."sharpe_3y" AS sharpe_3y', 'd."sharpe_1y" AS sharpe_1y',
    'd."max_drawdown_3y" AS max_drawdown_3y', 'd."max_drawdown_1y" AS max_drawdown_1y',
    'd."position_stock" AS position_stock', 'd."position_bond" AS position_bond',
    'd."return_ytd" AS return_ytd', 'd."drawdown_ytd" AS drawdown_ytd',
]

# OR 子句切分：逗号后须跟「非括号字符直到 ( 或 字符串结尾」，避免切到 in.(a,b) 内部
_OR_SPLIT_RE = re.compile(r",(?=[^()]*(?:\(|$))")


def _quote_col(col: str) -> str:
    """处理 ``table.field`` 形式，逐段加双引号。"""
    return ".".join(f'"{part}"' for part in col.split("."))


def _prefixed(col: str, prefix: str) -> str:
    """给无前缀的列名补上表别名前缀（JOIN 用）；已含 ``.`` 的不动。"""
    if not prefix or "." in col:
        return col
    return f"{prefix}.{col}"


def _parse_in_list(raw: str) -> list[str]:
    """``(a,b,c)`` → ``["a","b","c"]``。"""
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    return [x.strip() for x in raw.split(",") if x.strip() != ""]


def _in_clause(col: str, raw: str, negate: bool):
    items = _parse_in_list(raw)
    placeholders = ",".join("?" * len(items)) or "NULL"
    op = "NOT IN" if negate else "IN"
    return f"{col} {op} ({placeholders})", items


# 操作符前缀 → SQL 片段构造器。顺序重要：长前缀/取反在前。
_OPERATORS = [
    ("not.ilike.", lambda c, v: (f"{c} NOT LIKE ? COLLATE NOCASE", [v.replace("*", "%")])),
    ("ilike.", lambda c, v: (f"{c} LIKE ? COLLATE NOCASE", [v.replace("*", "%")])),
    ("not.in.", lambda c, v: _in_clause(c, v, True)),
    ("in.", lambda c, v: _in_clause(c, v, False)),
    ("neq.", lambda c, v: (f"{c} != ?", [v])),
    ("eq.", lambda c, v: (f"{c} = ?", [v])),
    ("gte.", lambda c, v: (f"{c} >= ?", [v])),
    ("gt.", lambda c, v: (f"{c} > ?", [v])),
    ("lte.", lambda c, v: (f"{c} <= ?", [v])),
    ("lt.", lambda c, v: (f"{c} < ?", [v])),
]


def _parse_filter(col: str, val) -> tuple[str, list]:
    """单列条件 → ``(sql, params)``，无前缀匹配则按等值。"""
    qcol = _quote_col(col)
    s = str(val)
    for prefix, builder in _OPERATORS:
        if s.startswith(prefix):
            return builder(qcol, s[len(prefix):])
    return f"{qcol} = ?", [s]


def _parse_or(val, prefix: str = "") -> tuple[str, list]:
    """``(c1.eq.a,c2.ilike.*b*)`` → ``(c1 = ? OR c2 LIKE ?)``。"""
    inner = str(val).strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    parts: list[str] = []
    params: list = []
    for clause in _OR_SPLIT_RE.split(inner):
        clause = clause.strip()
        if not clause:
            continue
        col, _, rest = clause.partition(".")
        sql, ps = _parse_filter(_prefixed(col, prefix), rest)
        parts.append(sql)
        params.extend(ps)
    return "(" + " OR ".join(parts) + ")", params


def _build_order(val, prefix: str = "") -> str:
    segs = []
    for seg in str(val).split(","):
        seg = seg.strip()
        if not seg:
            continue
        if seg.endswith(".desc"):
            col, direction = seg[:-5], "DESC"
        elif seg.endswith(".asc"):
            col, direction = seg[:-4], "ASC"
        else:
            col, direction = seg, "ASC"
        segs.append(f"{_quote_col(_prefixed(col, prefix))} {direction}")
    return ("ORDER BY " + ", ".join(segs)) if segs else ""


def _normalize_params(params):
    if params is None:
        return []
    if isinstance(params, dict):
        return list(params.items())
    return list(params)


def _build_clauses(params, prefix: str = "") -> dict:
    """把过滤语法拆成 where / order / limit / offset / select 各部分。"""
    where_parts: list[str] = []
    where_params: list = []
    order, select = "", "*"
    limit = offset = None
    for key, val in _normalize_params(params):
        if key == "select":
            select = str(val)
        elif key == "order":
            order = _build_order(val, prefix)
        elif key == "limit":
            limit = int(val)
        elif key == "offset":
            offset = int(val)
        elif key == "or":
            sql, ps = _parse_or(val, prefix)
            where_parts.append(sql)
            where_params.extend(ps)
        else:
            sql, ps = _parse_filter(_prefixed(key, prefix), val)
            where_parts.append(sql)
            where_params.extend(ps)
    return {
        "where": " AND ".join(where_parts),
        "where_params": where_params,
        "order": order,
        "limit": limit,
        "offset": offset,
        "select": select,
    }


class SqliteDatabase(Database):
    """SQLite 实现：每线程一个连接（WAL），用于 Flask 多线程与 worker 线程池。"""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    def select(self, table: str, params=None) -> list[dict]:
        c = _build_clauses(params)
        sql = f'SELECT {c["select"]} FROM "{table}"'
        if c["where"]:
            sql += " WHERE " + c["where"]
        if c["order"]:
            sql += " " + c["order"]
        if c["limit"] is not None:
            sql += f' LIMIT {c["limit"]}'
        if c["offset"] is not None:
            sql += f' OFFSET {c["offset"]}'
        cur = self._conn().execute(sql, c["where_params"])
        return [dict(row) for row in cur.fetchall()]

    def insert(self, table: str, data: dict) -> dict:
        cols = list(data.keys())
        col_sql = ",".join(f'"{col}"' for col in cols)
        placeholders = ",".join("?" * len(cols))
        conn = self._conn()
        try:
            cur = conn.execute(
                f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders})',
                [data[col] for col in cols],
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise UniqueViolation(str(exc)) from exc
        row = conn.execute(
            f'SELECT * FROM "{table}" WHERE rowid = ?', [cur.lastrowid]
        ).fetchone()
        return dict(row) if row else {**data, "id": cur.lastrowid}

    def batch_insert(self, table: str, rows: list[dict], batch_size: int = 500) -> None:
        if not rows:
            return
        cols = list(rows[0].keys())
        col_sql = ",".join(f'"{col}"' for col in cols)
        placeholders = ",".join("?" * len(cols))
        sql = f'INSERT OR REPLACE INTO "{table}" ({col_sql}) VALUES ({placeholders})'
        conn = self._conn()
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            conn.executemany(sql, [[row.get(col) for col in cols] for row in chunk])
        conn.commit()

    def update(self, table: str, filters: dict, data: dict) -> None:
        set_sql = ", ".join(f'"{col}" = ?' for col in data)
        sql = f'UPDATE "{table}" SET {set_sql}'
        params = list(data.values())
        if filters:
            sql += " WHERE " + " AND ".join(f'"{col}" = ?' for col in filters)
            params += list(filters.values())
        conn = self._conn()
        conn.execute(sql, params)
        conn.commit()

    def delete(self, table: str, filters: dict | None = None) -> None:
        sql = f'DELETE FROM "{table}"'
        params: list = []
        if filters:
            sql += " WHERE " + " AND ".join(f'"{col}" = ?' for col in filters)
            params = list(filters.values())
        conn = self._conn()
        conn.execute(sql, params)
        conn.commit()

    def count(self, table: str, params=None) -> int:
        c = _build_clauses(params)
        sql = f'SELECT COUNT(*) AS n FROM "{table}"'
        if c["where"]:
            sql += " WHERE " + c["where"]
        cur = self._conn().execute(sql, c["where_params"])
        return int(cur.fetchone()["n"])

    @staticmethod
    def _build_join_order(order_parts) -> str:
        if not order_parts:
            return 'ORDER BY f."code" ASC'
        segs = []
        for field, direction in order_parts:
            sql_dir = "DESC" if str(direction).lower() == "desc" else "ASC"
            alias = "d" if field in SORTABLE_DETAIL else "f"
            segs.append(f'{alias}."{field}" {sql_dir}')
        return "ORDER BY " + ", ".join(segs)

    def list_funds_with_details(self, fund_params, detail_params, skip, limit, order_parts):
        fund_c = _build_clauses(fund_params, "f")
        detail_c = _build_clauses(detail_params, "d")
        where_parts, where_params = [], []
        for clause in (fund_c, detail_c):
            if clause["where"]:
                where_parts.append(clause["where"])
                where_params.extend(clause["where_params"])
        where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        base = 'FROM "funds" f LEFT JOIN "fund_details" d ON f."code" = d."fund_code"'
        conn = self._conn()
        total = int(
            conn.execute(f"SELECT COUNT(*) AS n {base}{where_sql}", where_params).fetchone()["n"]
        )
        order_sql = self._build_join_order(order_parts)
        sql = (
            f'SELECT {", ".join(_RESULT_COLS)} {base}{where_sql} {order_sql} LIMIT ? OFFSET ?'
        )
        rows = conn.execute(sql, where_params + [limit, skip]).fetchall()
        return total, [dict(row) for row in rows]

    def list_industry_mapping(self, *, market="", label_kw="", status="", keyword="", skip=0, limit=50):
        # held：持仓股票去重（带簡称），走 (holding_type, asset_code, asset_name) 覆盖索引，免全表扫。
        # m：LEFT JOIN 行业映射后派生 market（缺映射按代码形态兜底）/ covered（有申万三级或东财）。
        # 末层再算 label（覆盖时取 申万三级→二级→东财），并把过滤/排序/分页全交给 SQL。
        base = """
            WITH held AS (
                SELECT asset_code AS stock_code, MIN(asset_name) AS held_name
                FROM fund_holdings WHERE holding_type = 'stock' GROUP BY asset_code
            ),
            m AS (
                SELECT h.stock_code,
                    COALESCE(NULLIF(si.stock_name, ''), h.held_name, '') AS stock_name,
                    COALESCE(NULLIF(si.market, ''),
                        CASE
                            WHEN h.stock_code GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]' THEN 'A'
                            WHEN h.stock_code GLOB '[0-9][0-9][0-9][0-9][0-9]' THEN 'HK'
                            ELSE 'OTHER'
                        END) AS market,
                    COALESCE(si.sw_l1, '') AS sw_l1,
                    COALESCE(si.sw_l2, '') AS sw_l2,
                    COALESCE(si.sw_l3, '') AS sw_l3,
                    COALESCE(si.em_industry, '') AS em_industry,
                    COALESCE(si.source, '') AS source,
                    COALESCE(si.manual, 0) AS manual,
                    CASE WHEN COALESCE(si.sw_l3, '') <> '' OR COALESCE(si.em_industry, '') <> ''
                         THEN 1 ELSE 0 END AS covered
                FROM held h LEFT JOIN stock_industry si ON si.stock_code = h.stock_code
            ),
            r AS (
                SELECT *,
                    CASE WHEN covered = 1
                         THEN COALESCE(NULLIF(sw_l3, ''), NULLIF(sw_l2, ''), NULLIF(em_industry, ''))
                         ELSE '' END AS label
                FROM m
            )
        """
        where, params = ["1 = 1"], []
        if market:
            where.append("market = ?")
            params.append(market)
        if status == "covered":
            where.append("covered = 1")
        elif status == "uncovered":
            where.append("covered = 0")
        if label_kw:
            where.append("(sw_l3 || sw_l2 || sw_l1 || em_industry) LIKE ?")
            params.append(f"%{label_kw}%")
        if keyword:
            where.append("(stock_code LIKE ? OR stock_name LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        where_sql = " WHERE " + " AND ".join(where)
        # COUNT(*) OVER () 随行带回过滤后总数，重 CTE+JOIN 只跑一遍（免去单独 COUNT 查询）。
        sql = (
            f"{base} SELECT *, COUNT(*) OVER () AS _total FROM r{where_sql} "
            "ORDER BY covered DESC, stock_code ASC LIMIT ? OFFSET ?"
        )
        rows = [dict(row) for row in self._conn().execute(sql, params + [limit, skip]).fetchall()]
        total = rows[0].pop("_total") if rows else 0
        for r in rows:
            r.pop("_total", None)
        return total, rows

    def init_db(self, schema_sql: str) -> None:
        conn = self._conn()
        conn.executescript(schema_sql)
        conn.commit()
