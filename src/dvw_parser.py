import os
import re
from typing import Dict, List, Any, Optional

class DVWParser:
    """Parser puro per file Data Volley (.dvw).
    Estrae sezioni, metadati match, squadre, giocatori e decodifica le righe play-by-play
    eseguendo una validazione sintattica immediata su ciascun codice.
    """
    VALID_SKILLS = set("SREABDFsreabdf")
    VALID_EVALUATIONS = set("#+!-!/=")

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.sections: Dict[str, List[str]] = {}
        self.match_info: Dict[str, Any] = {}
        self.teams: Dict[str, Any] = {}
        self.sets_info: List[Dict[str, Any]] = []
        self.players_home: List[Dict[str, Any]] = []
        self.players_visiting: List[Dict[str, Any]] = []
        self.scout_events: List[Dict[str, Any]] = []

    def parse(self) -> Dict[str, Any]:
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File non trovato: {self.file_path}")

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(self.file_path, 'r', encoding='latin-1') as f:
                lines = f.readlines()

        current_section = None
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            if line_str.startswith('[') and line_str.endswith(']'):
                current_section = line_str[1:-1].upper()
                self.sections[current_section] = []
            elif current_section:
                self.sections[current_section].append(line_str)

        self._parse_match()
        self._parse_teams()
        self._parse_sets()
        self._parse_players()
        self._parse_scout()

        return {
            "match_info": self.match_info,
            "teams": self.teams,
            "sets": self.sets_info,
            "players_home": self.players_home,
            "players_visiting": self.players_visiting,
            "events": self.scout_events,
            "scout_lines_count": len(self.scout_events)
        }

    def _parse_match(self):
        match_lines = self.sections.get("3MATCH", self.sections.get("MATCH", []))
        if match_lines:
            parts = match_lines[0].split(';')
            date_str = parts[0] if len(parts) > 0 else ""
            time_str = parts[1] if len(parts) > 1 else ""
            season = parts[2] if len(parts) > 2 else ""
            league = parts[3] if len(parts) > 3 else ""

            iso_date = date_str
            if '/' in date_str:
                d_parts = date_str.split('/')
                if len(d_parts) == 3:
                    iso_date = f"{d_parts[2]}-{d_parts[1]}-{d_parts[0]}"

            base_filename = os.path.basename(self.file_path)
            match_code = os.path.splitext(base_filename)[0]

            self.match_info = {
                "match_code": match_code,
                "date": iso_date,
                "time": time_str,
                "season": season,
                "league": league
            }

    def _parse_teams(self):
        teams_data = self.sections.get("3TEAMS", self.sections.get("TEAMS", []))
        if len(teams_data) >= 2:
            self.teams = {
                "home_code": teams_data[0].split(';')[0].strip() if ';' in teams_data[0] else teams_data[0].strip(),
                "home_name": teams_data[0].split(';')[1].strip() if ';' in teams_data[0] and len(teams_data[0].split(';')) > 1 else teams_data[0].strip(),
                "away_code": teams_data[1].split(';')[0].strip() if ';' in teams_data[1] else teams_data[1].strip(),
                "away_name": teams_data[1].split(';')[1].strip() if ';' in teams_data[1] and len(teams_data[1].split(';')) > 1 else teams_data[1].strip(),
            }

    def _parse_sets(self):
        sets_data = self.sections.get("3SET", self.sections.get("SET", []))
        self.sets_info = []
        for idx, line in enumerate(sets_data):
            parts = line.split(';')
            if not parts or not parts[0]:
                continue
            set_num = idx + 1
            final_score_str = parts[4] if len(parts) > 4 else ""
            duration = int(parts[5]) if len(parts) > 5 and parts[5].strip().isdigit() else None

            home_score = 0
            away_score = 0
            winning_team = None

            if '-' in final_score_str:
                s_parts = final_score_str.split('-')
                try:
                    home_score = int(s_parts[0].strip())
                    away_score = int(s_parts[1].strip())
                    if home_score > away_score:
                        winning_team = '*'
                    elif away_score > home_score:
                        winning_team = 'a'
                except ValueError:
                    pass

            if home_score > 0 or away_score > 0:
                self.sets_info.append({
                    "set_number": set_num,
                    "home_score": home_score,
                    "away_score": away_score,
                    "duration_minutes": duration,
                    "winning_team": winning_team
                })

    def _parse_players(self):
        self.players_home = []
        self.players_visiting = []
        home_keys = [k for k in self.sections.keys() if "PLAYER" in k and ("H" in k or "HOME" in k)]
        vis_keys = [k for k in self.sections.keys() if "PLAYER" in k and ("V" in k or "VISIT" in k or "A" in k)]

        if home_keys:
            for line in self.sections.get(home_keys[0], []):
                parts = line.split(';')
                if len(parts) >= 10:
                    shirt_num = parts[1].strip() if len(parts) > 1 else ""
                    name = f"{parts[9].strip()} {parts[10].strip()}".strip() if len(parts) > 10 else parts[9].strip()
                    code = parts[8].strip() if len(parts) > 8 and parts[8].strip() else f"H_{shirt_num}"
                    if shirt_num:
                        self.players_home.append({
                            "number": shirt_num,
                            "name": name,
                            "code": code
                        })

        if vis_keys:
            for line in self.sections.get(vis_keys[0], []):
                parts = line.split(';')
                if len(parts) >= 10:
                    shirt_num = parts[1].strip() if len(parts) > 1 else ""
                    name = f"{parts[9].strip()} {parts[10].strip()}".strip() if len(parts) > 10 else parts[9].strip()
                    code = parts[8].strip() if len(parts) > 8 and parts[8].strip() else f"V_{shirt_num}"
                    if shirt_num:
                        self.players_visiting.append({
                            "number": shirt_num,
                            "name": name,
                            "code": code
                        })

    def _parse_scout_line(self, line: str, event_index: int, current_set: int) -> Dict[str, Any]:
        """Scompone e valida sintatticamente la riga scout."""
        parts = line.split(';')
        code = parts[0].strip() if parts else ""

        # Colonne posizionali registrate
        col_set = int(parts[8]) if len(parts) > 8 and parts[8].isdigit() else current_set
        home_score = int(parts[9]) if len(parts) > 9 and parts[9].isdigit() else None
        away_score = int(parts[10]) if len(parts) > 10 and parts[10].isdigit() else None

        lineup_info = {}
        if len(parts) >= 26:
            try:
                lineup_info = {
                    "home_pos": [int(p) if p.isdigit() else None for p in parts[14:20]],
                    "away_pos": [int(p) if p.isdigit() else None for p in parts[20:26]]
                }
            except Exception:
                pass

        if not code:
            return {
                "event_index": event_index,
                "set_number": col_set,
                "team_code": "*",
                "extended_code": "",
                "is_skill": False,
                "is_valid": 1,
                "error_note": None
            }

        # --- A. MARCATORI DI FINE SET (**1set, **2set...) ---
        if code.startswith("**") and "SET" in code.upper():
            return {
                "event_index": event_index,
                "set_number": col_set,
                "team_code": "*",
                "extended_code": code,
                "is_skill": False,
                "is_system": True,
                "is_valid": 1,
                "error_note": None,
                "lineup": lineup_info
            }

        # --- B. NOTE DELLO SCOUTMAN (>...) ---
        if code.startswith(">"):
            return {
                "event_index": event_index,
                "set_number": col_set,
                "team_code": "*",
                "extended_code": code,
                "is_skill": False,
                "is_system": True,
                "is_valid": 1,
                "error_note": None,
                "lineup": lineup_info
            }

        team_char = code[0]
        if team_char not in ('*', 'a', 'A'):
            # Riga sintatticamente malformata
            return {
                "event_index": event_index,
                "set_number": col_set,
                "team_code": team_char,
                "extended_code": code,
                "is_skill": False,
                "is_system": False,
                "is_valid": 0,
                "error_note": f"Prefisso squadra non valido: '{team_char}'",
                "lineup": lineup_info
            }

        # Normalizza prefisso ospite 'A' -> 'a'
        team_char = 'a' if team_char in ('a', 'A') else '*'
        sub_code = code[1:]

        # --- C. CODICI SPECIALI DI SISTEMA (*P, aP, *z, az, *c, ac, *p, ap, *T, aT, *$$) ---
        is_system = False
        if (
            '>LUP' in code.upper() or
            sub_code.startswith("$$&") or
            (len(sub_code) >= 2 and sub_code[0] in ('p', 'P') and ':' in sub_code) or
            (len(sub_code) >= 2 and sub_code[0] in ('c', 'C') and ':' in sub_code) or
            (len(sub_code) >= 2 and sub_code[0] in ('z', 'Z') and sub_code[1].isdigit()) or
            (len(sub_code) >= 2 and sub_code[0] in ('P', 'p') and sub_code[1:].isdigit()) or
            (len(sub_code) == 1 and sub_code in ('T', 't', 'C', 'c'))
        ):
            is_system = True
            return {
                "event_index": event_index,
                "set_number": col_set,
                "team_code": team_char,
                "shirt_number": None,
                "skill": None,
                "skill_type": None,
                "evaluation": None,
                "combo_code": None,
                "target_attacker": None,
                "start_zone": None,
                "end_zone": None,
                "end_subzone": None,
                "extended_code": code,
                "is_skill": False,
                "is_system": True,
                "is_valid": 1,
                "error_note": None,
                "home_score": home_score,
                "away_score": away_score,
                "lineup": lineup_info
            }

        # --- D. CODICE DI GIOCO ORDINARIO (Skill Event) ---
        # Formato posizionale: Team(1) + Maglia(2) + Skill(1) + Tipo(1) + Valutazione(1) + Estensione...
        m = re.match(r"^([*aA])(\d{2})([SRABDEFBsrabdefb])([A-Za-z0-9])([#\+!\-/\=])(.*)$", code)
        if m:
            shirt_number = int(m.group(2))
            skill = m.group(3).upper()
            skill_type = m.group(4)
            evaluation = m.group(5)
            extended = m.group(6)

            combo_code = None
            target_attacker = None
            start_zone = None
            end_zone = None
            end_subzone = None

            # Combinazione d'attacco / palleggiatore (es. K1, X6, CF, KM)
            combo_match = re.match(r"^([A-Za-z0-9]{2})", extended)
            if combo_match and not extended.startswith("~"):
                combo_code = combo_match.group(1)
                remaining = extended[2:]
            else:
                remaining = extended

            # Zone (partenza, arrivo) e sottozona (A, B, C, D)
            zone_match = re.search(r"([1-9])([1-9])([ABCDabcd])?", remaining)
            if zone_match:
                start_zone = int(zone_match.group(1))
                end_zone = int(zone_match.group(2))
                if zone_match.group(3):
                    end_subzone = zone_match.group(3).upper()
            else:
                single_zone = re.search(r"([1-9])([ABCDabcd])?", remaining)
                if single_zone:
                    start_zone = int(single_zone.group(1))
                    if single_zone.group(2):
                        end_subzone = single_zone.group(2).upper()

            return {
                "event_index": event_index,
                "set_number": col_set,
                "team_code": team_char,
                "shirt_number": shirt_number,
                "skill": skill,
                "skill_type": skill_type,
                "evaluation": evaluation,
                "combo_code": combo_code,
                "target_attacker": target_attacker,
                "start_zone": start_zone,
                "end_zone": end_zone,
                "end_subzone": end_subzone,
                "extended_code": code,
                "is_skill": True,
                "is_system": False,
                "is_valid": 1,
                "error_note": None,
                "home_score": home_score,
                "away_score": away_score,
                "lineup": lineup_info
            }
        else:
            # Codice non riconosciuto sintatticamente
            return {
                "event_index": event_index,
                "set_number": col_set,
                "team_code": team_char,
                "shirt_number": None,
                "skill": None,
                "skill_type": None,
                "evaluation": None,
                "combo_code": None,
                "target_attacker": None,
                "start_zone": None,
                "end_zone": None,
                "end_subzone": None,
                "extended_code": code,
                "is_skill": False,
                "is_system": False,
                "is_valid": 0,
                "error_note": f"Sintassi codice scout non riconosciuta: '{code}'",
                "home_score": home_score,
                "away_score": away_score,
                "lineup": lineup_info
            }

    def _parse_scout(self):
        self.scout_events = []
        scout_lines = self.sections.get("3SCOUT", self.sections.get("SCOUT", []))
        current_set = 1

        for idx, line in enumerate(scout_lines, start=1):
            if line:
                event = self._parse_scout_line(line, idx, current_set)
                self.scout_events.append(event)
                # Se incontriamo un marcatore **Xset avanziamo al set successivo
                code = event["extended_code"]
                if code.startswith("**") and "SET" in code.upper():
                    try:
                        set_char = code[2]
                        if set_char.isdigit():
                            current_set = int(set_char) + 1
                    except Exception:
                        current_set += 1
