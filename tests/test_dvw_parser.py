from src.dvw_parser import DVWParser

def test_parse_scout_line_native_lineup():
    parser = DVWParser("dummy.dvw")
    line = "*18SM-~~~58B;;;;;;;20.30.09;1;2;1;1;398;;18;15;1;5;7;4;9;8;2;1;11;13;"
    ev = parser._parse_scout_line(line, 1, 1)

    assert ev["is_valid"] == 1
    assert ev["team_code"] == "*"
    assert ev["shirt_number"] == 18
    assert ev["skill"] == "S"
    assert ev["home_setter_pos"] == 2
    assert ev["away_setter_pos"] == 1
    assert ev["home_lineup"] == [18, 15, 1, 5, 7, 4]
    assert ev["away_lineup"] == [9, 8, 2, 1, 11, 13]
    assert ev["video_frame"] == 398

def test_parse_single_digit_shirt_and_tilde_zones():
    parser = DVWParser("dummy.dvw")
    # Maglia a 1 cifra (*5SM+)
    line1 = "*5SM+;;;;;;;;1;1;1;;;;;;;;;;;;;;"
    ev1 = parser._parse_scout_line(line1, 1, 1)
    assert ev1["is_valid"] == 1
    assert ev1["shirt_number"] == 5
    assert ev1["skill"] == "S"

    # Zone con tilde sparse: *13BQ#~~~~4~~2
    line2 = "*13BQ#~~~~4~~2;;;;;;;;1;1;1;;;;;;;;;;;;;;"
    ev2 = parser._parse_scout_line(line2, 2, 1)
    assert ev2["is_valid"] == 1
    assert ev2["shirt_number"] == 13
    assert ev2["start_zone"] == 4
    assert ev2["end_zone"] == 2

def test_parse_special_codes_and_fallback_lineup():
    parser = DVWParser("dummy.dvw")
    # Codice speciale o parziale senza formazioni complete
    line = "*p01:00;;;;;;;;1;2;1;1;421;;;;;;;;;;;;;;"
    ev = parser._parse_scout_line(line, 3, 1)
    assert ev["home_setter_pos"] == 2
    assert ev["away_setter_pos"] == 1
    assert ev["video_frame"] == 421
