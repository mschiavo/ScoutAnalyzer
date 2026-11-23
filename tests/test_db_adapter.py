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

def test_db_row_unpacking_and_mapping():
    from src.db import DbRow

    row = DbRow(["id", "set_number", "home_score"], [101, 2, 25])

    # 1. Unpacking like a tuple/sqlite3.Row
    set_id, set_num, h_score = row
    assert set_id == 101, f"Expected 101, got {set_id}"
    assert set_num == 2, f"Expected 2, got {set_num}"
    assert h_score == 25, f"Expected 25, got {h_score}"

    # 2. Positional indexing
    assert row[0] == 101
    assert row[1] == 2
    assert row[2] == 25

    # 3. Key access
    assert row["id"] == 101
    assert row["set_number"] == 2
    assert row["home_score"] == 25

    # 4. Conversion to dict
    d = dict(row)
    assert d == {"id": 101, "set_number": 2, "home_score": 25}

    # 5. Iteration and keys
    assert list(row) == [101, 2, 25]
    assert list(row.keys()) == ["id", "set_number", "home_score"]
    assert "id" in row
    assert "non_existent" not in row

def test_postgres_cursor_wrapper_unpacking():
    class DummyCol:
        def __init__(self, name):
            self.name = name

    class MockRawCursor:
        def __init__(self):
            self.description = [DummyCol("id"), DummyCol("set_number")]
            self._rows = [(10, 1), (20, 2)]
            self._idx = 0
            self.rowcount = 2

        def fetchone(self):
            if self._idx < len(self._rows):
                r = self._rows[self._idx]
                self._idx += 1
                return r
            return None

        def fetchall(self):
            return self._rows

    raw = MockRawCursor()
    wrapper = PostgresCursorWrapper(raw)
    rows = wrapper.fetchall()

    unpacked = []
    for s_id, s_num in rows:
        unpacked.append((s_id, s_num))

    assert unpacked == [(10, 1), (20, 2)]

def test_refresh_match_summary_metrics(tmp_path):
    from database.setup_db import create_database
    from src.db import refresh_match_summary_metrics
    import sqlite3

    db_path = str(tmp_path / "summary_test.db")
    create_database(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("INSERT INTO championships (code, name) VALUES ('2026-2027', 'B1F')")
    cur.execute("INSERT INTO teams (code, name) VALUES ('HOM', 'Home Team')")
    cur.execute("INSERT INTO teams (code, name) VALUES ('AWY', 'Away Team')")
    cur.execute("""
        INSERT INTO matches (match_code, home_team_id, away_team_id)
        VALUES ('&And01_home-away_sync_marco', 1, 2)
    """)
    match_id = cur.lastrowid

    # 3 sets: 2-1 for home
    cur.execute("INSERT INTO match_sets (match_id, set_number, home_score, away_score, winning_team) VALUES (?, 1, 25, 20, '*')", (match_id,))
    cur.execute("INSERT INTO match_sets (match_id, set_number, home_score, away_score, winning_team) VALUES (?, 2, 20, 25, 'a')", (match_id,))
    cur.execute("INSERT INTO match_sets (match_id, set_number, home_score, away_score, winning_team) VALUES (?, 3, 25, 22, '*')", (match_id,))

    # 1 event
    cur.execute("INSERT INTO events (match_id, set_id, event_index, team_code) VALUES (?, 1, 1, '*')", (match_id,))

    # 1 log
    cur.execute("INSERT INTO validation_logs (match_id, file_name, error_summary) VALUES (?, 'file.dvw', 'err')", (match_id,))

    res = refresh_match_summary_metrics(cur, match_id)
    conn.commit()

    assert res["final_score"] == "2 - 1"
    assert res["set_scores"] == "25-20, 20-25, 25-22"
    assert res["home_sets_won"] == 2
    assert res["away_sets_won"] == 1
    assert res["sets_count"] == 3
    assert res["events_count"] == 1
    assert res["logs_count"] == 1
    assert res["scout_author"] == "marco"

    cur.execute("SELECT final_score, set_scores, scout_author FROM matches WHERE id = ?", (match_id,))
    row = cur.fetchone()
    assert row[0] == "2 - 1"
    assert row[1] == "25-20, 20-25, 25-22"
    assert row[2] == "marco"
    conn.close()

def test_scout_db_path_environment_resolution(monkeypatch, tmp_path):
    from src.db import get_sqlite_path
    from src.ingestion_manager import IngestionManager
    from src.state_engine import MatchStateEngine

    custom_path = str(tmp_path / "custom_docker_data" / "scoutanalyzer.db")
    monkeypatch.setenv("SCOUT_DB_PATH", custom_path)

    assert get_sqlite_path() == custom_path
    assert get_sqlite_path("scoutanalyzer.db") == custom_path

    ingester = IngestionManager()
    assert ingester.db_path == custom_path

    engine = MatchStateEngine(match_id=1)
    assert engine.db_path == custom_path




