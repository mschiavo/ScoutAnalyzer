import json
import os
from typing import Dict, Any, List, Optional
from src.db import get_db_connection

DEFAULT_CONFIG_PATH = "config/config.json"

class IngestionManager:
    """Gestisce il salvataggio dei dati parsati da un file .dvw nel database relazionale.
    Implementa la Lazy Creation per squadre e atlete storiche non censite, e registra
    immediatamente i log per le violazioni sintattiche riscontrate dal parser.
    """
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.db_path = self.config.get("db_path", "scoutanalyzer.db")

    def ingest_dvw(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Ingestione completa dei dati nel database con persistenza delle validazioni sintattiche."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        try:
            # 1. Lazy Creation Campionato, Squadre e Atlete
            championship_id = self._ensure_championship(cursor, parsed_data.get("match_info", {}))
            home_team_id, away_team_id = self._ensure_teams(cursor, parsed_data.get("teams", {}))
            
            home_players_map = self._ensure_players(cursor, home_team_id, parsed_data.get("players_home", []))
            away_players_map = self._ensure_players(cursor, away_team_id, parsed_data.get("players_visiting", []))

            # 2. Inserimento/Aggiornamento Partita (matches)
            match_info = parsed_data.get("match_info", {})
            match_code = match_info.get("match_code", "UNKNOWN_MATCH")
            date_played = match_info.get("date")

            cursor.execute("""
                INSERT INTO matches (match_code, scheduled_date, home_team_id, away_team_id, status)
                VALUES (?, ?, ?, ?, 'PENDING')
                ON CONFLICT(match_code) DO UPDATE SET
                    scheduled_date = excluded.scheduled_date,
                    home_team_id = excluded.home_team_id,
                    away_team_id = excluded.away_team_id
            """, (match_code, date_played, home_team_id, away_team_id))

            cursor.execute("SELECT id FROM matches WHERE match_code = ?", (match_code,))
            match_id = cursor.fetchone()[0]

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

            for fallback_set in range(1, 6):
                if fallback_set not in set_id_map:
                    cursor.execute("""
                        INSERT OR IGNORE INTO match_sets (match_id, set_number) VALUES (?, ?)
                    """, (match_id, fallback_set))
                    cursor.execute("SELECT id FROM match_sets WHERE match_id = ? AND set_number = ?", (match_id, fallback_set))
                    set_id_map[fallback_set] = cursor.fetchone()[0]

            # 4. Inserimento Eventi Play-by-Play (events)
            events_data = parsed_data.get("events", [])
            cursor.execute("DELETE FROM events WHERE match_id = ?", (match_id,))

            events_to_insert = []
            syntax_errors = []

            for ev in events_data:
                set_num = ev.get("set_number", 1)
                set_id = set_id_map.get(set_num, set_id_map.get(1))
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
                    INSERT INTO validation_logs (match_id, file_name, line_number, raw_code, parsed_status, error_summary)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, syntax_errors)

            conn.commit()
            return {
                "status": "SUCCESS",
                "match_id": match_id,
                "match_code": match_code,
                "events_count": len(events_to_insert),
                "syntax_issues_count": len(syntax_errors),
                "sets_count": len(parsed_data.get("sets", []))
            }
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _ensure_championship(self, cursor: sqlite3.Cursor, match_info: Dict[str, Any]) -> int:
        season = match_info.get("season") or "2026/2027"
        name = match_info.get("league") or "Campionato B1F"
        cursor.execute("INSERT OR IGNORE INTO championships (code, name) VALUES (?, ?)", (season, f"{name} {season}"))
        cursor.execute("SELECT id FROM championships WHERE code = ?", (season,))
        row = cursor.fetchone()
        return row[0] if row else 1

    def _ensure_teams(self, cursor: sqlite3.Cursor, teams: Dict[str, Any]) -> (int, int):
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

    def _ensure_players(self, cursor: sqlite3.Cursor, team_id: int, players: List[Dict[str, Any]]) -> Dict[str, int]:
        players_map = {}
        for p in players:
            shirt = str(p.get("number", "")).strip()
            name = p.get("name", "").strip()
            code = p.get("code", f"P_{team_id}_{shirt}").strip()
            if not shirt:
                continue

            parts = name.split()
            last_name = parts[0] if parts else f"Player_{shirt}"
            first_name = " ".join(parts[1:]) if len(parts) > 1 else ""

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

            cursor.execute("""
                INSERT INTO players (code, first_name, last_name, role_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    role_id = COALESCE(excluded.role_id, players.role_id)
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
