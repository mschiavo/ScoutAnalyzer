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


def scout_filename_metadata(match_code: str):
    """Return the round and sharing account encoded in a standard scout filename."""
    match = re.fullmatch(r"&(\d+)_([A-Za-z0-9]+)-([A-Za-z0-9]+)_(.+)", match_code or "")
    return (int(match[1]), match[4]) if match else (None, None)

DEFAULT_CONFIG_PATH = "config/config.json"


def get_database_url() -> Optional[str]:
    """Restituisce l'URL di connessione PostgreSQL se configurato in ambiente."""
    return os.environ.get("DATABASE_URL")


def get_sqlite_path(db_path: Optional[str] = None) -> str:
    """Restituisce il path del file SQLite locale.
    Se SCOUT_DB_PATH è impostato nell'ambiente (es. in Docker), ha la precedenza
    assoluta rispetto a qualsiasi path predefinito.
    Un db_path esplicito di test (es. pytest tmp_path) viene rispettato.
    """
    env_path = os.environ.get("SCOUT_DB_PATH")
    if db_path and ("test" in db_path.lower() or "tmp" in db_path.lower()):
        return db_path
    if env_path:
        return env_path
    if db_path and db_path != "scoutanalyzer.db":
        return db_path
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


class DbRow:
    """Oggetto riga che supporta sia l'accesso per chiave dizionario (r['name'])
    sia l'accesso per indice numerico (r[0]), identico al comportamento di sqlite3.Row.
    L'iterazione (es. for a, b in row o list(row)) restituisce i valori delle colonne,
    mentre .keys() restituisce i nomi delle colonne, supportando nativamente dict(row)."""
    def __init__(self, cols, vals):
        self._cols = tuple(cols)
        self._vals = tuple(vals)
        self._map = dict(zip(cols, vals))

    def __getitem__(self, item):
        if isinstance(item, (int, slice)):
            return self._vals[item]
        return self._map[item]

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)

    def __contains__(self, key):
        return key in self._map

    def get(self, key, default=None):
        return self._map.get(key, default)

    def keys(self):
        return list(self._cols)

    def values(self):
        return list(self._vals)

    def items(self):
        return list(self._map.items())

    def __repr__(self):
        return f"<DbRow {self._map}>"

    def __eq__(self, other):
        if isinstance(other, DbRow):
            return self._vals == other._vals and self._cols == other._cols
        if isinstance(other, (tuple, list)):
            return self._vals == tuple(other)
        if isinstance(other, dict):
            return self._map == other
        return False


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


def _ensure_sqlite_matches_schema(conn: sqlite3.Connection):
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='matches'")
        if cur.fetchone():
            cur.execute("PRAGMA table_info(matches)")
            cols = {r[1] for r in cur.fetchall()}
            new_cols = [
                ("home_sets_won", "INTEGER DEFAULT 0"),
                ("away_sets_won", "INTEGER DEFAULT 0"),
                ("final_score", "TEXT DEFAULT '0 - 0'"),
                ("set_scores", "TEXT DEFAULT ''"),
                ("sets_count", "INTEGER DEFAULT 0"),
                ("events_count", "INTEGER DEFAULT 0"),
                ("logs_count", "INTEGER DEFAULT 0"),
                ("scout_author", "TEXT"),
                ("audit_scope", "TEXT"),
                ("source_match_code", "TEXT"),
                ("scout_hash", "TEXT"),
            ]
            for col_name, col_type in new_cols:
                if col_name not in cols:
                    cur.execute(f"ALTER TABLE matches ADD COLUMN {col_name} {col_type}")
            conn.commit()
    except Exception:
        pass


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
    path = get_sqlite_path(db_path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    _ensure_sqlite_matches_schema(conn)
    return conn


def refresh_match_summary_metrics(cursor: Any, match_id: int) -> Dict[str, Any]:
    """Ricalcola e memorizza le colonne di riepilogo su matches per match_id.
    Aggiorna home_sets_won, away_sets_won, final_score, set_scores, sets_count,
    events_count, logs_count e scout_author per velocizzare list_matches (zero N+1).
    """
    cursor.execute("SELECT COALESCE(source_match_code, match_code) FROM matches WHERE id = ?", (match_id,))
    m_row = cursor.fetchone()
    match_code = m_row[0] if m_row else ""

    _, scout_author = scout_filename_metadata(match_code)
    if match_code and not scout_author:
        parts = match_code.split("_")
        if len(parts) > 1:
            author_candidate = parts[-1]
            if author_candidate.lower() == "sync" and len(parts) > 2:
                author_candidate = parts[-2]
            if author_candidate and len(author_candidate) <= 30:
                scout_author = author_candidate

    cursor.execute("""
        SELECT set_number, home_score, away_score, winning_team
        FROM match_sets
        WHERE match_id = ?
        ORDER BY set_number ASC
    """, (match_id,))
    sets = cursor.fetchall()

    h_won = 0
    a_won = 0
    partials = []
    for s in sets:
        s_num = s[0] if isinstance(s, (tuple, list)) else s["set_number"]
        h_s = s[1] if isinstance(s, (tuple, list)) else s["home_score"]
        a_s = s[2] if isinstance(s, (tuple, list)) else s["away_score"]
        w_t = s[3] if isinstance(s, (tuple, list)) else s["winning_team"]
        if w_t == "*":
            h_won += 1
        elif w_t == "a":
            a_won += 1
        elif h_s is not None and a_s is not None:
            if h_s > a_s:
                h_won += 1
            elif a_s > h_s:
                a_won += 1
        if h_s is not None and a_s is not None:
            partials.append(f"{h_s}-{a_s}")

    final_score = f"{h_won} - {a_won}" if (h_won > 0 or a_won > 0) else "0 - 0"
    set_scores_str = ", ".join(partials) if partials else ""
    sets_count = len(sets)

    cursor.execute("SELECT COUNT(*) FROM events WHERE match_id = ?", (match_id,))
    ev_row = cursor.fetchone()
    events_count = ev_row[0] if ev_row else 0

    cursor.execute("""
        SELECT COUNT(*) FROM validation_logs WHERE match_id = ?
        AND NOT (COALESCE(validation_source, '') = 'ROSTER_VARIATION' AND COALESCE(parsed_status, '') = 'OK')
    """, (match_id,))
    log_row = cursor.fetchone()
    logs_count = log_row[0] if log_row else 0

    cursor.execute("""
        UPDATE matches SET
            home_sets_won = ?,
            away_sets_won = ?,
            final_score = ?,
            set_scores = ?,
            sets_count = ?,
            events_count = ?,
            logs_count = ?,
            scout_author = ?
        WHERE id = ?
    """, (h_won, a_won, final_score, set_scores_str, sets_count, events_count, logs_count, scout_author, match_id))

    return {
        "match_id": match_id,
        "home_sets_won": h_won,
        "away_sets_won": a_won,
        "final_score": final_score,
        "set_scores": set_scores_str,
        "sets_count": sets_count,
        "events_count": events_count,
        "logs_count": logs_count,
        "scout_author": scout_author
    }

