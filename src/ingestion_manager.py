import json
import os
import sqlite3
import hashlib
from typing import Dict, Any, List, Optional
from src.db import get_db_connection, scout_filename_metadata

DEFAULT_CONFIG_PATH = "config/config.json"


def scout_section_hash(content: bytes):
    """Hash delle righe della sezione scout, ignorando solo la codifica dei newline."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    lines, in_scout = [], False
    for line in text.splitlines():
        marker = line.strip().upper()
        if marker.startswith("[") and marker.endswith("]"):
            section = marker[1:-1]
            if in_scout:
                break
            in_scout = section in {"3SCOUT", "SCOUT3"}
            continue
        if in_scout:
            lines.append(line)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest() if in_scout else None


class DuplicateMatch(Exception):
    def __init__(self, matches, incoming, identical=False):
        self.matches = matches
        self.incoming = incoming
        self.identical = identical


class UnknownRoster(Exception):
    def __init__(self, teams):
        self.teams = teams


class IngestionManager:
    """Gestisce il salvataggio dei dati parsati da un file .dvw nel database relazionale.
    Implementa la Lazy Creation per squadre e atlete storiche non censite, e registra
    immediatamente i log per le violazioni sintattiche riscontrate dal parser.
    """
    def __init__(self, config_path: str = "config/config.json"):
        self.config_path = config_path
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        cfg_db = self.config.get("db_path", "scoutanalyzer.db")
        from src.db import get_sqlite_path
        self.db_path = get_sqlite_path(cfg_db)

    def ingest_dvw(self, parsed_data: Dict[str, Any], *, audit_scope=None,
                   giornata=None, replace_match_id=None, roster_policy=None,
                   create_new=False, file_hash=None, scout_hash=None, save_file=None, replace_file_hash=None) -> Dict[str, Any]:
        """Ingestione completa dei dati nel database con persistenza delle validazioni sintattiche."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            # 1. Lazy Creation Campionato, Squadre e Atlete
            self._ensure_championship(cursor, parsed_data.get("match_info", {}))
            unknown, protected, roster_issues, roster_variations = [], set(), [], []
            if roster_policy is not None:
                from src.roster_manager import assess_dvw_rosters
                parsed_data = {**parsed_data, "teams": dict(parsed_data.get("teams", {}))}
                unknown, protected, roster_issues, roster_variations = assess_dvw_rosters(cursor, parsed_data)
            home_team_id, away_team_id = self._ensure_teams(cursor, parsed_data.get("teams", {}))

            match_info = parsed_data.get("match_info", {})
            match_code = match_info.get("match_code", "UNKNOWN_MATCH")
            source_match_code = match_code if audit_scope is not None else None
            replacement = None
            duplicate_same_code = False
            if audit_scope is not None:
                if not isinstance(conn, sqlite3.Connection):
                    cursor.execute("SELECT id FROM teams WHERE id IN (?, ?) ORDER BY id FOR UPDATE", (home_team_id, away_team_id))
                duplicates = self._find_duplicate_matches(cursor, home_team_id, away_team_id,
                                                          match_code, giornata, audit_scope, scout_hash)
                teams = parsed_data.get("teams", {})
                incoming = {"match_code": match_code, "home_name": teams.get("home_name") or teams.get("home_code"),
                            "away_name": teams.get("away_name") or teams.get("away_code"),
                            "scout_author": scout_filename_metadata(match_code)[1], "giornata": giornata}
                identical = [match for match in duplicates if match["identical"]]
                if identical:
                    raise DuplicateMatch(identical, incoming, identical=True)
                duplicate_same_code = any(match["internal_code"] == match_code for match in duplicates)
                if replace_match_id is not None:
                    replacement = next((match for match in duplicates if match["id"] == replace_match_id and match["replaceable"]), None)
                    if replacement is None or (replace_file_hash is not None and replacement["file_hash"] != replace_file_hash):
                        raise DuplicateMatch(duplicates, incoming)
                elif duplicates and not create_new:
                    # La stessa gara può avere due scout indipendenti (uno per rilevatore).
                    # Chiediamo una scelta solo quando la sezione play-by-play è identica.
                    duplicates = [match for match in duplicates if match["identical"]]
                    if duplicates:
                        raise DuplicateMatch(duplicates, incoming, identical=True)

                if create_new or duplicate_same_code or (replacement and replacement["internal_code"] != match_code):
                    match_code = f"{match_code} [{file_hash}]"

            if unknown and roster_policy == "ask":
                raise UnknownRoster(unknown)
            if roster_policy == "skip":
                protected.update(team["side"] for team in unknown)
            home_players_map = self._ensure_players(cursor, home_team_id, parsed_data.get("players_home", []),
                                                    register="home" not in protected, update_existing=roster_policy is None)
            away_players_map = self._ensure_players(cursor, away_team_id, parsed_data.get("players_visiting", []),
                                                    register="away" not in protected, update_existing=roster_policy is None)

            # 2. Inserimento/Aggiornamento Partita (matches)
            date_played = match_info.get("date")

            if replacement:
                cursor.execute("UPDATE matches SET match_code = ? WHERE id = ?", (match_code, replacement["id"]))
            cursor.execute("""
                INSERT INTO matches (match_code, scheduled_date, home_team_id, away_team_id, status, giornata, audit_scope, source_match_code)
                VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?)
                ON CONFLICT(match_code) DO UPDATE SET
                    scheduled_date = excluded.scheduled_date,
                    home_team_id = excluded.home_team_id,
                    away_team_id = excluded.away_team_id,
                    giornata = COALESCE(excluded.giornata, matches.giornata),
                    audit_scope = COALESCE(excluded.audit_scope, matches.audit_scope),
                    source_match_code = COALESCE(excluded.source_match_code, matches.source_match_code)
            """, (match_code, date_played, home_team_id, away_team_id, giornata, audit_scope, source_match_code))

            cursor.execute("SELECT id FROM matches WHERE match_code = ?", (match_code,))
            match_id = cursor.fetchone()[0]

            # Rimuove i dati derivati dalla versione precedente del file.
            for table in ("events", "actions", "rotations", "validation_logs"):
                cursor.execute(f"DELETE FROM {table} WHERE match_id = ?", (match_id,))
            cursor.execute("DELETE FROM match_sets WHERE match_id = ?", (match_id,))
            cursor.execute("DELETE FROM match_roster_players WHERE match_id = ?", (match_id,))
            self._store_match_roster(cursor, match_id, parsed_data, roster_issues)

            # 3. Inserimento Set (match_sets)
            set_id_map = {}
            for s in parsed_data.get("sets", []):
                set_num = s["set_number"]
                cursor.execute("""
                    INSERT INTO match_sets (match_id, set_number, home_score, away_score, duration_minutes, winning_team)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(match_id, set_number) DO UPDATE SET
                        home_score = excluded.home_score,
                        away_score = excluded.away_score,
                        duration_minutes = excluded.duration_minutes,
                        winning_team = excluded.winning_team
                """, (match_id, set_num, s["home_score"], s["away_score"], s.get("duration_minutes"), s.get("winning_team")))

                cursor.execute("SELECT id FROM match_sets WHERE match_id = ? AND set_number = ?", (match_id, set_num))
                set_id_map[set_num] = cursor.fetchone()[0]

            event_sets = {event.get("set_number", 1) for event in parsed_data.get("events", [])}
            for fallback_set in sorted(event_sets):
                if fallback_set not in set_id_map:
                    cursor.execute("""
                        INSERT INTO match_sets (match_id, set_number, home_score, away_score)
                        VALUES (?, ?, NULL, NULL)
                    """, (match_id, fallback_set))
                    cursor.execute("SELECT id FROM match_sets WHERE match_id = ? AND set_number = ?", (match_id, fallback_set))
                    set_id_map[fallback_set] = cursor.fetchone()[0]

            # 4. Inserimento Eventi Play-by-Play (events)
            events_data = parsed_data.get("events", [])

            events_to_insert = []
            syntax_errors = []

            for ev in events_data:
                set_num = ev.get("set_number", 1)
                set_id = set_id_map[set_num]
                team_code = ev.get("team_code", "*")
                shirt_number = ev.get("shirt_number")

                player_id = None
                if shirt_number is not None:
                    if team_code == '*':
                        player_id = home_players_map.get(str(shirt_number))
                    else:
                        player_id = away_players_map.get(str(shirt_number))

                is_valid = ev.get("is_valid", 1)
                error_note = ev.get("error_note")

                if is_valid == 0:
                    syntax_errors.append((match_id, match_code, ev["event_index"], ev.get("extended_code"), "ERROR", error_note))

                home_setter_pos = ev.get("home_setter_pos")
                away_setter_pos = ev.get("away_setter_pos")
                video_frame = ev.get("video_frame")

                raw_h_lineup = ev.get("home_lineup") or []
                h_pos = (raw_h_lineup + [None] * 6)[:6]
                raw_a_lineup = ev.get("away_lineup") or []
                a_pos = (raw_a_lineup + [None] * 6)[:6]

                events_to_insert.append((
                    match_id,
                    set_id,
                    ev["event_index"],
                    team_code,
                    shirt_number,
                    player_id,
                    ev.get("skill"),
                    ev.get("skill_type"),
                    ev.get("evaluation"),
                    ev.get("combo_code"),
                    ev.get("target_attacker"),
                    ev.get("start_zone"),
                    ev.get("end_zone"),
                    ev.get("end_subzone"),
                    ev.get("extended_code"),
                    video_frame,
                    home_setter_pos,
                    away_setter_pos,
                    h_pos[0], h_pos[1], h_pos[2], h_pos[3], h_pos[4], h_pos[5],
                    a_pos[0], a_pos[1], a_pos[2], a_pos[3], a_pos[4], a_pos[5],
                    bool(is_valid),
                    error_note
                ))

            if events_to_insert:
                cursor.executemany("""
                    INSERT INTO events (
                        match_id, set_id, event_index, team_code, shirt_number, player_id,
                        skill, skill_type, evaluation, combo_code, target_attacker,
                        start_zone, end_zone, end_subzone, extended_code, video_frame,
                        home_setter_pos, away_setter_pos,
                        home_pos1, home_pos2, home_pos3, home_pos4, home_pos5, home_pos6,
                        away_pos1, away_pos2, away_pos3, away_pos4, away_pos5, away_pos6,
                        is_valid, error_note
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?
                    )
                """, events_to_insert)

            # Persistiamo gli eventuali log di errore sintattico
            if syntax_errors:
                cursor.executemany("""
                    INSERT INTO validation_logs (match_id, file_name, line_number, raw_code, parsed_status, error_summary, validation_source)
                    VALUES (?, ?, ?, ?, ?, ?, 'SYNTAX')
                """, syntax_errors)
            if roster_issues:
                cursor.executemany("""
                    INSERT INTO validation_logs (match_id, file_name, raw_code, parsed_status, error_summary, validation_source)
                    VALUES (?, ?, 'ROSTER', 'WARNING', ?, 'ROSTER')
                """, [(match_id, match_code, issue) for issue in roster_issues])
            if roster_variations:
                cursor.executemany("""
                    INSERT INTO validation_logs (match_id, file_name, raw_code, parsed_status, error_summary, validation_source)
                    VALUES (?, ?, 'ROSTER', 'WARNING', ?, 'ROSTER_VARIATION')
                """, [(match_id, match_code, issue) for issue in roster_variations])

            from src.db import refresh_match_summary_metrics
            refresh_match_summary_metrics(cursor, match_id)

            storage_path = None
            if save_file is not None:
                storage_path = save_file(cursor, match_id, bool(replacement or create_new))
                cursor.execute("UPDATE matches SET storage_path = ?, file_hash = ?, scout_hash = ? WHERE id = ?",
                               (storage_path, file_hash, scout_hash, match_id))
            conn.commit()
            return {
                "status": "SUCCESS",
                "match_id": match_id,
                "match_code": source_match_code or match_code,
                "storage_path": storage_path,
                "events_count": len(events_to_insert),
                "syntax_issues_count": len(syntax_errors),
                "roster_issues": roster_issues,
                "roster_variations": roster_variations,
                "sets_count": len(parsed_data.get("sets", []))
            }
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _find_duplicate_matches(self, cursor, home_id, away_id, match_code, round_number, scope, scout_hash):
        cursor.execute("""
            SELECT m.id, m.match_code, m.source_match_code, m.giornata, m.audit_scope, m.storage_path,
                   m.home_team_id, m.away_team_id, m.scout_author, m.file_hash, m.scout_hash,
                   ht.name AS home_name, at.name AS away_name
            FROM matches m JOIN teams ht ON ht.id = m.home_team_id JOIN teams at ON at.id = m.away_team_id
            WHERE m.match_code = ? OR m.source_match_code = ? OR m.scout_hash = ?
               OR (m.home_team_id = ? AND m.away_team_id = ?)
               OR (m.home_team_id = ? AND m.away_team_id = ?)
            ORDER BY m.id
        """, (match_code, match_code, scout_hash, home_id, away_id, away_id, home_id))
        matches = []
        for row in cursor.fetchall():
            match = dict(row)
            path = (match["storage_path"] or "").replace("\\", "/").split("/")
            stored_scope = match["audit_scope"] or ("/".join(path[:-2]) if len(path) >= 5 else "")
            same_scope = not stored_scope or stored_scope.upper().replace("/", "-") == scope.upper().replace("/", "-")
            stored_code = match["source_match_code"] or match["match_code"]
            filename_round, author = scout_filename_metadata(stored_code)
            stored_round = filename_round or match["giornata"]
            if stored_round is None and len(path) >= 5 and path[-2].isdigit():
                stored_round = int(path[-2])
            same_order = (match["home_team_id"], match["away_team_id"]) == (home_id, away_id)
            reverse_order = (match["home_team_id"], match["away_team_id"]) == (away_id, home_id)
            same_fixture = (same_order or reverse_order) and same_scope and round_number == stored_round
            stored_author = author or match["scout_author"]
            stored_scout_hash = match["scout_hash"]
            if same_fixture and scout_hash and not stored_scout_hash and match["storage_path"]:
                try:
                    from src.storage_manager import StorageManager
                    stored_scout_hash = scout_section_hash(StorageManager().get_dvw_bytes(match["storage_path"]))
                    if stored_scout_hash:
                        cursor.execute("UPDATE matches SET scout_hash = ? WHERE id = ?", (stored_scout_hash, match["id"]))
                except Exception:
                    pass
            identical = bool(same_fixture and scout_hash and scout_hash == stored_scout_hash)
            if same_fixture:
                matches.append({"id": match["id"], "match_code": stored_code, "internal_code": match["match_code"],
                                "home_name": match["home_name"], "away_name": match["away_name"],
                                "scout_author": stored_author, "giornata": stored_round,
                                "file_hash": match["file_hash"],
                                "identical": identical, "replaceable": same_fixture or (same_order and same_scope and stored_round is None)})
        return matches

    def _ensure_championship(self, cursor: Any, match_info: Dict[str, Any]) -> int:
        season = match_info.get("season") or "2026/2027"
        name = match_info.get("league") or "Campionato B1F"
        cursor.execute("INSERT OR IGNORE INTO championships (code, name) VALUES (?, ?)", (season, f"{name} {season}"))
        cursor.execute("SELECT id FROM championships WHERE code = ?", (season,))
        row = cursor.fetchone()
        return row[0] if row else 1

    @staticmethod
    def _store_match_roster(cursor, match_id, parsed, issues):
        roster = []
        for side, key in (("*", "players_home"), ("a", "players_visiting")):
            shirts = set()
            for player in parsed.get(key, []):
                number = str(player.get("number", ""))
                if not number.isdigit():
                    continue
                shirt = int(number)
                if shirt in shirts:
                    issues.append(f"Referto {'casa' if side == '*' else 'ospite'}: numero di maglia {shirt} assegnato più volte.")
                    continue
                shirts.add(shirt)
                names = (player.get("name") or "").split(maxsplit=1)
                last = player.get("last_name", names[0] if names else "")
                first = player.get("first_name", names[1] if len(names) > 1 else "")
                role = player.get("role_code")
                is_libero = bool(player.get("is_libero")) or str(role).upper() in ("1", "L")
                roster.append((match_id, side, shirt, player.get("code"), first, last, role, int(is_libero)))
        if roster:
            cursor.executemany("""
                INSERT INTO match_roster_players
                    (match_id, team_side, shirt_number, player_code, first_name, last_name, role_code, is_libero)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, roster)

    def _ensure_teams(self, cursor: Any, teams: Dict[str, Any]) -> (int, int):
        home_code = teams.get("home_code", "HOME")
        home_name = teams.get("home_name", "Home Team")
        away_code = teams.get("away_code", "AWAY")
        away_name = teams.get("away_name", "Away Team")

        cursor.execute("INSERT OR IGNORE INTO teams (code, name) VALUES (?, ?)", (home_code, home_name))
        cursor.execute("INSERT OR IGNORE INTO teams (code, name) VALUES (?, ?)", (away_code, away_name))

        cursor.execute("SELECT id FROM teams WHERE code = ?", (home_code,))
        home_id = cursor.fetchone()[0]

        cursor.execute("SELECT id FROM teams WHERE code = ?", (away_code,))
        away_id = cursor.fetchone()[0]

        return home_id, away_id

    def _ensure_players(self, cursor: Any, team_id: int, players: List[Dict[str, Any]], *,
                        register=True, update_existing=True) -> Dict[str, int]:
        players_map = {}
        for p in players:
            shirt = str(p.get("number", "")).strip()
            name = p.get("name", "").strip()
            code = (p.get("code") or f"P_{team_id}_{shirt}").strip()
            if not update_existing and not p.get("code_from_file", True):
                code = f"P_{team_id}_{shirt}"
            if not shirt:
                continue

            if not register:
                cursor.execute("""
                    SELECT p.id FROM players p JOIN team_players tp ON tp.player_id = p.id
                    WHERE tp.team_id = ? AND tp.valid_to IS NULL AND p.code = ?
                """, (team_id, code))
                player = cursor.fetchone()
                if player:
                    players_map[shirt] = player[0]
                continue

            parts = name.split()
            last_name = p.get("last_name") or (parts[0] if parts else f"Player_{shirt}")
            first_name = p.get("first_name", " ".join(parts[1:]))

            is_libero = p.get("is_libero", False)
            role_code = str(p.get("role_code", "")).strip()
            role_id = None
            if is_libero or role_code in ("1", "L"):
                cursor.execute("SELECT id FROM roles WHERE dv_role_code = '1' OR code = 'L'")
                r_row = cursor.fetchone()
                if r_row:
                    role_id = r_row[0]
            elif role_code:
                cursor.execute("SELECT id FROM roles WHERE dv_role_code = ? OR code = ?", (role_code, role_code))
                r_row = cursor.fetchone()
                if r_row:
                    role_id = r_row[0]

            conflict = "DO NOTHING"
            if update_existing:
                conflict = """DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    role_id = COALESCE(excluded.role_id, players.role_id)
                """
            cursor.execute(f"""
                INSERT INTO players (code, first_name, last_name, role_id)
                VALUES (?, ?, ?, ?) ON CONFLICT(code) {conflict}
            """, (code, first_name, last_name, role_id))

            cursor.execute("SELECT id FROM players WHERE code = ?", (code,))
            player_id = cursor.fetchone()[0]
            players_map[shirt] = player_id

            cursor.execute("SELECT id FROM team_players WHERE team_id = ? AND player_id = ?", (team_id, player_id))
            tp_row = cursor.fetchone()
            if tp_row:
                cursor.execute("""
                    UPDATE team_players SET shirt_number = ?, valid_to = NULL WHERE id = ?
                """, (int(shirt) if shirt.isdigit() else 0, tp_row[0]))
            else:
                cursor.execute("""
                    INSERT INTO team_players (team_id, player_id, shirt_number)
                    VALUES (?, ?, ?)
                """, (team_id, player_id, int(shirt) if shirt.isdigit() else 0))

        return players_map
