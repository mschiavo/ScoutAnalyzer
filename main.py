import os
import sys
import sqlite3
import json
from src.dvw_parser import DVWParser
from src.roster_manager import RosterManager
from src.ingestion_manager import IngestionManager, UnknownRoster
from src.state_engine import MatchStateEngine
from src.models.header_validator import HeaderValidator, Severity

def show_menu():
    print("\n==================================================")
    print("         SCOUT ANALYZER - MENU PRINCIPALE         ")
    print("==================================================")
    print(" 1. Download Roster Ufficiali (.sq da VolleyNetwork)")
    print(" 2. Sincronizza Roster a DB (con Soft-Delete)")
    print(" 3. Valida Header & Roster File (.dvw vs DB)")
    print(" 4. Ingestione File Scout a Database (.dvw -> DB)")
    print(" 5. State Engine & Validazione Semantica (Rally/Rotazioni)")
    print(" 6. Audit Singolo File Completo (Header + Ingestion + State Engine)")
    print(" 0. Uscita")
    print("==================================================")

def get_dvw_file_path() -> str:
    default_path = r"D:/Volley/B1FB/giornata_01/&01_COR-VOL_Vicenza_b1fb_26_s.dvw"
    user_input = input(f"Inserisci il percorso del file .dvw [Premi Invio per Vicenza G01]: ").strip()
    if not user_input:
        return default_path
    return user_input.strip('"')


def ingest_with_roster_confirmation(parsed):
    ingester = IngestionManager()
    try:
        result = ingester.ingest_dvw(parsed, roster_policy="ask")
    except UnknownRoster as error:
        names = ", ".join(f"{team['name']} ({team['code']})" for team in error.teams)
        answer = input(f"Roster sconosciuti: {names}. Salvarli nel database? [s/N] ").strip().lower()
        result = ingester.ingest_dvw(parsed, roster_policy="add" if answer == "s" else "skip")
    for issue in result["roster_issues"]:
        print(f" [ROSTER] {issue}")
    return result


def main():
    roster_mgr = RosterManager()

    while True:
        show_menu()
        choice = input("Seleziona un'opzione (0-6): ").strip()

        if choice == "1":
            print("\n--- 1. DOWNLOAD ROSTER UFFICIALI (.SQ) ---")
            print("1. Download di TUTTE le squadre registrate")
            print("2. Download di una singola squadra (es. VIC26, CRT26)")
            sub = input("Scelta: ").strip()
            
            if sub == "1":
                results = roster_mgr.download_all_rosters()
                for code, res in results:
                    if res["status"] == "SUCCESS":
                        note = f" ({res.get('note')})" if res.get('note') else ""
                        print(f" -> [OK] {res['team_name']} ({code}): Roster scaricato in {res['path']}{note}")
                    else:
                        print(f" -> [ERRORE] {code}: {res['message']}")
            elif sub == "2":
                code = input("Inserisci il codice squadra (es. VIC26, CRT26): ").strip().upper()
                res = roster_mgr.download_roster_for_team(code)
                if res["status"] == "SUCCESS":
                    note = f" ({res.get('note')})" if res.get('note') else ""
                    print(f" -> [OK] {res['team_name']}: Roster scaricato in {res['path']}{note}")
                else:
                    print(f" -> [ERRORE]: {res['message']}")

        elif choice == "2":
            print("\n--- 2. SINCRONIZZA ROSTER A DB (CON SOFT-DELETE) ---")
            print("1. Sincronizza TUTTE le squadre")
            print("2. Sincronizza una singola squadra (es. VIC26, CRT26)")
            sub = input("Scelta: ").strip()

            if sub == "1":
                results = roster_mgr.sync_all_rosters_to_db()
                for code, res in results:
                    if res["status"] == "SUCCESS":
                        deact = f", {res.get('deactivated_count', 0)} disattivate" if res.get('deactivated_count') else ""
                        print(f" -> [OK] {res['team_name']} ({code}): DB aggiornato con {res['updated_count']} atlete{deact}.")
                    else:
                        print(f" -> [ERRORE] {code}: {res['message']}")
            elif sub == "2":
                code = input("Inserisci il codice squadra (es. VIC26, CRT26): ").strip().upper()
                res = roster_mgr.sync_roster_file_to_db(code)
                if res["status"] == "SUCCESS":
                    deact = f", {res.get('deactivated_count', 0)} disattivate" if res.get('deactivated_count') else ""
                    print(f" -> [OK] {res['team_name']}: DB aggiornato con {res['updated_count']} atlete{deact}.")
                else:
                    print(f" -> [ERRORE]: {res['message']}")

        elif choice == "3":
            print("\n--- 3. VALIDA HEADER & ROSTER FILE (.DVW VS DB) ---")
            file_path = get_dvw_file_path()
            if not os.path.exists(file_path):
                print(f"[ERRORE] File non trovato: {file_path}")
                continue

            try:
                parser = DVWParser(file_path)
                parsed = parser.parse()

                validator = HeaderValidator(parsed, parser.sections)
                issues = validator.validate_all()

                critici = [i for i in issues if i.severity == Severity.ERRORE_CRITICO]
                errori = [i for i in issues if i.severity == Severity.ERRORE]
                warnings = [i for i in issues if i.severity == Severity.WARNING]

                print(f"\nEsito Validazione Header per: {parsed['teams'].get('home_name')} vs {parsed['teams'].get('away_name')}")
                print(f" -> Totale segnalazioni: {len(issues)} (Critici: {len(critici)}, Errori: {len(errori)}, Warning: {len(warnings)})\n")

                if critici:
                    print("=== [ERRORE_CRITICO] BLOCCANTI ===")
                    for c_iss in critici:
                        print(f" [!!!] [{c_iss.section}] {c_iss.code}: {c_iss.message}")

                if errori:
                    print("\n=== [ERRORE] DA SEGNALARE ===")
                    for e_iss in errori:
                        print(f" [!] [{e_iss.section}] {e_iss.code}: {e_iss.message}")

                if warnings:
                    print("\n=== [WARNING] AVVISI INTERNI ===")
                    for w_iss in warnings:
                        print(f" [*] [{w_iss.section}] {w_iss.code}: {w_iss.message}")

                if not issues:
                    print(" -> [ECCELLENTE] Tutti i controlli di intestazione e roster sono conformi al 100%!")

            except Exception as e:
                print(f"[ERRORE ANALISI]: {e}")

        elif choice == "4":
            print("\n--- 4. INGESTIONE FILE SCOUT A DATABASE (.DVW -> DB) ---")
            file_path = get_dvw_file_path()
            if not os.path.exists(file_path):
                print(f"[ERRORE] File non trovato: {file_path}")
                continue

            try:
                print(f"Lettura e validazione sintattica: {os.path.basename(file_path)}...")
                parser = DVWParser(file_path)
                parsed = parser.parse()

                result = ingest_with_roster_confirmation(parsed)

                print("\n -> [SUCCESSO] Ingestione completata a Database!")
                print(f"    * Match Code: {result['match_code']} (ID: {result['match_id']})")
                print(f"    * Set inseriti/aggiornati: {result['sets_count']}")
                print(f"    * Eventi play-by-play salvati: {result['events_count']}")
                print(f"    * Violazioni sintattiche intercettate in-line: {result['syntax_issues_count']}")

            except Exception as e:
                print(f"[ERRORE INGESTIONE]: {e}")

        elif choice == "5":
            print("\n--- 5. STATE ENGINE & VALIDAZIONE SEMANTICA ---")
            conn = sqlite3.connect(roster_mgr.db_path)
            c = conn.cursor()
            c.execute("SELECT id, match_code, scheduled_date FROM matches ORDER BY id DESC")
            matches = c.fetchall()
            conn.close()

            if not matches:
                print("[!] Nessuna partita presente a DB. Esegui prima l'opzione 4 (Ingestione Scout)!")
                continue

            print("Partite disponibili:")
            for m in matches:
                print(f" [{m[0]}] {m[1]} ({m[2] or 'Data N.D.'})")

            m_input = input("\nInserisci l'ID della partita da processare [Premi Invio per ultima]: ").strip()
            target_id = matches[0][0] if not m_input else int(m_input)

            try:
                engine = MatchStateEngine(match_id=target_id)
                res = engine.process_match()

                print(f"\n -> [ESITO STATE ENGINE]:")
                print(f"    * Azioni (Rally) ricostruite: {res['actions_created']}")
                print(f"    * Rotazioni calcolate: {res['rotations_created']}")
                print(f"    * Violazioni semantiche riscontrate: {res['issues_found']}")

                if res['issues_found'] > 0:
                    conn = sqlite3.connect(roster_mgr.db_path)
                    c = conn.cursor()
                    c.execute("""
                        SELECT line_number, raw_code, parsed_status, error_summary 
                        FROM validation_logs 
                        WHERE match_id = ? 
                        ORDER BY line_number LIMIT 15
                    """, (target_id,))
                    print("\nPrime anomalie riscontrate:")
                    for row in c.fetchall():
                        print(f"    [{row[2]}] Riga {row[0]:4d} | Codice: {row[1]:<16} -> {row[3]}")
                    conn.close()
                else:
                    print("    [OK] Nessun errore di rotazione, servizio o chiusura rally riscontrato!")

            except Exception as e:
                print(f"[ERRORE STATE ENGINE]: {e}")

        elif choice == "6":
            print("\n--- 6. AUDIT SINGOLO FILE COMPLETO (END-TO-END) ---")
            file_path = get_dvw_file_path()
            if not os.path.exists(file_path):
                print(f"[ERRORE] File non trovato: {file_path}")
                continue

            try:
                print(f"\n[FASE 1: PARSING ED HEADER VALIDATION]")
                parser = DVWParser(file_path)
                parsed = parser.parse()

                validator = HeaderValidator(parsed, parser.sections)
                h_issues = validator.validate_all()
                print(f" -> Segnalazioni Header/Roster: {len(h_issues)}")
                for h in h_issues:
                    print(f"    [{h.severity.value}] {h.message}")

                print(f"\n[FASE 2: INGESTION A DATABASE CON VALIDAZIONE SINTATTICA]")
                i_res = ingest_with_roster_confirmation(parsed)
                print(f" -> Eventi salvati: {i_res['events_count']} | Errori sintassi in-line: {i_res['syntax_issues_count']}")

                print(f"\n[FASE 3: STATE ENGINE & VALIDAZIONE SEMANTICA]")
                engine = MatchStateEngine(match_id=i_res['match_id'])
                s_res = engine.process_match()
                print(f" -> Rally creati: {s_res['actions_created']} | Rotazioni: {s_res['rotations_created']} | Anomalie semantiche: {s_res['issues_found']}")

                conn = sqlite3.connect(roster_mgr.db_path)
                c = conn.cursor()
                c.execute("""
                    SELECT line_number, raw_code, error_summary 
                    FROM validation_logs 
                    WHERE match_id = ? 
                    ORDER BY line_number
                """, (i_res['match_id'],))
                all_logs = c.fetchall()
                conn.close()

                print(f"\n[RIASSUNTO FINALE ERRORI GARA ({len(all_logs)})]")
                if not all_logs:
                    print(" -> [CONFORME] La partita è perfetta al 100%!")
                else:
                    for l_idx, (l_no, l_raw, l_err) in enumerate(all_logs, start=1):
                        print(f"  {l_idx:2d}. [Riga {l_no:4d}] {l_raw:<16} -> {l_err}")

            except Exception as e:
                print(f"[ERRORE AUDIT COMPLETO]: {e}")

        elif choice == "0":
            print("\nChiusura Scout Analyzer. Arrivederci!")
            break
        else:
            print("Opzione non valida, riprova.")

if __name__ == "__main__":
    main()
