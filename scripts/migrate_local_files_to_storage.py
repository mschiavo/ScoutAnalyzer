import os
import sys
import glob
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.storage_manager import StorageManager

DB_PATH = "scoutanalyzer.db"
VOLLEY_SOURCE_DIR = r"D:\Volley\B1FB"

def migrate_historical_files():
    print("=== AVVIO MIGRAZIONE FILE STORICI DVW IN STORAGE GESTITO ===")
    if not os.path.exists(VOLLEY_SOURCE_DIR):
        print(f"[!] Directory sorgente non trovata: {VOLLEY_SOURCE_DIR}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT id, match_code FROM matches")
    matches = c.fetchall()
    print(f"Partite censite nel database: {len(matches)}")

    dvw_files = glob.glob(os.path.join(VOLLEY_SOURCE_DIR, "**", "*.dvw"), recursive=True)
    print(f"File DVW trovati su disco: {len(dvw_files)}")

    dvw_map = {}
    for p in dvw_files:
        base = os.path.basename(p)
        name_no_ext = os.path.splitext(base)[0]
        dvw_map[base] = p
        dvw_map[name_no_ext] = p

    storage = StorageManager()
    migrated_count = 0

    for m in matches:
        m_id = m["id"]
        m_code = m["match_code"]

        src_path = dvw_map.get(f"{m_code}.dvw") or dvw_map.get(m_code)
        if src_path and os.path.exists(src_path):
            with open(src_path, "rb") as f:
                content = f.read()

            season = "2026-2027"
            rel_path, f_hash = storage.save_dvw(content, f"{m_code}.dvw", season=season)

            c.execute("""
                UPDATE matches SET storage_path = ?, file_hash = ? WHERE id = ?
            """, (rel_path, f_hash, m_id))

            migrated_count += 1
            print(f" [OK] Match #{m_id} ({m_code}) -> {rel_path} (hash: {f_hash[:8]}...)")
        else:
            print(f" [!] File non trovato per Match #{m_id} ({m_code})")

    conn.commit()
    conn.close()
    print(f"\nMigrazione completata con successo! {migrated_count} file archiviati in storage/dvw/.")

if __name__ == "__main__":
    migrate_historical_files()
