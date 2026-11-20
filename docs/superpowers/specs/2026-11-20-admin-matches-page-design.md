# Design Doc: Admin Matches Management Page & Dropdown Cleanup

**Data:** 20 Novembre 2026  
**Autore:** Principal Software Architect & Domain Engineer  
**Stato:** Approvato  
**Branch:** `feature/auth-multitenant-storage`

---

## 1. Intent e Obiettivi

Migliorare l'usabilità della piattaforma ScoutAnalyzer 3000 attraverso due interventi mirati:
1. **Pulizia del Menu a Tendina Gare:** Eliminazione visiva di qualsiasi ID tecnico nel testo delle opzioni del menu a tendina "Partita:", adottando un'etichetta leggibile e descrittiva con i nomi reali delle squadre e il nome della gara.
2. **Pagina Dedicata di Gestione Gare (Admin Only):** Creazione di una vista a pagina intera (`#view-admin-matches`) accessibile da `⚙️ Gestione ▾ ➔ 🏐 Gestione Gare` con pulsante per tornare alla Dashboard principale. La pagina presenterà una tabella completa di tutte le gare caricate con:
   - Nome File / Codice Gara
   - Scout / Autore (estratto dalla desinenza del filename, es. `..._sync_marco.dvw` -> `marco`)
   - Squadra Casa (descrizione estesa)
   - Squadra Ospite (descrizione estesa)
   - Risultato Finale (es. `3 - 1` calcolato dai set vinti)
   - Parziali dei Set (es. `25-21, 23-25, 25-18, 25-20`)
   - Conteggio Eventi
   - Conteggio Anomalie
   - Azioni: "👁️ Apri Gara" (ritorna alla dashboard caricando la gara selezionata) e "🗑️ Elimina".

---

## 2. Dettaglio Tecnico dei Componenti

### 2.1 Backend: Estensione di `GET /api/matches`
Per mostrare immediatamente il risultato finale e i parziali di ogni set nella tabella delle gare senza dover fare N chiamate aggiuntive, arricchiamo la risposta dell'endpoint `GET /api/matches` (in `src/api/routes.py`):
- Per ciascun match, esegue una subquery / JOIN per recuperare i set disputati:
  - `home_sets_won`: conteggio set vinti dalla squadra di casa (`winning_team = '*'`)
  - `away_sets_won`: conteggio set vinti dalla squadra ospite (`winning_team = 'a'`)
  - `final_score`: stringa formatted es. `"3 - 1"` (se la gara è terminata) o `"0 - 0"`
  - `set_scores`: lista/stringa dei parziali ordinati per numero di set, es. `"25-21, 23-25, 25-18, 25-20"`
  - `scout_author`: parsing server-side del nome scout dal filename (es. regex `_([a-zA-Z0-9]+)$` da `match_code` o `storage_path`).

### 2.2 Frontend: Navigazione a Due Viste (SPA)
In `static/index.html`:
- Il contenitore principale dell'app conterrà due viste:
  1. `<div id="view-dashboard" class="app-view active">`: la dashboard attuale con campo e tabella.
  2. `<div id="view-admin-matches" class="app-view" style="display: none;">`: la nuova pagina a schermo intero con la tabella completa delle gare e barra di controllo con pulsante `"⬅️ Torna alla Dashboard"` e `"⚠️ Svuota Tutte le Gare"`.

In `static/app.js`:
- Funzione `switchView(viewName)` che gestisce la transizione fluida tra `'dashboard'` e `'admin-matches'`.
- Quando l'admin clicca su "🏐 Gestione Gare" nel menu a tendina "Gestione", viene richiamata `switchView('admin-matches')` e caricata la tabella aggiornata.
- Il pulsante "👁️ Apri Gara" richiama `selectMatch(matchId)` e `switchView('dashboard')`.

### 2.3 Formattazione Dropdown `matchSelect`
In `populateMatchSelect()`:
- L'etichetta di ciascuna option sarà:  
  `${m.home_name || m.home_code} vs ${m.away_name || m.away_code} — ${m.match_code}` (Data: `${m.scheduled_date || "N.D."}`)
- Nessun `ID` tecnico visibile nel testo.

---

## 3. Piano di Test e Validazione
- Test unitari in `tests/test_api.py` per verificare che `GET /api/matches` restituisca `final_score`, `set_scores`, `scout_author`.
- Test frontend in `tests/test_frontend_assets.py` per verificare la presenza di `#view-dashboard`, `#view-admin-matches`, dei pulsanti di navigazione e delle colonne della tabella.
- Verifiche di integrità e test suite completa (100% green).
