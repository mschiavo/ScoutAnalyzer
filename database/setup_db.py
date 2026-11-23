import sys
import os
import sqlite3

# Assicura che la radice del repository sia sempre in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import get_sqlite_path
DB_PATH = get_sqlite_path()

SCHEMA_DDL = """
PRAGMA foreign_keys = ON;

-- 1. Tabella dei Campionati (es. 2026/2027)
CREATE TABLE IF NOT EXISTS championships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,       -- es. "2026-2027"
    name TEXT NOT NULL               -- es. "Campionato Serie B1 Femminile"
);

-- 2. Tabella dei Gironi (es. Girone B)
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    championship_id INTEGER NOT NULL,
    code TEXT NOT NULL,              -- es. "A", "B", "C", "D"
    name TEXT,                       -- es. "Girone B B1 Femminile"
    FOREIGN KEY (championship_id) REFERENCES championships(id) ON DELETE CASCADE
);

-- 3. Tabella delle Squadre
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,       -- Codice identificativo nel file scout (es. VIC26)
    name TEXT NOT NULL,              -- Nome completo della società
    homestadium TEXT,
    group_id INTEGER,                -- A quale girone appartiene la squadra
    roster_code TEXT,                -- Codice per il download del file .sq (es. "2761")
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL
);

-- 4. Tabella dei Ruoli (con codice Data Volley nativo)
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,       -- es. "P", "S", "C", "O", "L"
    name TEXT NOT NULL,              -- es. "Palleggiatore", "Schiacciatore", ecc.
    dv_role_code TEXT UNIQUE         -- Codice numerico Data Volley .sq (es. "1", "2", "3", "4", "5")
);

-- 5. Tabella delle Atlete (Roster generale)
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,       -- Codice identificativo atlete nello scout o federale
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    birth_year INTEGER,
    role_id INTEGER,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE SET NULL
);

-- 6. Tabella di Relazione Squadra-Atleta (Roster con storico trasferimenti)
CREATE TABLE IF NOT EXISTS team_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    shirt_number INTEGER,            -- Numero di maglia in quella squadra
    valid_from TEXT,                 -- Data inizio validità tesseramento (YYYY-MM-DD)
    valid_to TEXT,                   -- Data fine validità (NULL se ancora attiva)
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- 7. Tabella delle Partite / Calendario
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER,                -- Riferimento al girone di appartenenza
    match_code TEXT UNIQUE,          -- Codice file match DataVolley
    giornata INTEGER,                -- Numero della giornata (es. 1, 2, ...)
    home_team_id INTEGER NOT NULL,
    away_team_id INTEGER NOT NULL,
    scheduled_date TEXT,
    status TEXT DEFAULT 'PENDING',   -- PENDING, VALIDATED, ERROR
    storage_path TEXT,               -- Percorso relativo nello storage gestito o key cloud
    file_hash TEXT,                  -- Hash MD5/SHA-256 del file DVW per verifica integrità
    home_sets_won INTEGER DEFAULT 0,
    away_sets_won INTEGER DEFAULT 0,
    final_score TEXT DEFAULT '0 - 0',
    set_scores TEXT DEFAULT '',
    sets_count INTEGER DEFAULT 0,
    events_count INTEGER DEFAULT 0,
    logs_count INTEGER DEFAULT 0,
    scout_author TEXT,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL,
    FOREIGN KEY (home_team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (away_team_id) REFERENCES teams(id) ON DELETE CASCADE
);

-- 8. Tabella dei Set disputati
CREATE TABLE IF NOT EXISTS match_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    set_number INTEGER NOT NULL,     -- 1, 2, 3, 4, 5
    home_score INTEGER DEFAULT 0,
    away_score INTEGER DEFAULT 0,
    duration_minutes INTEGER,        -- Durata del set in minuti
    first_serve_team CHAR(1),        -- '*' (Home) o 'a' (Away)
    winning_team CHAR(1),            -- '*' (Home) o 'a' (Away)
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    UNIQUE(match_id, set_number)
);

-- 9. Tabella delle Azioni / Rally
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    set_id INTEGER NOT NULL,
    azione_index INTEGER NOT NULL,
    serving_team CHAR(1) NOT NULL,
    winning_team CHAR(1),
    score_home_before INTEGER,
    score_away_before INTEGER,
    score_home_after INTEGER,
    score_away_after INTEGER,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (set_id) REFERENCES match_sets(id) ON DELETE CASCADE
);

-- 10. Tabella Rotations (Fotografia schieramento in campo per validazione semantica)
CREATE TABLE IF NOT EXISTS rotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    set_id INTEGER NOT NULL,
    event_id INTEGER,
    serving_team CHAR(1),            -- '*' (Home) o 'a' (Away)
    home_setter_pos INTEGER,         -- Posizione palleggiatore Home (1-6)
    away_setter_pos INTEGER,         -- Posizione palleggiatore Away (1-6)
    home_pos1 INTEGER, home_pos2 INTEGER, home_pos3 INTEGER,
    home_pos4 INTEGER, home_pos5 INTEGER, home_pos6 INTEGER,
    away_pos1 INTEGER, away_pos2 INTEGER, away_pos3 INTEGER,
    away_pos4 INTEGER, away_pos5 INTEGER, away_pos6 INTEGER,
    home_libero INTEGER, away_libero INTEGER,
    home_libero_pos INTEGER,         -- Zona occupata dal libero Home (es. 5 o 6, o NULL se in panchina)
    away_libero_pos INTEGER,         -- Zona occupata dal libero Away (es. 5 o 6, o NULL se in panchina)
    is_subst BOOLEAN DEFAULT 0,      -- 1 se generata da una sostituzione
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (set_id) REFERENCES match_sets(id) ON DELETE CASCADE
);

-- 11. Tabella Eventi (Singolo tocco / riga scout DataVolley)
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    set_id INTEGER NOT NULL,
    action_id INTEGER,
    rotation_id INTEGER,
    event_index INTEGER NOT NULL,
    team_code CHAR(1) NOT NULL,       -- '*' (Home) o 'a' (Away)
    shirt_number INTEGER,
    player_id INTEGER,
    skill CHAR(1),                    -- S, R, A, B, D, E, etc.
    skill_type CHAR(1),
    evaluation CHAR(1),               -- #, +, !, -, /, =
    combo_code TEXT,                  -- Codice combinazione attacco (es. K1, K2, X1)
    target_attacker TEXT,             -- Bersaglio alzata o chiamata palleggiatore
    start_zone INTEGER,
    end_zone INTEGER,
    end_subzone CHAR(1),
    extended_code TEXT,
    video_frame INTEGER,              -- Frame o timestamp video sincronizzato
    home_setter_pos INTEGER,
    away_setter_pos INTEGER,
    home_pos1 INTEGER, home_pos2 INTEGER, home_pos3 INTEGER,
    home_pos4 INTEGER, home_pos5 INTEGER, home_pos6 INTEGER,
    away_pos1 INTEGER, away_pos2 INTEGER, away_pos3 INTEGER,
    away_pos4 INTEGER, away_pos5 INTEGER, away_pos6 INTEGER,
    is_valid BOOLEAN DEFAULT 1,
    error_note TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (set_id) REFERENCES match_sets(id) ON DELETE CASCADE,
    FOREIGN KEY (action_id) REFERENCES actions(id) ON DELETE SET NULL,
    FOREIGN KEY (rotation_id) REFERENCES rotations(id) ON DELETE SET NULL,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE SET NULL
);

-- 12. Tabella Log di Validazione e Parsing
CREATE TABLE IF NOT EXISTS validation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    file_name TEXT NOT NULL,
    line_number INTEGER,
    raw_code TEXT,
    parsed_status TEXT CHECK(parsed_status IN ('OK', 'WARNING', 'ERROR')) DEFAULT 'OK',
    error_summary TEXT,
    validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

-- 13. Indici per ottimizzazione performance query analitiche
CREATE INDEX IF NOT EXISTS idx_events_match ON events(match_id, set_id, event_index);
CREATE INDEX IF NOT EXISTS idx_rotations_match ON rotations(match_id, set_id);
CREATE INDEX IF NOT EXISTS idx_logs_match ON validation_logs(match_id, line_number);

-- 14. Tabella Utenti
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT UNIQUE,
    role TEXT CHECK(role IN ('ADMIN', 'SCOUT')) DEFAULT 'SCOUT',
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. Tabella Associazioni Utente - Squadre Autorizzate (Multi-Tenancy)
CREATE TABLE IF NOT EXISTS user_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    UNIQUE(user_id, team_id)
);

-- 16. Tabella Tracciamento Accessi / Audit Login
CREATE TABLE IF NOT EXISTS user_logins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    login_status TEXT CHECK(login_status IN ('SUCCESS', 'FAILED')) DEFAULT 'SUCCESS',
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_user_teams_user ON user_teams(user_id);
CREATE INDEX IF NOT EXISTS idx_user_logins_user ON user_logins(user_id, logged_at);
"""

def create_database(db_path: Optional[str] = None):
    """Inizializza o aggiorna il database unificato con tutte le 16 tabelle relazionali."""
    target_db = get_sqlite_path(db_path)
    os.makedirs(os.path.dirname(os.path.abspath(target_db)), exist_ok=True)
    conn = sqlite3.connect(target_db)
    cursor = conn.cursor()
    cursor.executescript(SCHEMA_DDL)

    # Migrazione colonne se la tabella events esisteva già
    cursor.execute("PRAGMA table_info(events)")
    existing_cols = {r[1] for r in cursor.fetchall()}
    new_cols = [
        ("home_setter_pos", "INTEGER"),
        ("away_setter_pos", "INTEGER"),
        ("home_pos1", "INTEGER"), ("home_pos2", "INTEGER"), ("home_pos3", "INTEGER"),
        ("home_pos4", "INTEGER"), ("home_pos5", "INTEGER"), ("home_pos6", "INTEGER"),
        ("away_pos1", "INTEGER"), ("away_pos2", "INTEGER"), ("away_pos3", "INTEGER"),
        ("away_pos4", "INTEGER"), ("away_pos5", "INTEGER"), ("away_pos6", "INTEGER"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE events ADD COLUMN {col_name} {col_type}")

    # Migrazione colonne per matches (storage_path, file_hash, metriche di riepilogo)
    cursor.execute("PRAGMA table_info(matches)")
    m_cols = {r[1] for r in cursor.fetchall()}
    if "storage_path" not in m_cols:
        cursor.execute("ALTER TABLE matches ADD COLUMN storage_path TEXT")
    if "file_hash" not in m_cols:
        cursor.execute("ALTER TABLE matches ADD COLUMN file_hash TEXT")

    new_match_cols = [
        ("home_sets_won", "INTEGER DEFAULT 0"),
        ("away_sets_won", "INTEGER DEFAULT 0"),
        ("final_score", "TEXT DEFAULT '0 - 0'"),
        ("set_scores", "TEXT DEFAULT ''"),
        ("sets_count", "INTEGER DEFAULT 0"),
        ("events_count", "INTEGER DEFAULT 0"),
        ("logs_count", "INTEGER DEFAULT 0"),
        ("scout_author", "TEXT")
    ]
    for col_name, col_type in new_match_cols:
        if col_name not in m_cols:
            cursor.execute(f"ALTER TABLE matches ADD COLUMN {col_name} {col_type}")

    # Inserimento ruoli standard pallavolo se non presenti
    standard_roles = [
        ("L", "Libero", "1"),
        ("S", "Schiacciatore", "2"),
        ("O", "Opposto", "3"),
        ("C", "Centrale", "4"),
        ("P", "Palleggiatore", "5")
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO roles (code, name, dv_role_code) VALUES (?, ?, ?)
    """, standard_roles)

    # Seeding utente admin predefinito se assente
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        import bcrypt
        admin_pwd_hash = bcrypt.hashpw(b"adminpassword", bcrypt.gensalt()).decode("utf-8")
        cursor.execute("""
            INSERT INTO users (username, password_hash, email, role, is_active)
            VALUES (?, ?, ?, 'ADMIN', 1)
        """, ("admin", admin_pwd_hash, "admin@scoutanalyzer.local"))

    conn.commit()
    conn.close()
    print(f"Database SQLite '{db_path}' inizializzato con successo con lo schema DDL unificato (16 tabelle).")

if __name__ == "__main__":
    import os
    if os.environ.get("DATABASE_URL"):
        from scripts.migrate_sqlite_to_postgres import setup_and_seed_postgres
        setup_and_seed_postgres()
    else:
        create_database()
