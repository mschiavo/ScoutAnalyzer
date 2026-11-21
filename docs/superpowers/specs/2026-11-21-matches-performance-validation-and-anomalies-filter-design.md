# Design Doc: Performance Lista Gare, Validazione Puntuale/Massiva e Filtro Anomalie

**Data:** 21 Novembre 2026  
**Autore:** Principal Software Architect & Domain Engineer  
**Stato:** Approvato dall'utente  
**Branch:** `feature/auth-multitenant-storage`

---

## 1. Intent e Obiettivi

1. **Eliminazione Bottleneck Performance `/api/matches`:**
   Attualmente l'endpoint `/api/matches` itera su ogni singola partita eseguendo query SQL secondarie per recuperare i set (`match_sets`), calcolare i parziali, il punteggio finale e il conteggio di eventi e anomalie (problema classico N+1 su database remoto).
   **Soluzione:** Denormalizzare e precalcolare i valori di sintesi direttamente nella tabella `matches`:
   - `home_sets_won` (INTEGER DEFAULT 0)
   - `away_sets_won` (INTEGER DEFAULT 0)
   - `final_score` (TEXT DEFAULT '0 - 0')
   - `set_scores` (TEXT DEFAULT '')
   - `sets_count` (INTEGER DEFAULT 0)
   - `events_count` (INTEGER DEFAULT 0)
   - `logs_count` (INTEGER DEFAULT 0)
   - `scout_author` (TEXT)
   In questo modo `/api/matches` diventa una singola query immediata `SELECT ... FROM matches LEFT JOIN teams` con esecuzione in pochi millisecondi.

2. **Validazione Puntuale e Massiva:**
   - **Puntuale:** Nella vista `#view-admin-matches`, aggiungere su ciascuna riga il pulsante `"🔄 Valida Gara"` che invoca `POST /api/admin/matches/{id}/revalidate` per rieseguire lo State Engine su quel singolo match e aggiornare istantaneamente statistiche e anomalie.
   - **Massiva:** In alto nella barra azioni della vista admin, aggiungere il pulsante `"🔄 Valida Tutte le Gare"`. Se il numero di gare a sistema supera 30, mostrare un alert di conferma: *"Ci sono oltre 30 gare caricate ([N]). La validazione completa potrebbe richiedere del tempo. Continuare?"*. Se confermato, invoca `POST /api/admin/rules/revalidate` con feedback visivo e refresh della tabella.

3. **Risoluzione Definitiva Filtro "Solo Anomalie" in Dashboard:**
   - **Compatibilità Tipi SQLite/PostgreSQL:** Su SQLite `is_valid` è memorizzato come `0`/`1`, mentre su PostgreSQL `psycopg` restituisce booleani nativi `true`/`false`. Nel frontend il controllo rigoroso `ev.is_valid === 1` fallisce con i booleani, impedendo il corretto filtraggio.
   - **Isolamento Anomalie:** L'evento deve essere identificato come anomalia tramite `isError = (ev.is_valid === 0 || ev.is_valid === false || Boolean(ev.error_note))`.
   - **Persistenza al Cambio Gara:** Quando l'utente seleziona una nuova partita con il checkbox attivo, `state.errorsOnly` deve essere preservato e applicato correttamente alla nuova lista di eventi caricata.
   - **Visibilità Log a Livello di Set:** Gli errori semantici o generali registrati in `validation_logs` (es. punteggi set anomali) devono essere visibili o segnalati chiaramente anche nella vista eventi, evitando che la tabella rimanga vuota senza spiegazioni per l'utente.

---

## 2. Modello Dati e Migrazioni Database

### Schema `matches` Aggiornato (SQLite e PostgreSQL)
Aggiunta delle colonne di sintesi per garantire l'accesso istantaneo senza subquery:
```sql
ALTER TABLE matches ADD COLUMN IF NOT EXISTS home_sets_won INTEGER DEFAULT 0;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS away_sets_won INTEGER DEFAULT 0;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS final_score TEXT DEFAULT '0 - 0';
ALTER TABLE matches ADD COLUMN IF NOT EXISTS set_scores TEXT DEFAULT '';
ALTER TABLE matches ADD COLUMN IF NOT EXISTS sets_count INTEGER DEFAULT 0;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS events_count INTEGER DEFAULT 0;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS logs_count INTEGER DEFAULT 0;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS scout_author TEXT;
```

### Funzione di Aggiornamento Metriche Gara
Una funzione condivisa (es. `update_match_metrics(cursor, match_id)`) viene invocata sia al termine dell'ingestione (`IngestionManager`), sia al termine del processamento semantico (`MatchStateEngine`), sia durante le chiamate di revalidate.

---

## 3. Specifiche API

1. `GET /api/matches`:
   - Esegue una singola query diretta:
     ```sql
     SELECT 
         m.id, m.match_code, m.scheduled_date, m.home_team_id, m.away_team_id,
         m.home_sets_won, m.away_sets_won, m.final_score, m.set_scores,
         m.sets_count, m.events_count, m.logs_count, m.scout_author,
         ht.code as home_code, ht.name as home_name,
         at.code as away_code, at.name as away_name
     FROM matches m
     LEFT JOIN teams ht ON m.home_team_id = ht.id
     LEFT JOIN teams at ON m.away_team_id = at.id
     [WHERE permessi multi-tenant]
     ORDER BY m.id DESC
     ```
   - Zero cicli secondari in Python, zero subquery pesanti.

2. `POST /api/admin/matches/{id}/revalidate`:
   - Verifica autorizzazione `ADMIN`.
   - Esegue `MatchStateEngine(match_id=id).process_match()`.
   - Aggiorna i campi di riepilogo su `matches`.
   - Restituisce `{"status": "SUCCESS", "match_id": id, "issues_count": n, "match": {...}}`.

3. `POST /api/admin/rules/revalidate`:
   - Itera su tutte le gare eseguendo `MatchStateEngine` in modalità resiliente per ciascuna.
   - Aggiorna le metriche di ogni gara.
   - Restituisce `{"status": "SUCCESS", "revalidated_count": n, "revalidated_matches": [...]}`.

---

## 4. Specifiche Frontend

1. **Gestione Gare (`#view-admin-matches`):**
   - Aggiunta pulsante `#btn-admin-revalidate-all` nella barra comandi superiore (`"🔄 Valida Tutte le Gare"`).
   - Logica click con threshold a 30 gare per alert preventivo.
   - In ciascuna riga tabella, aggiunta azione `"🔄 Valida Gara"` che aggiorna la riga singola senza ricaricare l'intera pagina.

2. **Dashboard e Filtro Anomalie:**
   - In `renderEventsTable()`: normalizzazione di `is_valid` per supportare sia `0/1` sia `false/true`.
   - In `selectMatch(matchId)`: mantenimento dello stato di `filterErrorsOnly.checked` per riapplicare il filtro ai nuovi eventi caricati.
   - Gestione log generali: se il filtro è attivo e ci sono log di validazione senza tocco specifico (es. set score), visualizzazione di un banner informativo o riga di alert dedicata.

---

## 5. Strategia di Test
1. **Database Adapter & Migrazioni:** Test automatico di aggiunta colonne e aggiornamento metriche sia su SQLite che con wrapper PostgreSQL.
2. **Endpoint API:**
   - Test unitario su `GET /api/matches` che verifica l'assenza di N+1 e la corretta restituzione dei campi denormalizzati.
   - Test unitario su `POST /api/admin/matches/{id}/revalidate`.
3. **Frontend Assets:** Test di integrità su `static/app.js` e `static/index.html` per la presenza dei pulsanti di validazione e della logica corretta per `is_valid`.
