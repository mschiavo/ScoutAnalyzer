import os
import pytest
from src.db import get_db_connection, PostgresCursorWrapper

def test_sqlite_fallback_default(tmp_path):
    db_file = str(tmp_path / "test_local.db")
    conn = get_db_connection(db_file)
    assert conn is not None
    cur = conn.cursor()
    cur.execute("CREATE TABLE test_tab (id INTEGER PRIMARY KEY, val TEXT);")
    cur.execute("INSERT INTO test_tab (val) VALUES (?);", ("hello",))
    conn.commit()

    cur.execute("SELECT * FROM test_tab WHERE id = ?;", (1,))
    row = cur.fetchone()
    assert row["val"] == "hello"
    conn.close()

def test_postgres_query_conversion():
    class DummyCursor:
        pass

    wrapper = PostgresCursorWrapper(DummyCursor())

    # 1. PRAGMA ignored
    assert wrapper._convert_query("PRAGMA foreign_keys = ON;") is None

    # 2. Placeholders converted
    q = "SELECT * FROM users WHERE username = ? AND is_active = ?"
    assert wrapper._convert_query(q) == "SELECT * FROM users WHERE username = %s AND is_active = %s"

    # 3. INSERT OR IGNORE converted
    q_ins = "INSERT OR IGNORE INTO roles (code, name) VALUES (?, ?)"
    assert wrapper._convert_query(q_ins) == "INSERT INTO roles (code, name) VALUES (%s, %s) ON CONFLICT DO NOTHING"
