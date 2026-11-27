import sqlite3

B1F_B_2026_2027_TEAMS = (
    ("VIV26", "Vivienergia Busnago", "Busnago (MB)", "2769"),
    ("BRE26", "Brembo Volley Team ASD", "Treviolo (BG)", "2762"),
    ("DON26", "Pallavolo Don Felice Colleoni", "Ponte Nossa (BG)", "2770"),
    ("ACA26", "Volley Academy V&V", "Sondrio", "2765"),
    ("IDR26", "Idras Torbole Casaglia", "Torbole Casaglia (BS)", "2768"),
    ("NUO26", "Nuova BSTZ-OMSI Pol. Vobarno", "Vobarno (BS)", "2764"),
    ("ROT26", "Rothoblaas Volano", "Volano (TN)", "2773"),
    ("CRT26", "Cortina Express Imoco", "San Donà di Piave (VE)", "2760"),
    ("VIC26", "Volksbank Vicenza Volley", "Vicenza", "2761"),
    ("GPS26", "GPS Volley Group Schio", "Schio (VI)", "2771"),
    ("IPA26", "IPAG Volley Noventa", "Noventa Vicentina (VI)", "2772"),
    ("ISU26", "Isuzu Cerea", "Cerea (VR)", "2767"),
    ("BLU26", "Blu Team Pavia Udine", "Pavia di Udine (UD)", "2766"),
    ("PAD26", "Padova Volley S.S.D. A R.L.", "Padova", "2763")
)

# I codici .sq sono ufficiali; il codice DVW sarà risolto al primo scout importato.
A3F_B_2026_2027_TEAMS = (
    ("PENDING_A3F_B_2632", "Azimut Giorgione TV", "2632"),
    ("PENDING_A3F_B_2633", "Smapiù Arena Volley VR", "2633"),
    ("PENDING_A3F_B_2630", "Banca Annia Aduna Women PD", "2630"),
    ("PENDING_A3F_B_2637", "V&V Modena", "2637"),
    ("PENDING_A3F_B_2631", "Olympia di Navigazione RA", "2631"),
    ("PENDING_A3F_B_2636", "CO.GE. Vesuvio Oplonti NA", "2636"),
    ("PENDING_A3F_B_2635", "Zero5 Castellana Grotte BA", "2635"),
    ("PENDING_A3F_B_2634", "Tonno Callipo Calabria VV", "2634"),
)

DB_PATH = "scoutanalyzer.db"

def seed_real_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Inserimento dati reali (Serie B1 Femminile - Girone B)...")

    # 1. Campionato
    cursor.execute("""
    INSERT OR IGNORE INTO championships (code, name) VALUES (?, ?)
    """, ("2026-2027", "Campionato Serie B1 Femminile 2026/2027"))
    
    cursor.execute("SELECT id FROM championships WHERE code = ?", ("2026-2027",))
    championship_id = cursor.fetchone()[0]

    # 2. Gironi
    cursor.execute("""
    INSERT OR IGNORE INTO groups (championship_id, code, name) VALUES (?, ?, ?)
    """, (championship_id, "A", "Girone A Serie B1 Femminile"))
    cursor.execute("""
    INSERT OR IGNORE INTO groups (championship_id, code, name) VALUES (?, ?, ?)
    """, (championship_id, "B", "Girone B Serie B1 Femminile"))
    cursor.execute("""
    INSERT OR IGNORE INTO groups (championship_id, code, name) VALUES (?, ?, ?)
    """, (championship_id, "C", "Girone C Serie B1 Femminile"))
    cursor.execute("""
    INSERT OR IGNORE INTO groups (championship_id, code, name) VALUES (?, ?, ?)
    """, (championship_id, "D", "Girone D Serie B1 Femminile"))
    
    cursor.execute("SELECT id FROM groups WHERE championship_id = ? AND code = ?", (championship_id, "B"))
    group_id = cursor.fetchone()[0]

    # 3. Ruoli standard pallavolo
    roles = [
        ("L", "Libero", "1"),
        ("S", "Schiacciatore", "2"),
        ("O", "Opposto", "3"),
        ("C", "Centrale", "4"),
        ("P", "Palleggiatore", "5")
    ]
    cursor.executemany("""
        INSERT INTO roles (code, name, dv_role_code) VALUES (?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET dv_role_code = excluded.dv_role_code
    """, roles)

    # 4. Squadre reali del Girone B (Stagione 2026/2027)
    teams = [(code, name, stadium, group_id, roster_code)
             for code, name, stadium, roster_code in B1F_B_2026_2027_TEAMS]
    
    cursor.executemany("""
    INSERT OR IGNORE INTO teams (code, name, homestadium, group_id, roster_code) 
    VALUES (?, ?, ?, ?, ?)
    """, teams)

    print("Squadre del Girone B caricate con successo nel database!")

    print("Aggiornamento codici roster per IMOCO e VICENZA...")

    # Aggiorniamo direttamente i roster_code per le due squadre di test
    cursor.execute("UPDATE teams SET roster_code = ? WHERE code = ?", ("2760", "IMOCO"))
    cursor.execute("UPDATE teams SET roster_code = ? WHERE code = ?", ("2761", "VICENZA"))

    conn.commit()
    conn.close()
    print("Codici roster salvati a DB (IMOCO: 2760, VICENZA: 2761).")

if __name__ == "__main__":
    seed_real_data()
