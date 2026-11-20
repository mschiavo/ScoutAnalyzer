import sqlite3
from database.setup_db import create_database

def test_auth_tables_and_default_admin(tmp_path):
    test_db = str(tmp_path / "test_auth.db")
    create_database(test_db)
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()

    # Verifica presenza tabelle
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    assert "users" in tables
    assert "user_teams" in tables
    assert "user_logins" in tables

    # Verifica colonne matches
    cur.execute("PRAGMA table_info(matches)")
    m_cols = [r[1] for r in cur.fetchall()]
    assert "storage_path" in m_cols
    assert "file_hash" in m_cols

    # Verifica creazione utente admin predefinito
    cur.execute("SELECT username, role, is_active FROM users WHERE username = 'admin'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "admin"
    assert row[1] == "ADMIN"
    assert row[2] == 1
    conn.close()
