import json
import sqlite3
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from src.models.validation_issue import ValidationIssue, Severity

class HeaderValidator:
    """Validatore di integrità dell'intestazione e del roster per file scout Data Volley (.dvw).
    Esegue controlli formali, temporali e incrociati con il database dei roster ufficiali.
    """
    def __init__(self, parsed_data: Dict[str, Any], raw_sections: Dict[str, List[str]], config_path: str = "config/config.json"):
        self.parsed_data = parsed_data
        self.raw_sections = raw_sections
        self.issues: List[ValidationIssue] = []

        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.db_path = self.config.get("db_path", "scoutanalyzer.db")
        self.validation_cfg = self.config.get("validation", {})
        self.max_days_gap = self.validation_cfg.get("max_days_between_generator_and_lastchange", 1)
        self.min_players = self.validation_cfg.get("min_players_per_team", 6)
        self.require_libero = self.validation_cfg.get("require_libero", True)

        # Data della gara per il controllo di validità tesseramento
        self.match_date = self.parsed_data.get("match_info", {}).get("date")

    def validate_all(self) -> List[ValidationIssue]:
        self.issues = []
        self.validate_datavolleyscout_header()
        self.validate_teams()
        self.validate_rosters_and_players()
        return self.issues

    def validate_datavolleyscout_header(self):
        """Validazione della sezione [3DATAVOLLEYSCOUT]."""
        lines = self.raw_sections.get("3DATAVOLLEYSCOUT", [])
        header_map = {}
        for line in lines:
            line_str = line.strip()
            if ":" in line_str:
                parts = line_str.split(":", 1)
                header_map[parts[0].strip().upper()] = parts[1].strip()

        gen_nam = header_map.get("GENERATOR-NAM", "")
        last_nam = header_map.get("LASTCHANGE-NAM", "")

        # 1. Coerenza scoutman / software
        if gen_nam and last_nam and gen_nam != last_nam:
            self.issues.append(ValidationIssue(
                code="HEAD_001",
                message=f"Discrepanza compilatore: creato da '{gen_nam}' e modificato da '{last_nam}'.",
                severity=Severity.WARNING,
                section="3DATAVOLLEYSCOUT"
            ))

        # 2. Controllo temporale date
        gen_day_str = header_map.get("GENERATOR-DAY", "")
        last_day_str = header_map.get("LASTCHANGE-DAY", "")

        if gen_day_str and last_day_str:
            gen_dt = self._parse_flexible_datetime(gen_day_str)
            last_dt = self._parse_flexible_datetime(last_day_str)

            if gen_dt and last_dt:
                if last_dt < gen_dt:
                    self.issues.append(ValidationIssue(
                        code="HEAD_002",
                        message=f"Incongruenza temporale: LASTCHANGE-DAY ({last_day_str}) è antecedente a GENERATOR-DAY ({gen_day_str}).",
                        severity=Severity.WARNING,
                        section="3DATAVOLLEYSCOUT"
                    ))
                else:
                    gap_days = (last_dt - gen_dt).total_seconds() / 86400.0
                    if gap_days > self.max_days_gap:
                        self.issues.append(ValidationIssue(
                            code="HEAD_003",
                            message=f"L'ultima modifica risale a {gap_days:.1f} giorni dopo la creazione dello scout (soglia max: {self.max_days_gap}gg).",
                            severity=Severity.WARNING,
                            section="3DATAVOLLEYSCOUT"
                        ))
        elif not gen_day_str or not last_day_str:
            self.issues.append(ValidationIssue(
                code="HEAD_004",
                message="Data di creazione (GENERATOR-DAY) o ultima modifica (LASTCHANGE-DAY) non valorizzata.",
                severity=Severity.WARNING,
                section="3DATAVOLLEYSCOUT"
            ))

    def validate_teams(self):
        """Validazione della sezione [3TEAMS]."""
        home_code = self.parsed_data.get("teams", {}).get("home_code")
        away_code = self.parsed_data.get("teams", {}).get("away_code")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for code, role in [(home_code, "Casa (*)"), (away_code, "Ospite (a)")]:
            if not code or code.strip() == "":
                self.issues.append(ValidationIssue(
                    code="TEAM_001",
                    message=f"Codice squadra {role} mancante nella sezione [3TEAMS].",
                    severity=Severity.ERRORE_CRITICO,
                    section="3TEAMS"
                ))
                continue

            cursor.execute("SELECT id FROM teams WHERE code = ?", (code.strip(),))
            if not cursor.fetchone():
                self.issues.append(ValidationIssue(
                    code="TEAM_002",
                    message=f"Codice squadra {role} '{code}' non registrato nel database ufficiale.",
                    severity=Severity.ERRORE,
                    section="3TEAMS"
                ))

        conn.close()

    def validate_rosters_and_players(self):
        """Validazione delle sezioni [3PLAYERS-H] e [3PLAYERS-V] rispetto al DB ufficiale."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Carica mappa ruoli { role_id: dv_role_code }
        cursor.execute("SELECT id, dv_role_code FROM roles WHERE dv_role_code IS NOT NULL")
        role_id_to_dv = {row[0]: str(row[1]) for row in cursor.fetchall()}

        match_date = self.match_date or datetime.now().strftime("%Y-%m-%d")

        for team_key, sec_key in [("home_code", "3PLAYERS-H"), ("away_code", "3PLAYERS-V")]:
            team_code = self.parsed_data.get("teams", {}).get(team_key)
            if not team_code:
                continue

            cursor.execute("SELECT id FROM teams WHERE code = ?", (team_code.strip(),))
            t_row = cursor.fetchone()
            if not t_row:
                continue

            team_id = t_row[0]

            # Atlete ufficialmente tesserate e valide alla data della gara
            cursor.execute("""
                SELECT p.code, tp.shirt_number, p.last_name, p.first_name, p.role_id, tp.valid_from, tp.valid_to
                FROM team_players tp
                JOIN players p ON tp.player_id = p.id
                WHERE tp.team_id = ?
            """, (team_id,))
            db_players = cursor.fetchall()

            # Mappa per codice atleta: { player_code: info_dict }
            db_by_code = {}
            for row in db_players:
                p_code, s_num, l_name, f_name, r_id, v_from, v_to = row
                # Verifica validità temporale rispetto a match_date
                is_valid_date = True
                if v_from and v_from > match_date:
                    is_valid_date = False
                if v_to and v_to < match_date:
                    is_valid_date = False

                db_by_code[p_code] = {
                    "shirt_number": s_num,
                    "last_name": l_name,
                    "first_name": f_name,
                    "dv_role_code": role_id_to_dv.get(r_id),
                    "is_valid_date": is_valid_date
                }

            # Atlete presenti nel file scout
            raw_lines = self.raw_sections.get(sec_key, [])
            scout_players = self._parse_scout_players(raw_lines)

            # Controllo numero minimo atlete
            if len(scout_players) < self.min_players:
                self.issues.append(ValidationIssue(
                    code="ROSTER_000",
                    message=f"La squadra {team_code} ha solo {len(scout_players)} atlete a referto (minimo richiesto: {self.min_players}).",
                    severity=Severity.ERRORE,
                    section=sec_key
                ))

            has_libero = False

            for sp in scout_players:
                p_code = sp["code"]
                p_shirt = sp["shirt_number"]
                p_name = sp["full_name"]
                p_role = sp["role_code"]
                is_libero = sp["is_libero"]

                if is_libero:
                    has_libero = True

                # 1. Controllo presenza a DB
                if p_code not in db_by_code:
                    self.issues.append(ValidationIssue(
                        code="ROSTER_001",
                        message=f"Atleta #{p_shirt} {p_name} (codice '{p_code}') NON presente nel roster ufficiale di {team_code}.",
                        severity=Severity.ERRORE_CRITICO,
                        section=sec_key
                    ))
                    continue

                db_info = db_by_code[p_code]

                # 2. Controllo validità temporale tesseramento alla data di gara
                if not db_info["is_valid_date"]:
                    self.issues.append(ValidationIssue(
                        code="ROSTER_002",
                        message=f"Atleta #{p_shirt} {p_name} non risultava tesserata o valida per {team_code} alla data della partita ({match_date}).",
                        severity=Severity.ERRORE_CRITICO,
                        section=sec_key
                    ))

                # 3. Controllo numero di maglia
                if db_info["shirt_number"] is not None and p_shirt is not None and db_info["shirt_number"] != p_shirt:
                    self.issues.append(ValidationIssue(
                        code="ROSTER_003",
                        message=f"Discrepanza numero maglia per {p_name}: a referto #{p_shirt}, registrata a DB con #{db_info['shirt_number']}.",
                        severity=Severity.ERRORE,
                        section=sec_key
                    ))

                # 4. Controllo ruolo (WARNING se differisce)
                if db_info["dv_role_code"] and p_role and db_info["dv_role_code"] != p_role:
                    self.issues.append(ValidationIssue(
                        code="ROSTER_004",
                        message=f"Discrepanza ruolo per #{p_shirt} {p_name}: a referto '{p_role}', registrata a DB con '{db_info['dv_role_code']}'.",
                        severity=Severity.WARNING,
                        section=sec_key
                    ))

            # Controllo presenza libero obbligatorio
            if self.require_libero and not has_libero and len(scout_players) >= self.min_players:
                self.issues.append(ValidationIssue(
                    code="ROSTER_005",
                    message=f"Nessun Libero designato nel referto di {team_code}.",
                    severity=Severity.WARNING,
                    section=sec_key
                ))

        conn.close()

    def _parse_scout_players(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Estrae le atlete dalla sezione [3PLAYERS-H] o [3PLAYERS-V] rispettando le 14 colonne posizionali."""
        players = []
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            parts = line_str.split(';')
            if len(parts) >= 10:
                try:
                    shirt_num = int(parts[1].strip()) if parts[1].strip().isdigit() else None
                    player_code = parts[8].strip()
                    last_name = parts[9].strip()
                    first_name = parts[10].strip() if len(parts) > 10 else ""
                    special_code = parts[12].strip().upper() if len(parts) > 12 else ""
                    role_code = parts[13].strip() if len(parts) > 13 else ""

                    if player_code and last_name:
                        players.append({
                            "shirt_number": shirt_num,
                            "code": player_code,
                            "last_name": last_name,
                            "first_name": first_name,
                            "full_name": f"{last_name} {first_name}".strip(),
                            "role_code": role_code,
                            "is_libero": (special_code == 'L' or role_code == '1')
                        })
                except Exception:
                    continue
        return players

    def _parse_flexible_datetime(self, dt_str: str) -> Optional[datetime]:
        """Supporta diversi formati data/ora Data Volley (DD/MM/YYYY HH.MM.SS, YYYY/MM/DD, ecc.)."""
        dt_clean = dt_str.strip().replace('-', '/').replace('.', ':')
        formats = [
            "%d/%m/%Y %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%d/%m/%y %H:%M:%S",
            "%y/%m/%d %H:%M:%S",
            "%d/%m/%Y",
            "%Y/%m/%d"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(dt_clean, fmt)
            except ValueError:
                pass
        return None
