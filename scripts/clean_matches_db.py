"""Script di pulizia delle partite di esempio e dati correlati (events, rotations, logs)
dal database scoutanalyzer.db, lasciando intatti utenti, ruoli, squadre e campionati.
"""
import sqlite3
import os

DB_PATH = "scoutanalyzer.db"

def clean_matches(db_path: str = DB_PATH):
    if not os.path.exists(db_path):
        print(f"Database {db_path} non trovato.")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON;")

    print(f"🧹 Pulizia partite dal database '{db_path}'...")

    # Tabelle correlate ai match da svuotare
    tables_to_clear = [
        "actions",
        "rotations",
        "events",
        "validation_logs",
        "match_sets",
        "matches"
    ]

    for tbl in tables_to_clear:
        c.execute(f"DELETE FROM {tbl};")
        print(f"   ↳ Tabella '{tbl}' svuotata.")

    # Reset degli ID autoincrementanti per queste tabelle
    c.execute("""
        DELETE FROM sqlite_sequence 
        WHERE name IN ('matches', 'match_sets', 'events', 'rotations', 'actions', 'validation_logs');
    """)

    conn.commit()
    conn.execute("VACUUM;")
    conn.close()

    # Verifica stato
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM matches;")
    m_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users;")
    u_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM teams;")
    t_count = c.fetchone()[0]
    conn.close()

    print(f"✅ Pulizia completata!")
    print(f"   - Partite rimanenti: {m_count}")
    print(f"   - Utenti presenti:   {u_count}")
    print(f"   - Squadre presenti:  {t_count}")

if __name__ == "__main__":
    clean_matches()
