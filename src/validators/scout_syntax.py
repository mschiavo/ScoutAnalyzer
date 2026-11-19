import sqlite3
from typing import List, Dict, Any
from src.models.validation_issue import ValidationIssue, Severity

class ScoutSyntaxValidator:
    def __init__(self, parsed_data: Dict[str, Any], raw_sections: Dict[str, List[str]], db_path: str = "scoutanalyzer.db"):
        self.parsed_data = parsed_data
        self.raw_sections = raw_sections
        self.db_path = db_path
        self.issues: List[ValidationIssue] = []

        # Range e set di valori ammessi per i campi strutturati (da indice 0 a 11)
        self.VALID_TEAMS = {'*', 'a'}
        self.VALID_SKILLS = {'S', 'R', 'E', 'A', 'B', 'D', 'F'}
        self.VALID_EVALUATIONS = {'#', '+', '!', '/', '-', '='}
        self.VALID_ZONES = {'1', '2', '3', '4', '5', '6', '7', '8', '9', ' '}

    def validate_actions(self) -> List[ValidationIssue]:
        scout_lines = self.raw_sections.get("3SCOUT", [])
        
        home_players = {p.get("number") for p in self.parsed_data.get("players_home", []) if p.get("number")}
        away_players = {p.get("number") for p in self.parsed_data.get("players_visiting", []) if p.get("number")}

        for line_idx, line in enumerate(scout_lines, start=1):
            line_str = line.strip()
            
            # Ignoriamo righe vuote o commenti/metadati di set
            if not line_str or line_str.startswith("i") or line_str.startswith("P"):
                continue

            if len(line_str) < 4:
                continue

            # ==========================================
            # MAPPATURA STRUTTURALE CARATTERI (0 a 11)
            # ==========================================
            team_code = line_str[0] if len(line_str) > 0 else ""                 # [0] Squadra (* o a)
            player_num_str = line_str[1:3] if len(line_str) >= 3 else ""         # [1-2] Numero maglia
            skill = line_str[3].upper() if len(line_str) > 3 else ""             # [3] Fondamentale
            skill_type = line_str[4] if len(line_str) > 4 else ""                # [4] Tipo di fondamentale (Opzionale)
            eval_code = line_str[5] if len(line_str) > 5 else ""                 # [5] Valutazione
            combination = line_str[6:8] if len(line_str) >= 8 else ""            # [6-8] Combinazione / Tipologia colpo (Opzionale)
            setting_zone = line_str[8] if len(line_str) > 8 else ""              # [9] Zona di alzata (Opzionale)
            start_zone = line_str[9] if len(line_str) > 9 else ""                # [10] Zona di partenza
            end_zone = line_str[10] if len(line_str) > 10 else ""                # [11] Zona di arrivo
            sub_end_zone = line_str[11] if len(line_str) > 11 else ""            # [12] Sottozona di arrivo (Opzionale)

            # ==========================================
            # VALIDAZIONE DEI CAMPI IMPORTANTI E NECESSARI
            # ==========================================

            # 1. Controllo Squadra (Indice 0)
            if team_code not in self.VALID_TEAMS:
                continue  # Se non è una riga d'azione valida, la saltiamo

            # 2. Controllo Numero Maglia (Indici 1-2)
            if not player_num_str.isdigit():
                self.issues.append(ValidationIssue(
                    code="SCOUT_001",
                    message=f"Numero di maglia non valido '{player_num_str}' nella riga d'azione.",
                    severity=Severity.ERROR,
                    section="3SCOUT",
                    line_num=line_idx
                ))
            else:
                num = player_num_str.lstrip("0") or "0"
                if num != "0":
                    allowed_numbers = home_players if team_code == '*' else away_players
                    if num not in allowed_numbers:
                        team_label = "CASA (*)" if team_code == '*' else "TRASFERTA (a)"
                        self.issues.append(ValidationIssue(
                            code="SCOUT_002",
                            message=f"La giocatrice #{num} non risulta a referto per la squadra di {team_label}.",
                            severity=Severity.ERROR,
                            section="3SCOUT",
                            line_num=line_idx
                        ))

            # 3. Controllo Fondamentale (Indice 3)
            if skill not in self.VALID_SKILLS:
                self.issues.append(ValidationIssue(
                    code="SCOUT_003",
                    message=f"Fondamentale non riconosciuto '{skill}' (Ammessi: S, R, E, A, B, D, F).",
                    severity=Severity.ERROR,
                    section="3SCOUT",
                    line_num=line_idx
                ))

            # 4. Controllo Valutazione (Indice 5)
            if eval_code and eval_code not in self.VALID_EVALUATIONS:
                self.issues.append(ValidationIssue(
                    code="SCOUT_004",
                    message=f"Valutazione colpo non valida '{eval_code}' per il fondamentale {skill} (Ammessi: #, +, !, /, -, =).",
                    severity=Severity.WARNING,
                    section="3SCOUT",
                    line_num=line_idx
                ))

            # 5. Controllo Zone di Partenza e Arrivo (Indici 9 e 10)
            if start_zone and start_zone not in self.VALID_ZONES:
                self.issues.append(ValidationIssue(
                    code="SCOUT_005",
                    message=f"Zona di partenza non valida '{start_zone}' (Range ammesso: 1-9).",
                    severity=Severity.WARNING,
                    section="3SCOUT",
                    line_num=line_idx
                ))

            if end_zone and end_zone not in self.VALID_ZONES:
                self.issues.append(ValidationIssue(
                    code="SCOUT_006",
                    message=f"Zona di arrivo non valida '{end_zone}' (Range ammesso: 1-9).",
                    severity=Severity.WARNING,
                    section="3SCOUT",
                    line_num=line_idx
                ))

        return self.issues