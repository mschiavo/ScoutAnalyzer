"""Modulo di accesso al database unificato per ScoutAnalyzer 3000.
Supporta in modo trasparente sia SQLite (locale/offline) sia PostgreSQL (Neon.tech / Cloud)
permettendo l'esecuzione del medesimo codice e delle stesse query SQL su entrambi i database.
"""
import os
import re
import sqlite3
from typing import Optional, Any, Dict, List
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config/config.json"


def get_database_url() -> Optional[str]:
    """Restituisce l'URL di connessione PostgreSQL se configurato in ambiente."""
    return os.environ.get("DATABASE_URL")


def get_sqlite_path() -> str:
    """Restituisce il path del file SQLite locale."""
    env_path = os.environ.get("SCOUT_DB_PATH")
    if env_path:
        return env_path
    if os.path.exists(DEFAULT_CONFIG_PATH):
        try:
            import json
            with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                p = cfg.get("db_path", "scoutanalyzer.db")
                if os.path.exists(p):
                    return p
        except Exception:
            pass
    root_candidate = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scoutanalyzer.db")
    if os.path.exists(root_candidate):
        return root_candidate
    return "scoutanalyzer.db"


class DbRow(dict):
    """Oggetto riga che supporta sia l'accesso per chiave dizionario (r['name'])
    sia l'accesso per indice numerico (r[0]), identico al comportamento di sqlite3.Row."""
    def __init__(self, cols, vals):
        super().__init__(zip(cols, vals))
        self._vals = tuple(vals)

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._vals[item]
        return super().__getitem__(item)


class PostgresCursorWrapper:
    """Wrapper per il cursore psycopg per garantire la compatibilità con l'API sqlite3."""
    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self.lastrowid = None

    @property
    def rowcount(self):
        return self._cur.rowcount

    def _wrap_row(self, row):
        if row is None:
            return None
        if self._cur.description:
            cols = [d.name for d in self._cur.description]
            return DbRow(cols, row)
        return row

    def _convert_query(self, sql: str) -> Optional[str]:
        q = sql.strip()
        # I comandi PRAGMA di SQLite non esistono e non servono in PostgreSQL
        if q.upper().startswith("PRAGMA"):
            return None

        # Conversione di INSERT OR IGNORE INTO in PostgreSQL ON CONFLICT DO NOTHING
        if re.search(r'\bINSERT\s+OR\s+IGNORE\s+INTO\b', q, re.IGNORECASE):
            q = re.sub(r'\bINSERT\s+OR\s+IGNORE\s+INTO\b', 'INSERT INTO', q, flags=re.IGNORECASE)
            if 'ON CONFLICT' not in q.upper():
                q = q.rstrip('; ') + ' ON CONFLICT DO NOTHING'

        # Conversione dei placeholder da '?' (SQLite) a '%s' (PostgreSQL psycopg)
        q = q.replace("?", "%s")

        # Conversione confronti booleani per PostgreSQL
        q = re.sub(r'\be\.is_valid\s*=\s*0\b', 'e.is_valid = FALSE', q, flags=re.IGNORECASE)
        q = re.sub(r'\be\.is_valid\s*=\s*1\b', 'e.is_valid = TRUE', q, flags=re.IGNORECASE)
        return q

    def execute(self, sql: str, params=None):
        q = self._convert_query(sql)
        if q is None:
            return self

        # Se è una INSERT e non ha già RETURNING, intercetta lastrowid se possibile
        is_insert = q.strip().upper().startswith("INSERT INTO") and "RETURNING" not in q.upper() and "DO NOTHING" not in q.upper()
        if is_insert:
            q_returning = q.rstrip('; ') + " RETURNING id"
            try:
                self._cur.execute(q_returning, params or ())
                row = self._cur.fetchone()
                if row:
                    if isinstance(row, dict) and "id" in row:
                        self.lastrowid = row["id"]
                    elif isinstance(row, dict):
                        self.lastrowid = list(row.values())[0]
                    else:
                        self.lastrowid = row[0]
                return self
            except Exception:
                # Fallback sull'esecuzione normale in caso di tabelle senza colonna 'id'
                pass

        self._cur.execute(q, params or ())
        return self

    def executemany(self, sql: str, seq_of_params):
        q = self._convert_query(sql)
        if q is None:
            return self
        self._cur.executemany(q, seq_of_params)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        return self._wrap_row(row)

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        cols = [d.name for d in self._cur.description] if self._cur.description else []
        return [DbRow(cols, r) for r in rows]

    def __iter__(self):
        for r in self._cur:
            yield self._wrap_row(r)

    def close(self):
        self._cur.close()


class PostgresConnectionWrapper:
    """Wrapper per la connessione psycopg per garantire compatibilità con sqlite3."""
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return PostgresCursorWrapper(self._conn.cursor())

    def execute(self, sql: str, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db_connection(db_path: Optional[str] = None) -> Any:
    """Restituisce una connessione al database attivo:
    - PostgreSQL (Neon.tech) se DATABASE_URL è presente;
    - SQLite locale altrimenti.
    """
    pg_url = get_database_url()
    if pg_url:
        try:
            import psycopg
            clean_url = pg_url.replace("postgres://", "postgresql://")
            raw_conn = psycopg.connect(clean_url)
            return PostgresConnectionWrapper(raw_conn)
        except Exception as e:
            logger.warning(f"[DB] Errore connessione a PostgreSQL ({e}), fallback su SQLite locale.")

    # SQLite Fallback
    path = db_path or get_sqlite_path()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn
