import pytest
from src.dvw_parser import DVWParser
from src.ingestion_manager import IngestionManager
from src.state_engine import MatchStateEngine
from database.setup_db import create_database

def test_visiting_players_section_isolation():
    # Verifica che [3PLAYERS-H] e [3PLAYERS-V] siano rigorosamente isolate
    parser = DVWParser("dummy.dvw")
    parser.sections = {
        "3PLAYERS-H": [
            "0;10;1;;;;;;;Player;Home;;;2;False;;;;;;",
            "0;4;2;;;;;;;Libero;Home;;L;1;False;;;;;;"
        ],
        "3PLAYERS-V": [
            "1;20;3;;;;;;;Player;Visitor;;;2;False;;;;;;",
            "1;4;4;;;;;;;Attacker;Visitor;;;2;False;;;;;;"
        ]
    }
    parser._parse_players()
    assert len(parser.players_home) == 2
    assert len(parser.players_visiting) == 2
    assert parser.players_home[0]["number"] == "10"
    assert parser.players_home[1]["number"] == "4"
    assert parser.players_home[1]["is_libero"] is True

    # La maglia 4 di Trasferta NON è un libero
    assert parser.players_visiting[0]["number"] == "20"
    assert parser.players_visiting[1]["number"] == "4"
    assert parser.players_visiting[1]["is_libero"] is False

def test_substitution_and_setter_change_state_flow(tmp_path):
    db_file = str(tmp_path / "test_sub.db")
    create_database(db_file)

    ingester = IngestionManager()
    ingester.db_path = db_file

    mock_data = {
        "match_info": {"match_code": "TEST_SUB_MATCH", "date": "2026-10-15"},
        "teams": {"home_code": "H", "home_name": "Home", "away_code": "A", "away_name": "Away"},
        "sets": [{"set_number": 1, "home_score": 25, "away_score": 20, "duration_minutes": 25, "winning_team": "*"}],
        "players_home": [
            {"number": "1", "name": "H1"},
            {"number": "2", "name": "H2"},
            {"number": "3", "name": "H3"},
            {"number": "4", "name": "H4"},
            {"number": "5", "name": "H5"},
            {"number": "6", "name": "H6"}
        ],
        "players_visiting": [
            {"number": "10", "name": "A10"},
            {"number": "11", "name": "A11"},
            {"number": "12", "name": "A12"},
            {"number": "13", "name": "A13"},
            {"number": "14", "name": "A14"},
            {"number": "15", "name": "A15"},
            {"number": "20", "name": "A20 Sub In"}
        ],
        "events": [
            # Inizio set
            {"event_index": 1, "set_number": 1, "team_code": "*", "extended_code": "*P1>LUp", "is_valid": 1, "home_setter_pos": 1, "away_setter_pos": 1, "home_lineup": [1, 2, 3, 4, 5, 6], "away_lineup": [10, 11, 12, 13, 14, 15]},
            {"event_index": 2, "set_number": 1, "team_code": "*", "shirt_number": 1, "skill": "S", "skill_type": "M", "evaluation": "+", "extended_code": "*01SM+", "is_valid": 1, "home_setter_pos": 1, "away_setter_pos": 1, "home_lineup": [1, 2, 3, 4, 5, 6], "away_lineup": [10, 11, 12, 13, 14, 15]},
            # Sostituzione Ospiti: esce 11 entra 20
            {"event_index": 3, "set_number": 1, "team_code": "a", "extended_code": "ac11:20", "is_valid": 1, "home_setter_pos": 1, "away_setter_pos": 1, "home_lineup": [1, 2, 3, 4, 5, 6], "away_lineup": [10, 20, 12, 13, 14, 15]},
            # Cambio palleggiatore Ospiti: nuovo palleggiatore 20 (in Posizione 2)
            {"event_index": 4, "set_number": 1, "team_code": "a", "extended_code": "aP20", "is_valid": 1, "home_setter_pos": 1, "away_setter_pos": 2, "home_lineup": [1, 2, 3, 4, 5, 6], "away_lineup": [10, 20, 12, 13, 14, 15]},
            # Conferma rotazione palleggiatore in Z2
            {"event_index": 5, "set_number": 1, "team_code": "a", "extended_code": "az2", "is_valid": 1, "home_setter_pos": 1, "away_setter_pos": 2, "home_lineup": [1, 2, 3, 4, 5, 6], "away_lineup": [10, 20, 12, 13, 14, 15]},
            # Prossima battuta: Casa batte #1 in Z1
            {"event_index": 6, "set_number": 1, "team_code": "*", "shirt_number": 1, "skill": "S", "skill_type": "M", "evaluation": "#", "extended_code": "*01SM#", "is_valid": 1, "home_setter_pos": 1, "away_setter_pos": 2, "home_lineup": [1, 2, 3, 4, 5, 6], "away_lineup": [10, 20, 12, 13, 14, 15]},
        ]
    }
    res = ingester.ingest_dvw(mock_data)
    engine = MatchStateEngine(match_id=res["match_id"])
    engine.db_path = db_file
    status = engine.process_match()
    assert status["issues_found"] == 0
