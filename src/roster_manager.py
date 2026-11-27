import os
import shutil
import hashlib
import json
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional
from src.db import get_db_connection, get_sqlite_path

DEFAULT_CONFIG_PATH = "config/config.json"


def _normalized_name(value):
    return " ".join((value or "").casefold().split())


def assess_dvw_rosters(cursor, parsed):
    """Resolve known teams and compare announced players with their saved official files."""
    cursor.execute("SELECT id, code, name, roster_code, roster_inactive FROM teams")
    teams = [dict(row) for row in cursor.fetchall()]
    teams_by_code = {team["code"]: team for team in teams}
    unknown = []
    reference_sides = set()
    issues = []
    variations = []
    cursor.execute("SELECT code, dv_role_code, name FROM roles")
    role_names = {value: name for code, dv_code, name in cursor.fetchall() for value in (code, dv_code) if value}
    manager = None
    match_teams = parsed.get("teams", {})
    for side, roster_key in (("home", "players_home"), ("away", "players_visiting")):
        players = parsed.get(roster_key, [])
        code = match_teams.get(f"{side}_code")
        name = match_teams.get(f"{side}_name") or code
        team = teams_by_code.get(code)
        if team is None and name:
            candidates = [candidate for candidate in teams if candidate["roster_code"]
                          and _normalized_name(candidate["name"]) == _normalized_name(name)]
            if len(candidates) == 1:
                team = candidates[0]
                if str(team["code"]).startswith("PENDING_A3F_B_") and code:
                    cursor.execute("SELECT id FROM teams WHERE code = ? AND id != ?", (code, team["id"]))
                    if cursor.fetchone() is None:
                        cursor.execute("UPDATE teams SET code = ? WHERE id = ?", (code, team["id"]))
                        team["code"] = code
                        teams_by_code[code] = team
                    else:
                        issues.append(f"{team['name']}: il codice squadra DVW {code} è già assegnato a un'altra squadra.")
                else:
                    issues.append(f"{team['name']}: codice squadra nel DVW {code}, ufficiale {team['code']}.")
                    match_teams[f"{side}_code"] = team["code"]
        if not players:
            continue
        if team and (team["roster_code"] or team["roster_inactive"]):
            reference_sides.add(side)
            if name and _normalized_name(name) != _normalized_name(team["name"]):
                other = [entry for entry in teams if entry["roster_code"]
                         and _normalized_name(entry["name"]) == _normalized_name(name)]
                if len(other) == 1:
                    issues.append(f"{name}: codice squadra nel DVW {code}, ufficiale {other[0]['code']}.")
            if team["roster_inactive"]:
                issues.append(f"{team['name']}: roster disattivato.")
                continue
            manager = manager or RosterManager()
            content = manager.storage.get_roster_bytes(team["roster_code"])
            official = manager._parse_sq_content(_decode_sq(content)) if content else []
            if not official:
                issues.append(f"{team['name']}: roster ufficiale non disponibile. Sincronizza il file .sq prima di confrontarlo.")
                continue
            differences, temporary = _compare_roster(team["name"], players, official, role_names)
            issues.extend(differences)
            variations.extend(temporary)
            continue
        if team:
            cursor.execute("SELECT 1 FROM team_players WHERE team_id = ? AND valid_to IS NULL LIMIT 1", (team["id"],))
            if cursor.fetchone():
                continue
        unknown.append({"side": side, "code": code, "name": name})
    return unknown, reference_sides, issues, variations


def _compare_roster(team_name, announced, official, role_names):
    issues = []
    variations = []
    codes = {player["code"]: player for player in official}
    for player in announced:
        shirt = int(player["number"]) if player["number"].isdigit() else player["number"]
        code = player["code"] if player.get("code_from_file", True) else None
        name = player["name"]
        expected = codes.get(code)
        same_code = expected is not None
        label = f"{team_name}, n. {shirt} {name}"
        if expected is None:
            by_name = [entry for entry in official if _normalized_name(f"{entry['last_name']} {entry['first_name']}") == _normalized_name(name)]
            by_shirt = [entry for entry in official if entry["shirt_number"] == shirt]
            candidates = by_name or by_shirt
            expected = candidates[0] if len(candidates) == 1 else None
            if expected is None:
                description = f"codice {code}" if code else "codice assente nel DVW"
                issues.append(f"{label}: atleta con {description} non identificata nel roster ufficiale.")
                continue
            issues.append(f"{label}: codice atleta nel DVW {code or 'assente'}, ufficiale {expected['code']}.")
        official_name = f"{expected['last_name']} {expected['first_name']}".strip()
        expected_names = (_normalized_name(expected["last_name"]), _normalized_name(expected["first_name"]))
        if "last_name" in player:
            name_matches = (_normalized_name(player["last_name"]), _normalized_name(player["first_name"])) == expected_names
        else:
            name_matches = _normalized_name(name) == _normalized_name(official_name)
        if not name_matches:
            issues.append(f"{label}: nome e cognome ufficiali {official_name}.")
        if expected["shirt_number"] != shirt:
            target = variations if same_code and name_matches else issues
            target.append(f"{label}: numero di maglia ufficiale {expected['shirt_number']}.")
        declared_role = "Libero" if player.get("is_libero") else role_names.get(player.get("role_code"))
        official_role = role_names.get(expected.get("raw_role_code"))
        if same_code and name_matches and declared_role and official_role and declared_role != official_role:
            variations.append(f"{label}: ruolo a referto {declared_role}, ruolo ufficiale {official_role}.")
    return issues, variations


def _decode_sq(content):
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")

class RosterManager:
    """Gestisce il download, il backup intelligente, l'aggiornamento a DB (con soft-delete)
    dei file roster ufficiali .sq, e il controllo atlete.
    """
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH, storage_manager: Optional[Any] = None):
        self.config_path = config_path
        self.config = self._load_config()

        self.db_path = get_sqlite_path()

        from src.storage_manager import StorageManager
        self.storage = storage_manager or StorageManager()

        self.current_dir = os.path.join(self.storage.base_dir, "rosters", "current")
        self.backup_dir = os.path.join(self.storage.base_dir, "rosters", "backups")
        self.base_url = self.config.get("volleynetwork_base_url", "https://volleynetworkitalia.it/data-files/volleynetworkitalia/dropbox/rosters/")

        os.makedirs(self.current_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _file_hash(self, file_path: str) -> str:
        """Calcola l'hash MD5 di un file locale."""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def download_roster_for_team(self, team_code: str) -> Dict[str, Any]:
        """Scarica il file .sq ufficiale da Volley Network.
        Esegue il backup con timestamp solo ed esclusivamente se il file scaricato differisce da quello locale.
        """
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT roster_code, name FROM teams WHERE code = ? AND roster_inactive = 0", (team_code,))
        team = cursor.fetchone()
        conn.close()

        if not team or not team[0]:
            return {"status": "ERROR", "message": f"Nessun roster_code configurato per la squadra '{team_code}'."}

        roster_code, team_name = team
        url = f"{self.base_url.rstrip('/')}/{roster_code}.sq"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            new_content = response.content
            if not self._parse_sq_content(_decode_sq(new_content)):
                return {"status": "ERROR", "message": f"File roster non valido per {team_name} ({roster_code})."}

            backup_created = False
            backup_path = None

            old_content = self.storage.get_roster_bytes(roster_code)
            if old_content:
                if hashlib.md5(new_content).hexdigest() != hashlib.md5(old_content).hexdigest():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    backup_path = self.storage.save_roster(roster_code, old_content, is_backup=True, timestamp=timestamp)
                    backup_created = True
                else:
                    return {
                        "status": "SUCCESS",
                        "team_name": team_name,
                        "roster_code": roster_code,
                        "storage_path": f"rosters/current/{roster_code}.sq",
                        "note": "File identico, nessun backup necessario."
                    }

            current_path = self.storage.save_roster(roster_code, new_content, is_backup=False)

            return {
                "status": "SUCCESS",
                "team_name": team_name,
                "roster_code": roster_code,
                "storage_path": current_path,
                "backup_created": backup_created,
                "backup_path": backup_path
            }
        except Exception as e:
            return {"status": "ERROR", "message": f"Errore download {team_name} ({roster_code}): {e}"}

    def download_all_rosters(self) -> List[Dict[str, Any]]:
        """Scarica il file roster per tutte le squadre censite con un roster_code valido."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT code FROM teams WHERE roster_code IS NOT NULL AND roster_code != '' AND roster_inactive = 0")
        teams = cursor.fetchall()
        conn.close()

        results = []
        for (code,) in teams:
            res = self.download_roster_for_team(code)
            results.append((code, res))
        return results

    def sync_roster_file_to_db(self, team_code: str, execution_date: Optional[str] = None) -> Dict[str, Any]:
        """Legge il file .sq locale e aggiorna il database.
        Applica il soft-delete (valid_to = data_odierna) alle atlete non più presenti nel roster.
        """
        today_str = execution_date or datetime.now().strftime("%Y-%m-%d")

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # Mappa ruoli { dv_role_code: role_id }
        cursor.execute("SELECT dv_role_code, id FROM roles WHERE dv_role_code IS NOT NULL")
        role_map = {str(row[0]): row[1] for row in cursor.fetchall()}

        cursor.execute("SELECT id, roster_code, name FROM teams WHERE code = ? AND roster_inactive = 0", (team_code,))
        team = cursor.fetchone()

        if not team or not team[1]:
            conn.close()
            return {"status": "ERROR", "message": f"Squadra '{team_code}' non trovata o priva di roster_code."}

        team_id, roster_code, team_name = team
        content_bytes = self.storage.get_roster_bytes(roster_code)

        if not content_bytes:
            conn.close()
            return {"status": "ERROR", "message": f"File roster non trovato nello storage per squadra '{team_code}' ({roster_code}.sq). Scaricare prima il file .sq."}

        players_data = self._parse_sq_content(_decode_sq(content_bytes))
        if not players_data:
            conn.close()
            return {"status": "ERROR", "message": f"File roster non valido per {team_name} ({roster_code})."}
        current_sq_player_codes = set()

        for p in players_data:
            current_sq_player_codes.add(p["code"])
            birth_year = None
            if p["birth_date"] and '/' in p["birth_date"]:
                try:
                    birth_year = int(p["birth_date"].split('/')[-1])
                except ValueError:
                    pass

            role_id = role_map.get(str(p.get("raw_role_code")))

            # 1. Upsert su anagrafica atlete (players)
            cursor.execute("""
                INSERT INTO players (code, first_name, last_name, birth_year, role_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    birth_year = COALESCE(excluded.birth_year, players.birth_year),
                    role_id = COALESCE(excluded.role_id, players.role_id)
            """, (p["code"], p["first_name"], p["last_name"], birth_year, role_id))

            cursor.execute("SELECT id FROM players WHERE code = ?", (p["code"],))
            player_id = cursor.fetchone()[0]

            # 2. Upsert su team_players (se nuova atleta, valid_from = data odierna, valid_to = NULL)
            cursor.execute("""
                SELECT id, valid_from FROM team_players 
                WHERE team_id = ? AND player_id = ?
            """, (team_id, player_id))
            existing_tp = cursor.fetchone()

            if existing_tp:
                # Riattiva l'atleta se precedentemente disattivata
                cursor.execute("""
                    UPDATE team_players 
                    SET shirt_number = ?, valid_to = NULL 
                    WHERE id = ?
                """, (p["shirt_number"], existing_tp[0]))
            else:
                cursor.execute("""
                    INSERT INTO team_players (team_id, player_id, shirt_number, valid_from, valid_to)
                    VALUES (?, ?, ?, ?, NULL)
                """, (team_id, player_id, p["shirt_number"], today_str))

        # 3. Soft-delete delle atlete non più presenti nel file .sq
        cursor.execute("""
            SELECT tp.id, p.code 
            FROM team_players tp
            JOIN players p ON tp.player_id = p.id
            WHERE tp.team_id = ? AND (tp.valid_to IS NULL OR tp.valid_to > ?)
        """, (team_id, today_str))
        active_db_players = cursor.fetchall()

        deactivated_count = 0
        for tp_id, p_code in active_db_players:
            if p_code not in current_sq_player_codes:
                cursor.execute("UPDATE team_players SET valid_to = ? WHERE id = ?", (today_str, tp_id))
                deactivated_count += 1

        conn.commit()
        conn.close()
        return {
            "status": "SUCCESS",
            "team_name": team_name,
            "updated_count": len(players_data),
            "deactivated_count": deactivated_count
        }

    def sync_all_rosters_to_db(self) -> List[Dict[str, Any]]:
        """Aggiorna il database per tutte le squadre con file .sq disponibili."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT code FROM teams WHERE roster_code IS NOT NULL AND roster_code != '' AND roster_inactive = 0")
        teams = cursor.fetchall()
        conn.close()

        results = []
        for (code,) in teams:
            res = self.sync_roster_file_to_db(code)
            results.append((code, res))
        return results

    def _parse_sq_content(self, content: str) -> List[Dict[str, Any]]:
        """Parser preciso del file .sq a tabulazioni.
        Struttura verificata:
        Col 0: shirt_number
        Col 1: player_code
        Col 2: last_name
        Col 3: birth_date
        Col 6: code L (Libero) o C (Capitano)
        Col 8: first_name
        Col 9: raw_role_code (1-5)
        """
        players = []
        for line in content.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("DV-Team"):
                continue

            parts = line_str.split('\t')
            if len(parts) >= 10 and '-' in parts[1]:
                try:
                    shirt_number = int(parts[0].strip()) if parts[0].strip().isdigit() else None
                    player_code = parts[1].strip()
                    last_name = parts[2].strip()
                    birth_date = parts[3].strip()
                    first_name = parts[8].strip() if len(parts) > 8 else ""
                    raw_role_code = parts[9].strip() if len(parts) > 9 else ""

                    if player_code and last_name:
                        players.append({
                            "shirt_number": shirt_number,
                            "code": player_code,
                            "last_name": last_name,
                            "first_name": first_name,
                            "birth_date": birth_date,
                            "raw_role_code": raw_role_code
                        })
                except Exception:
                    continue
        return players
