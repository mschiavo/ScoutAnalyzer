"""Script di inizializzazione e sincronizzazione del database PostgreSQL (Neon.tech)
a partire dallo schema e dai dati di base di ScoutAnalyzer 3000.
"""
import os
import sqlite3
import psycopg
from dotenv import load_dotenv

load_dotenv()

PG_URL = os.environ.get("DATABASE_URL")
SQLITE_PATH = "scoutanalyzer.db"

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS championships (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    id SERIAL PRIMARY KEY,
    championship_id INTEGER NOT NULL REFERENCES championships(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    name TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    homestadium TEXT,
    group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    roster_code TEXT
);

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    dv_role_code TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS players (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    birth_year INTEGER,
    role_id INTEGER REFERENCES roles(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS team_players (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    shirt_number INTEGER,
    valid_from TEXT,
    valid_to TEXT
);

CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    match_code TEXT UNIQUE,
    giornata INTEGER,
    home_team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    away_team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    scheduled_date TEXT,
    status TEXT DEFAULT 'PENDING',
    storage_path TEXT,
    file_hash TEXT,
    home_sets_won INTEGER DEFAULT 0,
    away_sets_won INTEGER DEFAULT 0,
    final_score TEXT DEFAULT '0 - 0',
    set_scores TEXT DEFAULT '',
    sets_count INTEGER DEFAULT 0,
    events_count INTEGER DEFAULT 0,
    logs_count INTEGER DEFAULT 0,
    scout_author TEXT
);

CREATE TABLE IF NOT EXISTS match_sets (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    set_number INTEGER NOT NULL,
    home_score INTEGER DEFAULT 0,
    away_score INTEGER DEFAULT 0,
    duration_minutes INTEGER,
    first_serve_team CHAR(1),
    winning_team CHAR(1),
    UNIQUE(match_id, set_number)
);

CREATE TABLE IF NOT EXISTS actions (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    set_id INTEGER NOT NULL REFERENCES match_sets(id) ON DELETE CASCADE,
    azione_index INTEGER NOT NULL,
    serving_team CHAR(1) NOT NULL,
    winning_team CHAR(1),
    score_home_before INTEGER,
    score_away_before INTEGER,
    score_home_after INTEGER,
    score_away_after INTEGER
);

CREATE TABLE IF NOT EXISTS rotations (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    set_id INTEGER NOT NULL REFERENCES match_sets(id) ON DELETE CASCADE,
    event_id INTEGER,
    serving_team CHAR(1),
    home_setter_pos INTEGER,
    away_setter_pos INTEGER,
    home_pos1 INTEGER, home_pos2 INTEGER, home_pos3 INTEGER,
    home_pos4 INTEGER, home_pos5 INTEGER, home_pos6 INTEGER,
    away_pos1 INTEGER, away_pos2 INTEGER, away_pos3 INTEGER,
    away_pos4 INTEGER, away_pos5 INTEGER, away_pos6 INTEGER,
    home_libero INTEGER, away_libero INTEGER,
    home_libero_pos INTEGER,
    away_libero_pos INTEGER,
    is_subst BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    set_id INTEGER NOT NULL REFERENCES match_sets(id) ON DELETE CASCADE,
    action_id INTEGER,
    rotation_id INTEGER,
    event_index INTEGER NOT NULL,
    team_code CHAR(1) NOT NULL,
    shirt_number INTEGER,
    player_id INTEGER,
    skill CHAR(1),
    skill_type CHAR(1),
    evaluation CHAR(1),
    combo_code TEXT,
    target_attacker TEXT,
    start_zone INTEGER,
    end_zone INTEGER,
    end_subzone CHAR(1),
    extended_code TEXT,
    video_frame INTEGER,
    home_setter_pos INTEGER,
    away_setter_pos INTEGER,
    home_pos1 INTEGER, home_pos2 INTEGER, home_pos3 INTEGER,
    home_pos4 INTEGER, home_pos5 INTEGER, home_pos6 INTEGER,
    away_pos1 INTEGER, away_pos2 INTEGER, away_pos3 INTEGER,
    away_pos4 INTEGER, away_pos5 INTEGER, away_pos6 INTEGER,
    is_valid BOOLEAN DEFAULT TRUE,
    error_note TEXT
);

CREATE TABLE IF NOT EXISTS validation_logs (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    file_name TEXT,
    line_number INTEGER,
    raw_code TEXT,
    parsed_status TEXT,
    error_summary TEXT,
    validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT,
    role TEXT NOT NULL DEFAULT 'SCOUT',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_teams (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, team_id)
);

CREATE TABLE IF NOT EXISTS user_logins (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    login_status TEXT NOT NULL,
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_match ON events(match_id, set_id);
CREATE INDEX IF NOT EXISTS idx_rotations_match ON rotations(match_id, set_id);
CREATE INDEX IF NOT EXISTS idx_logs_match ON validation_logs(match_id, severity);
CREATE INDEX IF NOT EXISTS idx_user_teams_user ON user_teams(user_id);
CREATE INDEX IF NOT EXISTS idx_user_logins_user ON user_logins(user_id, logged_at);
"""

def setup_and_seed_postgres():
    if not PG_URL:
        print("❌ DATABASE_URL non configurata. Impostare la variabile d'ambiente DATABASE_URL.")
        return
    print(f"🐘 Connessione a Neon PostgreSQL...")
    with psycopg.connect(PG_URL) as pg_conn:
        with pg_conn.cursor() as cur:
            # 1. Creazione Schema DDL
            cur.execute(PG_SCHEMA)
            cur.execute("""
                ALTER TABLE events ADD COLUMN IF NOT EXISTS is_valid BOOLEAN DEFAULT TRUE;
                ALTER TABLE events ADD COLUMN IF NOT EXISTS error_note TEXT;
                ALTER TABLE rotations ADD COLUMN IF NOT EXISTS home_libero_pos INTEGER;
                ALTER TABLE rotations ADD COLUMN IF NOT EXISTS away_libero_pos INTEGER;
                ALTER TABLE validation_logs ADD COLUMN IF NOT EXISTS file_name TEXT;
                ALTER TABLE validation_logs ADD COLUMN IF NOT EXISTS line_number INTEGER;
                ALTER TABLE validation_logs ADD COLUMN IF NOT EXISTS parsed_status TEXT;
                ALTER TABLE validation_logs ADD COLUMN IF NOT EXISTS error_summary TEXT;
                ALTER TABLE validation_logs ADD COLUMN IF NOT EXISTS validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                ALTER TABLE matches ADD COLUMN IF NOT EXISTS home_sets_won INTEGER DEFAULT 0;
                ALTER TABLE matches ADD COLUMN IF NOT EXISTS away_sets_won INTEGER DEFAULT 0;
                ALTER TABLE matches ADD COLUMN IF NOT EXISTS final_score TEXT DEFAULT '0 - 0';
                ALTER TABLE matches ADD COLUMN IF NOT EXISTS set_scores TEXT DEFAULT '';
                ALTER TABLE matches ADD COLUMN IF NOT EXISTS sets_count INTEGER DEFAULT 0;
                ALTER TABLE matches ADD COLUMN IF NOT EXISTS events_count INTEGER DEFAULT 0;
                ALTER TABLE matches ADD COLUMN IF NOT EXISTS logs_count INTEGER DEFAULT 0;
                ALTER TABLE matches ADD COLUMN IF NOT EXISTS scout_author TEXT;
            """)
            pg_conn.commit()
            print("✅ Schema 16 tabelle e indici verificati su Neon PostgreSQL.")

            # 2. Seeding da SQLite se presente
            if os.path.exists(SQLITE_PATH):
                s_conn = sqlite3.connect(SQLITE_PATH)
                s_cur = s_conn.cursor()

                # Ruoli
                s_cur.execute("SELECT id, code, name, dv_role_code FROM roles")
                for r in s_cur.fetchall():
                    cur.execute("""
                        INSERT INTO roles (id, code, name, dv_role_code) 
                        VALUES (%s, %s, %s, %s) 
                        ON CONFLICT (code) DO NOTHING
                    """, r)

                # Campionati
                s_cur.execute("SELECT id, code, name FROM championships")
                for r in s_cur.fetchall():
                    cur.execute("""
                        INSERT INTO championships (id, code, name) 
                        VALUES (%s, %s, %s) 
                        ON CONFLICT (code) DO NOTHING
                    """, r)

                # Gironi
                s_cur.execute("SELECT id, championship_id, code, name FROM groups")
                for r in s_cur.fetchall():
                    cur.execute("""
                        INSERT INTO groups (id, championship_id, code, name) 
                        VALUES (%s, %s, %s, %s) 
                        ON CONFLICT DO NOTHING
                    """, r)

                # Squadre
                s_cur.execute("SELECT id, code, name, homestadium, group_id, roster_code FROM teams")
                for r in s_cur.fetchall():
                    cur.execute("""
                        INSERT INTO teams (id, code, name, homestadium, group_id, roster_code) 
                        VALUES (%s, %s, %s, %s, %s, %s) 
                        ON CONFLICT (code) DO NOTHING
                    """, r)

                # Utenti
                s_cur.execute("SELECT id, username, password_hash, email, role, is_active FROM users")
                for r in s_cur.fetchall():
                    u_row = (r[0], r[1], r[2], r[3], r[4], bool(r[5]))
                    cur.execute("""
                        INSERT INTO users (id, username, password_hash, email, role, is_active) 
                        VALUES (%s, %s, %s, %s, %s, %s) 
                        ON CONFLICT (username) DO NOTHING
                    """, u_row)

                # Squadre per utenti
                s_cur.execute("SELECT user_id, team_id FROM user_teams WHERE user_id IN (SELECT id FROM users)")
                for r in s_cur.fetchall():
                    cur.execute("""
                        INSERT INTO user_teams (user_id, team_id) 
                        VALUES (%s, %s) 
                        ON CONFLICT DO NOTHING
                    """, r)

                # Atlete
                s_cur.execute("SELECT id, code, first_name, last_name, birth_year, role_id FROM players")
                for r in s_cur.fetchall():
                    cur.execute("""
                        INSERT INTO players (id, code, first_name, last_name, birth_year, role_id) 
                        VALUES (%s, %s, %s, %s, %s, %s) 
                        ON CONFLICT (code) DO NOTHING
                    """, r)

                # Relazione Squadra-Atlete
                s_cur.execute("SELECT id, team_id, player_id, shirt_number, valid_from, valid_to FROM team_players")
                for r in s_cur.fetchall():
                    cur.execute("""
                        INSERT INTO team_players (id, team_id, player_id, shirt_number, valid_from, valid_to) 
                        VALUES (%s, %s, %s, %s, %s, %s) 
                        ON CONFLICT DO NOTHING
                    """, r)

                s_conn.close()

                # Sincronizza i contatori delle chiavi SERIAL primarie
                tables_with_serial = ["championships", "groups", "teams", "roles", "players", "team_players", "users", "matches", "match_sets", "actions", "rotations", "events", "validation_logs", "user_logins"]
                for tbl in tables_with_serial:
                    cur.execute(f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), coalesce((SELECT max(id) FROM {tbl}), 1));")

                pg_conn.commit()
                print("✅ Dati di base (squadre, utenti, campionati) sincronizzati con successo su Neon.")

            # Conteggio finale
            cur.execute("SELECT count(*) FROM users;")
            users_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM teams;")
            teams_count = cur.fetchone()[0]
            print(f"🎉 Database Neon PostgreSQL pronto: {users_count} utenti, {teams_count} squadre.")

if __name__ == "__main__":
    setup_and_seed_postgres()
