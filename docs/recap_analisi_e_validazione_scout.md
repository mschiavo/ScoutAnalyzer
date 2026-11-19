# ScoutAnalyzer: Specifiche Tecniche, Architettura DB e Validazione

## Capitolo 1: Gestione Roster, Sincronizzazione e Integrazione
L'infrastruttura di **ScoutAnalyzer** è progettata per garantire l'integrità e la tracciabilità dei dati anagrafici e di tesseramento delle atlete nel tempo.

### 1.1 Flusso dei Roster e dei Tesseramenti
* **Anagrafica Atlete Unificata:** Le atlete sono registrate con identificativo univoco (codice federale/scout), nome, cognome, anno di nascita e ruolo.
* **Storico Tesseramenti (`team_players`):** La relazione tra atleta e squadra gestisce il numero di maglia e la validità temporale (`valid_from`, `valid_to`), consentendo di tracciare trasferimenti e cambi numero durante la stagione.
* **Integrazione File `.sq` e Volley Network:** L'applicazione permette l'importazione automatica delle rosa tramite i file ufficiali `.sq` (sfruttando il codice `roster_code` associato a ogni squadra) o mediante sincronizzazione remota con *volleynetworkitalia.it*.

---

## Capitolo 2: Architettura e Schema del Database SQLite
Il database relazionale (`scoutanalyzer.db`) integra la gestione strutturale (campionati, gare, roster) con l'analisi puntuale delle partite (set, azioni, rotazioni, eventi).

### 2.1 Schema DDL del Database (`create_database`)

```sql
PRAGMA foreign_keys = ON;

-- 1. Tabella dei Campionati (es. 2025/2026)
CREATE TABLE IF NOT EXISTS championships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,       -- es. "2025-2026"
    name TEXT NOT NULL               -- es. "Campionato Serie B1 Femminile"
);

-- 2. Tabella dei Gironi (es. Girone C)
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    championship_id INTEGER NOT NULL,
    code TEXT NOT NULL,              -- es. "A", "B", "C", "D"
    name TEXT,                       -- es. "Girone C B1 Femminile"
    FOREIGN KEY (championship_id) REFERENCES championships(id) ON DELETE CASCADE
);

-- 3. Tabella delle Squadre
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,       -- Codice identificativo nel file scout (es. VIC26)
    name TEXT NOT NULL,              -- Nome completo della società
    homestadium TEXT,
    group_id INTEGER,                -- A quale girone appartiene la squadra
    roster_code TEXT,                -- Codice per il download del file .sq (es. "2766")
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL
);

-- 4. Tabella dei Ruoli (con codice Data Volley nativo)
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,       -- es. "P", "S", "C", "O", "L"
    name TEXT NOT NULL,              -- es. "Palleggiatore", "Schiacciatore", ecc.
    dv_role_code TEXT UNIQUE         -- Codice numerico Data Volley .sq (es. "1", "2", "3", "4", "5")
);

-- 5. Tabella delle Atlete (Roster generale)
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,       -- Codice identificativo atlete nello scout o federale
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    birth_year INTEGER,
    role_id INTEGER,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE SET NULL
);

-- 6. Tabella di Relazione Squadra-Atleta (Roster con storico trasferimenti)
CREATE TABLE IF NOT EXISTS team_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    shirt_number INTEGER,            -- Numero di maglia in quella squadra
    valid_from TEXT,                 -- Data inizio validità tesseramento (YYYY-MM-DD)
    valid_to TEXT,                   -- Data fine validità (NULL se ancora attiva)
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- 7. Tabella delle Partite / Calendario
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,       -- Riferimento al girone di appartenenza
    match_code TEXT UNIQUE,          -- Codice file match DataVolley
    giornata INTEGER NOT NULL,       -- Numero della giornata (es. 1, 2, ...)
    home_team_id INTEGER NOT NULL,
    away_team_id INTEGER NOT NULL,
    scheduled_date TEXT,
    status TEXT DEFAULT 'PENDING',   -- PENDING, VALIDATED, ERROR
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL,
    FOREIGN KEY (home_team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY (away_team_id) REFERENCES teams(id) ON DELETE CASCADE
);

-- 8. Tabella dei Set disputati
CREATE TABLE IF NOT EXISTS match_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    set_number INTEGER NOT NULL,     -- 1, 2, 3, 4, 5
    home_score INTEGER DEFAULT 0,
    away_score INTEGER DEFAULT 0,
    winning_team CHAR(1),            -- '*' (Home) o 'a' (Away)
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    UNIQUE(match_id, set_number)
);

-- 9. Tabella delle Azioni / Rally
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    set_id INTEGER NOT NULL,
    azione_index INTEGER NOT NULL,
    serving_team CHAR(1) NOT NULL,
    winning_team CHAR(1),
    score_home_before INTEGER,
    score_away_before INTEGER,
    score_home_after INTEGER,
    score_away_after INTEGER,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (set_id) REFERENCES match_sets(id) ON DELETE CASCADE
);

-- 10. Tabella Rotations (Fotografia schieramento in campo per validazione semantica)
CREATE TABLE IF NOT EXISTS rotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    set_id INTEGER NOT NULL,
    event_id INTEGER,
    home_pos1 INTEGER, home_pos2 INTEGER, home_pos3 INTEGER,
    home_pos4 INTEGER, home_pos5 INTEGER, home_pos6 INTEGER,
    away_pos1 INTEGER, away_pos2 INTEGER, away_pos3 INTEGER,
    away_pos4 INTEGER, away_pos5 INTEGER, away_pos6 INTEGER,
    home_libero INTEGER, away_libero INTEGER,
    is_subst BOOLEAN DEFAULT 0,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (set_id) REFERENCES match_sets(id) ON DELETE CASCADE
);

-- 11. Tabella Eventi (Singolo tocco / riga scout DataVolley)
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    set_id INTEGER NOT NULL,
    action_id INTEGER,
    rotation_id INTEGER,
    event_index INTEGER NOT NULL,
    team_code CHAR(1) NOT NULL,       -- '*' (Home) o 'a' (Away)
    shirt_number INTEGER,
    player_id INTEGER,
    skill CHAR(1),                    -- S, R, A, B, D, E, etc.
    skill_type CHAR(1),
    evaluation CHAR(1),               -- #, +, !, -, /, =
    start_zone INTEGER,
    end_zone INTEGER,
    end_subzone CHAR(1),
    extended_code TEXT,
    is_valid BOOLEAN DEFAULT 1,
    error_note TEXT,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE,
    FOREIGN KEY (set_id) REFERENCES match_sets(id) ON DELETE CASCADE,
    FOREIGN KEY (action_id) REFERENCES actions(id) ON DELETE SET NULL,
    FOREIGN KEY (rotation_id) REFERENCES rotations(rotation_id) ON DELETE SET NULL,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE SET NULL
);

-- 12. Tabella Log di Validazione e Parsing
CREATE TABLE IF NOT EXISTS validation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    file_name TEXT NOT NULL,
    line_number INTEGER,
    raw_code TEXT,
    parsed_status TEXT CHECK(parsed_status IN ('OK', 'WARNING', 'ERROR')) DEFAULT 'OK',
    error_summary TEXT,
    validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);
```

---

## Capitolo 3: Lettura e Parsing dei File `.dvw` (Analisi Sintattica)

### 3.1 Sezioni Principali del File DataVolley
1. `[3MATCH]`: Contiene metadati della partita, data, ora e codici squadre.
2. `[3TEAMS]`: Nomi ufficiali e codici identificativi delle squadre.
3. `[3PLAYERS-H]` & `[3PLAYERS-V]`: Formazioni e numeri di maglia per le squadre di casa e ospite.
4. `[3SET]`: Punteggi parziali dei set e durata.
5. `[3SCOUT]`: Flusso grezzo dei codici delle azioni di gioco.

### 3.2 Analisi Sintattica dei Codici Scout
Ogni riga di `[3SCOUT]` segue una struttura posizionale precisa:
* **Squadra (`pos 1`):** `*` per la squadra di casa, `a` per la squadra ospite.
* **Numero Maglia (`pos 2-3`):** Cifra numerica a due caratteri (es. `05`).
* **Fondamentale / Skill (`pos 4`):** `S` (Servizio), `R` (Ricezione), `A` (Attacco), `B` (Muro), `D` (Difesa), `E` (Alzata).
* **Tipo di Colpo (`pos 5`):** `H` (Hard/Alto), `M` (Medium), `Q` (Quick), etc.
* **Valutazione (`pos 6`):** `#` (Punto/Perfetto), `+` (Positivo), `!` (Sufficiente), `-` (Negativo), `/` (Sbagliato/Invasione), `=` (Errore diretto).
* **Zone di Gioco (`pos 7-9`):** Zona partenza (1-9), Zona arrivo (1-9), Subzona (A, B, C, D).

---

## Capitolo 4: Motore a Stati e Validazione Semantica

Il **Motore a Stati (State Engine)** elabora sequenzialmente gli eventi registrati nel database per garantire il rispetto assoluto del regolamento della pallavolo.

### 4.1 Regole Semantiche Verificate
1. **Controllo del Servizio in Zona 1:**
   * Quando il sistema rileva un evento di servizio (`S`), verifica che il giocatore con il numero di maglia corrispondente occupi la **Zona 1** nella tabella `rotations` attiva per quella squadra.
   * In caso di discrepanza, l'evento viene marcato con `is_valid = 0` e l'errore viene registrato nei `validation_logs`.
2. **Tracciamento delle Sostituzioni (`ac`):**
   * Aggiorna la disponibilità dei giocatori in campo e in panchina.
   * Segnala come anomalia eventuali tocchi di palla effettuati da giocatori non presenti sul terreno di gioco.
3. **Gestione Cambio Palla e Rotazioni (`$$&H`):**
   * Al verificarsi di un cambio palla, il motore applica una rotazione oraria ai giocatori della squadra vincente (Zona 2 $\rightarrow$ Zona 1, Zona 1 $\rightarrow$ Zona 6, ecc.).
   * Registra la nuova disposizione geometrica nella tabella `rotations`.