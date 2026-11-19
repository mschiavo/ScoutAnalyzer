# Design Doc: DVW Native Lineups, Volleyball Domain Rules & Web UI Architecture

**Data:** 19 Novembre 2026  
**Autore:** Principal Software Architect & Domain Engineer  
**Stato:** Approvato (Approccio A per il Core Engine + Opzione 1 con supporto Opzione 2 per la Web UI)  
**Branch:** `feature/dvw-native-lineups-and-fixes`

---

## 1. Intent e Motivazione

ScoutAnalyzer è un motore di audit ingegneristico e validazione per file scout Data Volley (`.dvw`) e roster federali (`.sq`).  
L'analisi empirica condotta su 36 file reali di Serie B1 Femminile ha evidenziato due grandi opportunità:
1. **Sfruttamento delle formazioni native Data Volley:** il 99.7% delle righe scout in `[3SCOUT]` riporta già le posizioni in campo di tutte le 12 giocatrici (colonne 14–25) e le rotazioni dei palleggiatori (colonne 9 e 10). La precedente ricostruzione euristica generava falsi positivi nei cambi palla.
2. **Accessibilità e visualizzazione grafica:** l'attuale CLI testuale in `main.py` necessita di un'interfaccia grafica moderna per permettere l'ispezione visiva del campo, delle rotazioni, dell'andamento dei set e delle anomalie arbitrali o di compilazione, aprendo la strada alla futura fruizione web multi-utente.

---

## 2. Obiettivi, Non-Obiettivi e Anti-Obiettivi

### Obiettivi (Goals)
* **Core Engine:**
  * Correggere il mapping delle colonne DVW in `dvw_parser.py`: colonna 9 (rotazione Casa P1-P6), colonna 10 (rotazione Ospite P1-P6), colonne 14-19 (giocatrici Casa in campo P1..P6), colonne 20-25 (giocatrici Ospite in campo P1..P6).
  * Gestire maglie a 1 cifra (es. `*5...` e `*05...`) e parsing delle zone e sottozone con segnaposti tilde `~` sparsi (es. `*13BQ#~~~~4~~2`).
  * Unificare e attivare la validazione sintattica con `ScoutSyntaxValidator`.
  * Persistere a DB le formazioni native e renderle accessibili a `MatchStateEngine`.
  * Verificare le regole di pallavolo:
    * Battitore in Zona 1 incrociato con la formazione reale.
    * Divieto di battuta per il Libero (`skill == 'S'`).
    * Limite massimo di 6 sostituzioni per set per squadra.
    * Validazione dello scarto di 2 punti sui punteggi finali dei set (25 punti reg., 15 punti tiebreak).
* **Web Architecture & Dashboard:**
  * Backend REST moderno in **FastAPI** (`web_app.py` o modulo `src/api/`).
  * Esposizione di endpoint REST puliti e documentati (OpenAPI / Swagger integrato).
  * Abilitazione CORS per consentire a qualsiasi frontend esterno (come l'app Vite già esistente dell'utente) di consumare le API.
  * Fornitura di una SPA integrata in **Vanilla CSS/JS** elegante, responsive e con riscontro grafico immediato:
    * Selettore/upload file DVW.
    * Riepilogo match, set e parziali.
    * **Campo da pallavolo SVG/Canvas interattivo** con visualizzazione grafica delle 6 posizioni e del Libero.
    * Tabella play-by-play navigabile con filtri di severità (`ERRORE_CRITICO`, `ERRORE`, `WARNING`).

### Non-Obiettivi (Non-Goals)
* Non riscrivere l'attuale schema SQLite da zero: si estendono le tabelle esistenti (`events`, `rotations`) preservando la compatibilità retroattiva.
* Non sostituire il CLI `main.py`: rimarrà perfettamente funzionante come interfaccia headless da terminale.

### Anti-Obiettivi (Anti-Goals)
* Non introdurre build complesse con bundler pesanti per la dashboard di default: deve avviarsi con un semplice comando Python.
* Non applicare commit o merge sui branch protetti `master`, `main` o `develop`.

---

## 3. Vincoli Tecnici e di Piattaforma

* **Ambiente Python:** Python 3.15 in `venv`.
* **Database:** SQLite `scoutanalyzer.db` con foreign keys attive.
* **Dipendenze Web:** `fastapi`, `uvicorn`, `pydantic`.
* **Git:** Tutte le modifiche e i commit devono avvenire esclusivamente sul branch `feature/dvw-native-lineups-and-fixes`.

---

## 4. Analisi degli Approcci Considerati

### Core Engine
* **Approccio A (Dual Source: Formazioni Native DVW + Fallback Ricostruzione) [SCELTO]:**
  * Utilizza le formazioni registrate direttamente dallo scoutman/software Data Volley nel 99.7% dei casi.
  * Elimina i falsi positivi di rotazione dovuti a cambi palla non esplicitati con `*z`.
  * Supporta la verifica istantanea della presenza del Libero in campo.
* **Approccio B (Simulazione euristica isolata con comparatore):**
  * Scartato perché più fragile e soggetto a desincronizzazione rispetto al referto reale.

### Architettura Web
* **Opzione 1 (FastAPI + SPA Vanilla CSS/JS) [SCELTA COME DASHBOARD INTEGRATA]:**
  * Zero complessità di build, avvio monolitico leggero, campo da gioco interattivo in CSS/SVG nativo.
* **Opzione 2 (FastAPI + Frontend Vite/React) [ABILITATA VIA API REST / CORS]:**
  * L'API FastAPI è progettata con contratti JSON standardizzati e CORS abilitato, consentendo all'app Vite esistente dell'utente di agganciarsi immediatamente come frontend alternativo o avanzato.

---

## 5. Dettaglio Tecnico dei Componenti

### 5.1 Estensione Parser DVW (`src/dvw_parser.py`)
* Decodifica corretta delle colonne:
  * `parts[8]`: `set_number`
  * `parts[9]`: `home_setter_pos` (1..6)
  * `parts[10]`: `away_setter_pos` (1..6)
  * `parts[14:20]`: `home_lineup` (6 numeri di maglia)
  * `parts[20:26]`: `away_lineup` (6 numeri di maglia)
  * `parts[12]`: `video_frame` (se intero)
* Regex flessibile:
  `^([*aA])(\d{1,2})([SRABDEFBsrabdefb])([A-Za-z0-9 ]?)([#\+!\-/\=])(.*)$`
* Estrazione combinazioni e zone con gestione robusta delle tilde `~`.

### 5.2 Estensione Ingestion & Database (`src/ingestion_manager.py`)
* Aggiunta/aggiornamento su `events` e `rotations` dei campi per la formazione nativa (`home_pos1..6`, `away_pos1..6`).
* Unificazione della registrazione degli errori sintattici.

### 5.3 Regole Semantiche nello State Engine (`src/state_engine.py`)
* Controllo battitore: se la formazione nativa è presente, verifica che `shirt_number == native_pos1`.
* Controllo Libero: se `shirt_number` appartiene a un Libero e `skill == 'S'`, segnala `ERRORE` (*Fallo del Libero al servizio*).
* Controllo Sostituzioni: tracciamento per ciascun set delle sostituzioni effettuate, con segnalazione di `ERRORE` al superamento della 6ª sostituzione.
* Controllo Set: verifica del rispetto dei 25 punti (15 al 5° set) e scarto di 2 punti.

### 5.4 Backend Web FastAPI (`src/api/` e `web_app.py`)
* Endpoints REST:
  * `GET /api/matches`: Lista delle partite a DB con esiti e KPI.
  * `GET /api/matches/{id}`: Dettaglio gara, formazioni, set e punteggi.
  * `GET /api/matches/{id}/events`: Eventi play-by-play con filtri per set, squadra, severità e formazioni.
  * `GET /api/matches/{id}/logs`: Registro audit con raggruppamento per gravità (`ERRORE_CRITICO`, `ERRORE`, `WARNING`).
  * `POST /api/audit/file`: Audit completo e immediato di un percorso `.dvw` o upload file.
  * `POST /api/rosters/sync`: Sincronizzazione roster `.sq`.
* Static Files:
  * Directory `static/` servita su `/`: `index.html`, `style.css`, `app.js`.

### 5.5 Visualizzazione Frontend (Dashboard Grafica)
* Layout responsive con Dark Theme professionale sportivo.
* **Componente Campo Volley:** Rendering 2D del rettangolo di gioco (9x18m diviso a metà rete), con le zone 1-6 per entrambe le squadre, evidenziazione del battitore, del palleggiatore e del Libero.
* Visualizzazione tabellare interattiva con badge colorati per i colpi terminali (Verde: Vincente `#`, Rosso: Errore `=`, Giallo: Contrattacco `!`/`+`).

---

## 6. Decisioni delegate al Builder

* Ottimizzazione delle query SQLite con indici appropriati per rendere fluida la navigazione degli eventi su web.
* Gestione della sincronizzazione automatica dei file statici frontend.
