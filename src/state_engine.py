import sqlite3
import json
from typing import Dict, List, Any, Optional

DEFAULT_CONFIG_PATH = "config/config.json"

class MatchStateEngine:
    """Motore a Stati e Validatore Semantico per ScoutAnalyzer.
    Scorre la cronologia degli eventi di un match per:
    1. Delimitare e ricostruire i Rally (tabella `actions`).
    2. Calcolare e tracciare le formazioni in campo e le rotazioni orarie (tabella `rotations`).
    3. Rilevare violazioni semantiche con controlli rigorosi su:
       - Falli di battuta e rotazione (Zona 1) per Casa e Ospite.
       - Gestione simmetrica del doppio cambio e dei palleggiatori (*P/aP, *z/az).
       - Colpi terminali di fine azione seguiti da tocchi ordinari nello stesso rally.
       - Congruenza tra esito del punto (chi fa errore/punto) e punteggio assegnato (*p vs ap).
    """
    def __init__(self, match_id: int, config_path: str = DEFAULT_CONFIG_PATH):
        self.match_id = match_id
        self.config_path = config_path
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.db_path = self.config.get("db_path", "scoutanalyzer.db")
        self.issues: List[Dict[str, Any]] = []

    def process_match(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT match_code FROM matches WHERE id = ?", (self.match_id,))
            m_row = cursor.fetchone()
            self.match_code = m_row[0] if m_row else f"Match_{self.match_id}"

            cursor.execute("SELECT id, set_number FROM match_sets WHERE match_id = ? ORDER BY set_number", (self.match_id,))
            sets = cursor.fetchall()

            total_actions = 0
            total_rotations = 0

            cursor.execute("DELETE FROM actions WHERE match_id = ?", (self.match_id,))
            cursor.execute("DELETE FROM rotations WHERE match_id = ?", (self.match_id,))
            # Rimuoviamo solo i log semantici precedenti lasciando intatti i log sintattici generati dal parser
            cursor.execute("DELETE FROM validation_logs WHERE match_id = ? AND parsed_status != 'SINTASSI'", (self.match_id,))

            cursor.execute("SELECT home_team_id, away_team_id FROM matches WHERE id = ?", (self.match_id,))
            m_team_row = cursor.fetchone()
            self.home_team_id = m_team_row[0] if m_team_row else None
            self.away_team_id = m_team_row[1] if m_team_row else None

            # Caricamento ID atlete e maglie designate con ruolo Libero
            cursor.execute("""
                SELECT p.id, tp.team_id, tp.shirt_number
                FROM players p
                LEFT JOIN team_players tp ON tp.player_id = p.id
                JOIN roles r ON p.role_id = r.id
                WHERE r.code = 'L' OR r.dv_role_code = '1'
            """)
            self.libero_player_ids = set()
            self.libero_shirt_numbers = set()
            for row in cursor.fetchall():
                self.libero_player_ids.add(row[0])
                if row[1] is not None and row[2] is not None:
                    self.libero_shirt_numbers.add((row[1], row[2]))

            for set_id, set_number in sets:
                cursor.execute("""
                    SELECT id, event_index, team_code, shirt_number, skill, evaluation, extended_code,
                           home_setter_pos, away_setter_pos,
                           home_pos1, home_pos2, home_pos3, home_pos4, home_pos5, home_pos6,
                           away_pos1, away_pos2, away_pos3, away_pos4, away_pos5, away_pos6,
                           player_id
                    FROM events
                    WHERE match_id = ? AND set_id = ?
                    ORDER BY event_index
                """, (self.match_id, set_id))
                events = cursor.fetchall()
                if not events:
                    continue

                act_count, rot_count = self._process_set(cursor, set_id, set_number, events)
                total_actions += act_count
                total_rotations += rot_count

            # Validazione Punteggio Finale Set (25/15 punti e scarto di 2)
            cursor.execute("SELECT id, set_number, home_score, away_score FROM match_sets WHERE match_id = ?", (self.match_id,))
            for s_id, s_num, h_sc, a_sc in cursor.fetchall():
                if h_sc is not None and a_sc is not None and (h_sc > 0 or a_sc > 0):
                    min_target = 15 if s_num == 5 else 25
                    winner_sc = max(h_sc, a_sc)
                    loser_sc = min(h_sc, a_sc)
                    diff = winner_sc - loser_sc
                    if winner_sc < min_target:
                        err_msg = f"Punteggio finale anomalo Set {s_num}: punteggio vincente {winner_sc} inferiore al minimo ({min_target})"
                        self.issues.append({"set": s_num, "error": err_msg})
                        cursor.execute("""
                            INSERT INTO validation_logs (match_id, file_name, line_number, raw_code, parsed_status, error_summary)
                            VALUES (?, ?, NULL, ?, 'WARNING', ?)
                        """, (self.match_id, self.match_code, f"SET_{s_num}", err_msg))
                    elif diff < 2:
                        err_msg = f"Punteggio finale anomalo Set {s_num}: scarto di {diff} punti ({h_sc}:{a_sc}, richiesto scarto minimo di 2 punti)"
                        self.issues.append({"set": s_num, "error": err_msg})
                        cursor.execute("""
                            INSERT INTO validation_logs (match_id, file_name, line_number, raw_code, parsed_status, error_summary)
                            VALUES (?, ?, NULL, ?, 'WARNING', ?)
                        """, (self.match_id, self.match_code, f"SET_{s_num}", err_msg))

            conn.commit()
            return {
                "status": "SUCCESS",
                "match_id": self.match_id,
                "actions_created": total_actions,
                "rotations_created": total_rotations,
                "issues_found": len(self.issues)
            }
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _process_set(self, cursor, set_id: int, set_number: int, events: List[Any]) -> (int, int):
        home_pos = [None] * 6
        away_pos = [None] * 6
        home_setter_num = None
        away_setter_num = None
        home_setter_pos = 1
        away_setter_pos = 1
        home_libero = None
        away_libero = None

        current_serving_team = '*'
        score_home = 0
        score_away = 0
        rally_serving_team = '*'

        current_action_events = []
        action_index = 1
        rotations_created = 0
        actions_created = 0
        current_rotation_id = None

        home_substitutions_count = 0
        away_substitutions_count = 0

        terminal_event: Optional[Dict[str, Any]] = None

        for ev in events:
            (ev_id, ev_idx, team_code, shirt_number, skill, evaluation, code,
             h_setter_p, a_setter_p,
             hp1, hp2, hp3, hp4, hp5, hp6,
             ap1, ap2, ap3, ap4, ap5, ap6,
             player_id) = ev

            if not code:
                continue

            # Sincronizzazione formazioni native e rotazioni registrate
            if hp1 is not None and hp2 is not None and hp3 is not None and hp4 is not None and hp5 is not None and hp6 is not None:
                home_pos = [hp1, hp2, hp3, hp4, hp5, hp6]
            if ap1 is not None and ap2 is not None and ap3 is not None and ap4 is not None and ap5 is not None and ap6 is not None:
                away_pos = [ap1, ap2, ap3, ap4, ap5, ap6]
            if h_setter_p is not None:
                home_setter_pos = h_setter_p
            if a_setter_p is not None:
                away_setter_pos = a_setter_p

            # --- A. MARCATORI DI FINE SET (**1set, **2set) ---
            if code.startswith("**") and "SET" in code.upper():
                continue

            # --- B. NOTE DELLO SCOUTMAN (>...) ---
            if code.startswith(">"):
                continue

            # --- C. TIMEOUT (*T, aT) ---
            if code in ('*T', '*t', 'aT', 'at'):
                continue

            # --- D. DECODIFICA FORMAZIONI INIZIALI (*P..>LUp, *z..>LUp, aP..>LUp, az..>LUp) ---
            if '>LUP' in code.upper():
                t_char = code[0]
                if 'P' in code.upper():
                    try:
                        p_num = int(code[2:4])
                        if t_char == '*':
                            home_setter_num = p_num
                        else:
                            away_setter_num = p_num
                    except Exception:
                        pass
                elif 'Z' in code.upper():
                    try:
                        rot_val = int(code[2])
                        if t_char == '*':
                            home_setter_pos = rot_val
                        else:
                            away_setter_pos = rot_val
                    except Exception:
                        pass
                continue

            # --- E. CAMBIO PALLEGGIATORE IN CORSA (*P.., aP..) ---
            if len(code) >= 3 and code[1] in ('P', 'p') and code[2:].isdigit():
                t_char = code[0]
                new_p = int(code[2:])
                if t_char == '*':
                    home_setter_num = new_p
                else:
                    away_setter_num = new_p
                continue

            # --- F. SOSTITUZIONI (*c[OUT]:[IN] o ac[OUT]:[IN]) ---
            if len(code) >= 7 and code[1] in ('c', 'C') and ':' in code:
                t_char = code[0]
                if t_char == '*':
                    home_substitutions_count += 1
                    if home_substitutions_count > 6:
                        err_msg = f"Superato il limite massimo di 6 sostituzioni per la squadra di Casa nel set {set_number} (effettuate: {home_substitutions_count})"
                        self._log_issue(cursor, ev_idx, code, err_msg, ev_id)
                else:
                    away_substitutions_count += 1
                    if away_substitutions_count > 6:
                        err_msg = f"Superato il limite massimo di 6 sostituzioni per la squadra Ospite nel set {set_number} (effettuate: {away_substitutions_count})"
                        self._log_issue(cursor, ev_idx, code, err_msg, ev_id)

                try:
                    p_out = int(code[2:4])
                    p_in = int(code[5:7])
                    target_pos = home_pos if t_char == '*' else away_pos
                    if p_out in target_pos:
                        idx = target_pos.index(p_out)
                        target_pos[idx] = p_in

                        current_rotation_id = self._save_rotation(
                            cursor, set_id, ev_id, current_serving_team,
                            home_setter_pos, away_setter_pos, home_pos, away_pos,
                            home_libero, away_libero, is_subst=True
                        )
                        rotations_created += 1
                except Exception:
                    pass
                continue

            # --- G. ROTAZIONE ESPLICITA (*z1..6, az1..6) ---
            if (code.startswith('*z') or code.startswith('az')) and len(code) >= 3 and code[2].isdigit():
                t_char = code[0]
                new_rot = int(code[2])

                if t_char == '*':
                    if new_rot != home_setter_pos:
                        # Ricalcolo nominale: se il palleggiatore è già in new_rot, aggiorniamo solo l'indice nominale
                        if home_setter_num in home_pos and (home_pos.index(home_setter_num) + 1) == new_rot:
                            home_setter_pos = new_rot
                        else:
                            self._rotate_clockwise(home_pos)
                            home_setter_pos = new_rot
                    current_serving_team = '*'
                else:
                    if new_rot != away_setter_pos:
                        # Ricalcolo nominale per Ospite: se il palleggiatore è già in new_rot
                        if away_setter_num in away_pos and (away_pos.index(away_setter_num) + 1) == new_rot:
                            away_setter_pos = new_rot
                        else:
                            self._rotate_clockwise(away_pos)
                            away_setter_pos = new_rot
                    current_serving_team = 'a'

                current_rotation_id = self._save_rotation(
                    cursor, set_id, ev_id, current_serving_team,
                    home_setter_pos, away_setter_pos, home_pos, away_pos,
                    home_libero, away_libero, is_subst=False
                )
                rotations_created += 1
                continue

            # --- H. VERIFICA PROSECUZIONE DOPO COLPO TERMINALE DEFINITIVO ---
            if skill is not None and terminal_event is not None:
                is_terminal_followup = (
                    (terminal_event['skill'] == 'A' and terminal_event['eval'] == '#' and skill in ('B', 'D') and evaluation == '=') or
                    (terminal_event['skill'] == 'A' and terminal_event['eval'] == '/' and skill == 'B' and evaluation == '#') or
                    (terminal_event['skill'] == 'B' and terminal_event['eval'] == '=' and skill == 'D' and evaluation == '=' and terminal_event['team'] == team_code) or
                    (terminal_event['skill'] == 'S' and terminal_event['eval'] == '#' and skill == 'R' and evaluation == '=')
                )

                if not is_terminal_followup:
                    err_msg = (f"Azione prosegue illegalmente dopo colpo terminale: rilevato tocco '{code}' "
                               f"dopo {terminal_event['code']} (riga {terminal_event['line']})")
                    self._log_issue(cursor, ev_idx, code, err_msg, ev_id)

            # --- I. VALIDAZIONE DEL SERVIZIO (Skill 'S') ---
            if skill == 'S':
                current_serving_team = team_code
                rally_serving_team = team_code
                terminal_event = None

                # Controllo divieto di battuta per il Libero
                is_libero = False
                if player_id is not None and player_id in self.libero_player_ids:
                    is_libero = True
                elif shirt_number is not None:
                    t_id = self.home_team_id if team_code == '*' else self.away_team_id
                    if (t_id, shirt_number) in self.libero_shirt_numbers:
                        is_libero = True

                if is_libero:
                    err_msg = f"Fallo del Libero: atleta #{shirt_number} designata come Libero non può effettuare il servizio"
                    self._log_issue(cursor, ev_idx, code, err_msg, ev_id)

                pos1_player = home_pos[0] if team_code == '*' else away_pos[0]
                if pos1_player is None and shirt_number is not None:
                    if team_code == '*':
                        home_pos[0] = shirt_number
                    else:
                        away_pos[0] = shirt_number
                    pos1_player = shirt_number

                if pos1_player is not None and shirt_number is not None and pos1_player != shirt_number:
                    err_msg = f"Fallo di rotazione: battitore #{shirt_number} non occupa la Posizione 1 (presente #{pos1_player})"
                    self._log_issue(cursor, ev_idx, code, err_msg, ev_id)

            # Rilevamento colpi terminali definitivi
            is_definitive_terminal = False
            expected_w = None

            if skill == 'S' and evaluation in ('#', '='):
                is_definitive_terminal = True
                expected_w = team_code if evaluation == '#' else ('a' if team_code == '*' else '*')
            elif skill == 'A' and evaluation in ('#', '=', '/'):
                is_definitive_terminal = True
                expected_w = team_code if evaluation == '#' else ('a' if team_code == '*' else '*')
            elif skill == 'B' and evaluation in ('#', '='):
                is_definitive_terminal = True
                expected_w = team_code if evaluation == '#' else ('a' if team_code == '*' else '*')
            elif skill == 'D' and evaluation == '=':
                is_definitive_terminal = True
                expected_w = 'a' if team_code == '*' else '*'
            elif skill == 'R' and evaluation == '=':
                is_definitive_terminal = True
                expected_w = 'a' if team_code == '*' else '*'
            elif skill == 'E' and evaluation == '=':
                is_definitive_terminal = True
                expected_w = 'a' if team_code == '*' else '*'
            elif skill == 'F' and evaluation == '=':
                is_definitive_terminal = True
                expected_w = 'a' if team_code == '*' else '*'

            if is_definitive_terminal:
                terminal_event = {
                    'team': team_code,
                    'skill': skill,
                    'eval': evaluation,
                    'code': code,
                    'line': ev_idx,
                    'expected_winner': expected_w
                }

            if current_rotation_id:
                cursor.execute("UPDATE events SET rotation_id = ? WHERE id = ?", (current_rotation_id, ev_id))

            current_action_events.append(ev_id)

            # --- J. CHIUSURA RALLY E PUNTEGGI ---
            # Caso 1: Cambio palla ($$&H=, $$&H#...)
            if '$$&H' in code or '$$&' in code:
                winning_team = None
                if code.startswith('*$$&H='):
                    winning_team = 'a'
                elif code.startswith('*$$&H#'):
                    winning_team = '*'
                elif code.startswith('a$$&H='):
                    winning_team = '*'
                elif code.startswith('a$$&H#'):
                    winning_team = 'a'
                else:
                    winning_team = 'a' if code.startswith('*') else '*'

                if terminal_event and terminal_event.get('expected_winner') and terminal_event['expected_winner'] != winning_team:
                    w_name = "Casa (*)" if winning_team == '*' else "Ospite (a)"
                    exp_name = "Casa (*)" if terminal_event['expected_winner'] == '*' else "Ospite (a)"
                    err_msg = (f"Incongruenza punto: azione chiusa a favore di {w_name} ({code}), "
                               f"ma l'azione precedente si chiudeva a favore di {exp_name} ({terminal_event['code']} a riga {terminal_event['line']})")
                    self._log_issue(cursor, ev_idx, code, err_msg, ev_id)

                score_before_h, score_before_a = score_home, score_away
                if winning_team == '*':
                    score_home += 1
                else:
                    score_away += 1

                action_id = self._save_action(
                    cursor, set_id, action_index, rally_serving_team, winning_team,
                    score_before_h, score_before_a, score_home, score_away
                )
                actions_created += 1
                action_index += 1

                for event_in_rally_id in current_action_events:
                    cursor.execute("UPDATE events SET action_id = ? WHERE id = ?", (action_id, event_in_rally_id))
                current_action_events = []
                terminal_event = None

            # Caso 2: Punteggio esplicito (*pXY:ZW o apXY:ZW)
            elif len(code) >= 7 and code[1] in ('p', 'P') and ':' in code:
                try:
                    p_pts = code[2:].split(':')
                    new_h = int(p_pts[0])
                    new_a = int(p_pts[1])
                    if new_h > score_home or new_a > score_away:
                        awarded_team = '*' if new_h > score_home else 'a'

                        # Controllo coerenza prefisso (*p deve incrementare Casa, ap deve incrementare Ospite)
                        if code.startswith('*p') and new_h <= score_home:
                            err_msg = f"Incongruenza prefisso punteggio: prefisso '*p' indica punto a Casa, ma il punteggio di Casa non è aumentato ({score_home}:{score_away} -> {new_h}:{new_a})"
                            self._log_issue(cursor, ev_idx, code, err_msg, ev_id)
                        elif code.startswith('ap') and new_a <= score_away:
                            err_msg = f"Incongruenza prefisso punteggio: prefisso 'ap' indica punto ad Ospite, ma il punteggio Ospite non è aumentato ({score_home}:{score_away} -> {new_h}:{new_a})"
                            self._log_issue(cursor, ev_idx, code, err_msg, ev_id)

                        # Controllo congruenza colpo terminale precedente
                        if terminal_event and terminal_event.get('expected_winner') and terminal_event['expected_winner'] != awarded_team:
                            aw_name = "Casa (*)" if awarded_team == '*' else "Ospite (a)"
                            exp_name = "Casa (*)" if terminal_event['expected_winner'] == '*' else "Ospite (a)"
                            err_msg = (f"Incongruenza punteggio: punto assegnato a {aw_name} ({code}), "
                                       f"ma l'azione precedente si chiudeva a favore di {exp_name} ({terminal_event['code']} a riga {terminal_event['line']})")
                            self._log_issue(cursor, ev_idx, code, err_msg, ev_id)

                        action_id = self._save_action(
                            cursor, set_id, action_index, rally_serving_team, awarded_team,
                            score_home, score_away, new_h, new_a
                        )
                        actions_created += 1
                        action_index += 1
                        score_home, score_away = new_h, new_a

                        for event_in_rally_id in current_action_events:
                            cursor.execute("UPDATE events SET action_id = ? WHERE id = ?", (action_id, event_in_rally_id))
                        current_action_events = []
                        terminal_event = None
                except Exception:
                    pass

        return actions_created, rotations_created

    def _log_issue(self, cursor, ev_idx: int, code: str, err_msg: str, ev_id: int):
        self.issues.append({"event": ev_idx, "error": err_msg})
        cursor.execute("""
            INSERT INTO validation_logs (match_id, file_name, line_number, raw_code, parsed_status, error_summary)
            VALUES (?, ?, ?, ?, 'ERROR', ?)
        """, (self.match_id, self.match_code, ev_idx, code, err_msg))
        cursor.execute("UPDATE events SET is_valid = 0, error_note = ? WHERE id = ?", (err_msg, ev_id))

    def _rotate_clockwise(self, pos_list: List[Optional[int]]):
        if all(x is None for x in pos_list):
            return
        p1, p2, p3, p4, p5, p6 = pos_list[0], pos_list[1], pos_list[2], pos_list[3], pos_list[4], pos_list[5]
        pos_list[0] = p2
        pos_list[1] = p3
        pos_list[2] = p4
        pos_list[3] = p5
        pos_list[4] = p6
        pos_list[5] = p1

    def _save_rotation(self, cursor, set_id: int, event_id: int, serving_team: str,
                       home_setter_pos: int, away_setter_pos: int,
                       home_pos: List[Optional[int]], away_pos: List[Optional[int]],
                       home_libero: Optional[int], away_libero: Optional[int],
                       is_subst: bool) -> int:
        cursor.execute("""
            INSERT INTO rotations (
                match_id, set_id, event_id, serving_team,
                home_setter_pos, away_setter_pos,
                home_pos1, home_pos2, home_pos3, home_pos4, home_pos5, home_pos6,
                away_pos1, away_pos2, away_pos3, away_pos4, away_pos5, away_pos6,
                home_libero, away_libero, is_subst
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.match_id, set_id, event_id, serving_team,
            home_setter_pos, away_setter_pos,
            home_pos[0], home_pos[1], home_pos[2], home_pos[3], home_pos[4], home_pos[5],
            away_pos[0], away_pos[1], away_pos[2], away_pos[3], away_pos[4], away_pos[5],
            home_libero, away_libero, 1 if is_subst else 0
        ))
        return cursor.lastrowid

    def _save_action(self, cursor, set_id: int, action_index: int,
                     serving_team: str, winning_team: str,
                     score_home_before: int, score_away_before: int,
                     score_home_after: int, score_away_after: int) -> int:
        cursor.execute("""
            INSERT INTO actions (
                match_id, set_id, azione_index, serving_team, winning_team,
                score_home_before, score_away_before, score_home_after, score_away_after
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.match_id, set_id, action_index, serving_team, winning_team,
            score_home_before, score_away_before, score_home_after, score_away_after
        ))
        return cursor.lastrowid
