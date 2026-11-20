"""Script di migrazione e sincronizzazione automatica dei file DVW su Cloudflare R2
con applicazione della gerarchia federale standard:
<campionato>/<categoria>/<girone>/<giornata>/<filename>
"""
import os
import sys
import re
import sqlite3
from typing import Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.storage_manager import StorageManager, build_storage_key

def infer_hierarchy_from_code(match_code: str, fallback_giornata: int = 1) -> Tuple[str, str, str, str]:
    """Deduce campionato, categoria, girone e giornata dal codice o nome file del match."""
    campionato = "2026-2027"
    categoria = "B1F"
    girone = "B"

    lower = match_code.lower()

    # Categoria e girone
    cat_match = re.search(r'(b1f|b2f|a1f|a2f|cf|df)([a-z])', lower)
    if cat_match:
        categoria = cat_match.group(1).upper()
        girone = cat_match.group(2).upper()

    # Giornata
    gio_match = re.search(r'(?:and|giornata|&|^|\D)(\d{1,2})', lower)
    if gio_match:
        giornata = f"{int(gio_match.group(1)):02d}"
    else:
        giornata = f"{fallback_giornata:02d}"

    return campionato, categoria, girone, giornata

def main():
    print("=" * 70)
    print("🚀 Sincronizzazione Partite Reali su Cloudflare R2 (Gerarchia Federale)")
    print("=" * 70)

    # Inizializza StorageManager con S3/R2 attivo
    storage = StorageManager(backend="s3")
    print(f"📦 Endpoint S3/R2: {storage.endpoint_url}")
    print(f"🪣 Bucket Name:   {storage.bucket_name}")
    print(f"🔑 Client S3:     {'Inizializzato con successo' if storage.s3_client else 'NON DISPONIBILE'}")

    if not storage.s3_client:
        print("❌ Errore: Credenziali S3/R2 non trovate o non valide in .env. Interruzione.")
        return

    db_path = "scoutanalyzer.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        SELECT id, match_code, storage_path, file_hash 
        FROM matches 
        WHERE id <= 7 OR (storage_path IS NOT NULL AND storage_path != '')
        ORDER BY id ASC
    """)
    matches = c.fetchall()

    print(f"\n🔍 Trovate {len(matches)} partite da sincronizzare nel database.\n")

    synced_count = 0
    errors_count = 0

    for idx, (m_id, m_code, curr_storage_path, curr_hash) in enumerate(matches, 1):
        # Determina dove trovare il file locale
        local_candidates = []
        if curr_storage_path:
            local_candidates.append(os.path.join(storage.base_dir, curr_storage_path))
        
        # Anche cartelle storiche come fallback
        filename_only = os.path.basename(curr_storage_path) if curr_storage_path else f"{m_code}.dvw"
        local_candidates.append(os.path.join("storage", "dvw", "2026-2027", filename_only))
        local_candidates.append(os.path.join(r"D:\Volley\B1FB", "esempi", filename_only))
        local_candidates.append(os.path.join(r"D:\Volley\B1FB", "giornata_01", filename_only))

        file_bytes = None
        found_path = None
        for cand in local_candidates:
            if os.path.exists(cand):
                with open(cand, "rb") as f:
                    file_bytes = f.read()
                found_path = cand
                break

        if not file_bytes:
            print(f"⚠️ Match ID #{m_id} ({m_code}): File non trovato in locale tra i candidati.")
            errors_count += 1
            continue

        campionato, categoria, girone, giornata = infer_hierarchy_from_code(m_code, fallback_giornata=idx)
        clean_filename = os.path.basename(found_path)

        new_rel_key, new_hash = storage.save_dvw(
            file_bytes=file_bytes,
            filename=clean_filename,
            campionato=campionato,
            categoria=categoria,
            girone=girone,
            giornata=giornata
        )

        # Aggiorna il DB
        c.execute("""
            UPDATE matches 
            SET storage_path = ?, file_hash = ?, giornata = ? 
            WHERE id = ?
        """, (new_rel_key, new_hash, int(giornata), m_id))
        conn.commit()

        size_kb = len(file_bytes) / 1024
        print(f"✅ [R2 Upload OK] ID #{m_id}: {clean_filename}")
        print(f"   ↳ Chiave R2: {new_rel_key} ({size_kb:.1f} KB)")
        print(f"   ↳ Hash SHA256: {new_hash[:16]}... | Giornata: {giornata}")
        synced_count += 1

    conn.close()

    print("\n" + "=" * 70)
    print(f"✨ Sincronizzazione R2 Completata: {synced_count} caricate con successo, {errors_count} errori.")
    print("=" * 70)

if __name__ == "__main__":
    main()
