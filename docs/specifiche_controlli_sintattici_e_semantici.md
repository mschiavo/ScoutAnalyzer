# Specifiche Complete dei Controlli Sintattici e Semantici (ScoutAnalyzer)

Il presente documento definisce l'insieme esaustivo e definitivo dei controlli di conformità eseguiti da **ScoutAnalyzer** sui file scout Data Volley (`.dvw`) per il campionato **Serie B1 Femminile**.

L'architettura adotta il pattern **ELT disaccoppiato a doppio livello**:
* **Livello 1: Integrità dell'Intestazione e Metadati (Header Validator)**
* **Livello 2: Controllo Roster e Tesseramenti Atlete (Roster Validator)**
* **Livello 3: Validazione Sintattica In-Line dei Codici Scout (Syntax Validator)**
* **Livello 4: Validazione Semantica di Gioco e State Engine (Semantic & State Validator)**

---

## 1. Scala Ufficiale di Severità

| Severità | Destinazione | Criterio di Assegnazione | Esempi Tipici |
| :---: | :--- | :--- | :--- |
| **`WARNING`** | Uso interno (Auditor) | Segnalazione non bloccante su cui prestare attenzione. | Gap temporale compilazione > 1gg; discrepanza ruolo atleta tra referto e DB; assenza libero designato. |
| **`ERRORE`** | Segnalazione alla società | Errore formale o di gioco che non invalida il referto ma richiede correzione. | Discrepanza numero maglia atleta; squadra non censita; azione che prosegue dopo colpo terminale; incongruenza punteggio (*p/ap). |
| **`ERRORE_CRITICO`**| Bloccante immediato | Violazione grave che inficia la regolarità del match o del tesseramento. | Atleta a referto NON presente nel roster ufficiale o non tesserata alla data della partita; codice squadra mancante. |

---

## 2. Livello 1: Integrità dell'Intestazione e Metadati

* **Sezione `[3DATAVOLLEYSCOUT]`:**
  * Controllo formato data e ora compilazione (`DD/MM/YYYY HH.MM.SS`).
  * `GENERATOR-NAM` != `LASTCHANGE-NAM` $\rightarrow$ `WARNING` (discrepanza software/compilatore).
  * `LASTCHANGE-DAY` < `GENERATOR-DAY` $\rightarrow$ `WARNING` (incongruenza temporale).
  * Differenza temporale tra creazione e ultima modifica $> 1$ giorno (da `config.json`) $\rightarrow$ `WARNING`.
  * Date mancanti $\rightarrow$ `WARNING`.
* **Sezione `[3TEAMS]`:**
  * Presenza codice squadra Casa (`*`) e Ospite (`a`).
  * Codice squadra assente $\rightarrow$ `ERRORE_CRITICO`.
  * Codice squadra non registrato nel DB ufficiale $\rightarrow$ `ERRORE`.
* **Sezione `[3SET]`:**
  * Presenza parziali, punteggio finale e determinazione della squadra vincente (`*` o `a`).
  * Rispetto della regola dei 25 punti (15 al quinto set) con almeno 2 punti di scarto.

---

## 3. Livello 2: Roster, Tesseramenti e Sincronizzazione (.sq)

* **Gestione File Roster Ufficiali (`.sq` da Volley Network):**
  * Download tramite URL: `https://volleynetworkitalia.it/data-files/volleynetworkitalia/dropbox/rosters/<roster_code>.sq`.
  * Salvataggio in `D:\Volley\B1FB\rosters\current\<roster_code>.sq`.
  * **Backup Intelligente:** calcolo dell'hash MD5 prima del salvataggio. Viene generato il backup in `D:\Volley\B1FB\rosters\backups\<roster_code>_<yyyymmdd>_<hhmmss>.sq` **solo ed esclusivamente se il file scaricato differisce da quello locale** (nessun file duplicato).
  * **Parser a Tabulazioni (10 Colonne):** Col 0: numero maglia, Col 1: codice atleta (`CET-ANA-01`), Col 2: cognome, Col 3: data nascita, Col 6: marcatore `L` (Libero) o `C` (Capitano), Col 8: nome, Col 9: codice ruolo FIPAV (`dv_role_code` 1-5).
  * **Soft-Delete con Validità:** 
    * Nuova atleta inserita: `valid_from = data_odierna` (o inizio stagione), `valid_to = NULL`.
    * Atleta a DB non più presente nel nuovo file `.sq`: aggiornamento `valid_to = data_odierna` (fine validità per quella squadra senza cancellazione fisica).
* **Controllo Roster nel File Scout (`[3PLAYERS-H]` e `[3PLAYERS-V]`):**
  * Controllo temporale rispetto alla **data della partita** (`valid_from <= match_date` e `valid_to IS NULL OR >= match_date`).
  * Atleta non presente a DB per quella squadra / non valida alla data di gara $\rightarrow$ **`ERRORE_CRITICO`**.
  * Atleta presente a DB ma con numero maglia diverso $\rightarrow$ **`ERRORE`**.
  * Atleta presente a DB con ruolo diverso tra file e DB $\rightarrow$ **`WARNING`**.
  * Numero atlete a referto $< 6$ $\rightarrow$ **`ERRORE`**.
  * Assenza di un Libero designato a referto $\rightarrow$ **`WARNING`**.

---

## 4. Livello 3: Validazione Sintattica In-Line ([3SCOUT])

Eseguita riga per riga durante la lettura del file prima del salvataggio nel DB:
* **Marcatori di Fine Set:** `**1set`, `**2set`, `**3set`, `**4set`, `**5set` (avanzamento set trasparente).
* **Timeout e Note:** `*T`, `aT` (eventi neutri); righe che iniziano con `>` (note dello scoutman ignorate).
* **Codici Speciali di Sistema:**
  * Palleggiatore: `*P..>LUp`, `aP..>LUp`, `*P..`, `aP..`.
  * Rotazione: `*z..>LUp`, `az..>LUp`, `*z1..6`, `az1..6`.
  * Sostituzione: `*c[OUT]:[IN]`, `ac[OUT]:[IN]`.
  * Punteggio: `*pXX:YY`, `apXX:YY`.
  * Cambio palla: `*$$&H=`, `*$$&H#`, `a$$&H=`, `a$$&H#`.
* **Codici di Gioco (Skill Event):**
  * Primi 6 caratteri posizionali obbligatori:
    * `1`: Squadra (`*` o `a` / `A`).
    * `2-3`: Numero maglia a due cifre (`00` - `99`).
    * `4`: Fondamentale (`S`, `R`, `E`, `A`, `B`, `D`, `F`).
    * `5`: Tipo di colpo (`A-Z` / `0-9`).
    * `6`: Valutazione (`#`, `+`, `!`, `-`, `/`, `=`).
  * Dal 7° carattere in poi: decodifica flessibile con tilde `~` per combinazioni d'attacco (`K1`, `X6`, `CF`), target alzata, zona partenza (1-9), zona arrivo (1-9), sottozona (A, B, C, D) e codici estesi.
* **Esito Sintattico:** Se una riga presenta caratteri illegali o formato non riconosciuto (es. `z13DT=`), viene marcata con **`is_valid = 0`** e registrata in `validation_logs` come **`ERROR`** sintattico.

---

## 5. Livello 4: Validazione Semantica e State Engine (Da Database)

Scorre la sequenza temporale degli eventi memorizzati nel DB:
1. **Regola Obbligatoria del Battitore in Zona 1:**
   * A ogni tocco di servizio (`skill = 'S'`), verifica che il numero di maglia dell'atleta corrisponda a chi occupa la **Zona 1** nella tabella `rotations` attiva. Discrepanza $\rightarrow$ **`ERRORE`** (*Fallo di rotazione*).
2. **Simmetria Assoluta tra Casa (`*`) e Ospite (`a`):**
   * Applicazione identica e speculare per entrambe le squadre per formazioni, rotazioni orarie, palleggiatori e cambi.
3. **Gestione del Doppio Cambio e Ricalcolo Nominale:**
   * Quando avviene una sostituzione della palleggiatrice seguita da designazione `*P` o `aP` e dal codice `*z` o `az`:
     * Se la nuova palleggiatrice occupa già la zona indicata dal codice `z` a seguito del cambio, **il motore NON applica una falsa rotazione oraria ai giocatori**, ma aggiorna l'indice nominale della rotazione da P4 a P1 (zero falsi positivi).
4. **Regole dei Colpi Terminali (Fine Azione):**
   * I colpi definitivi che chiudono l'azione sono: `S#`, `S=`, `A#`, `A=`, `A/`, `B#`, `D=`, `R=`, `E=`, `F=`.
   * **Divieto di Prosecuzione Illegale:** se nello stesso rally, dopo un colpo definitivo, compaiono tocchi di gioco regolari (`E`, `A`, `D` con valutazione `+`, `-`, `!`), viene emesso **`ERRORE`**.
   * **Sequenze Legittime Ammesse:**
     * `Attacco #` seguito da `Muro =` o `Difesa =`.
     * `Attacco /` seguito da `Muro #`.
     * `Muro =` seguito da `Difesa =` della stessa squadra.
     * `Servizio #` seguito da `Ricezione =`.
5. **Congruenza Punteggio a Referto:**
   * L'ultimo colpo terminale calcola chi ha diritto al punto.
   * Se il codice successivo incrementa il punteggio della squadra errata, viene emesso **`ERRORE`** (*Incongruenza punteggio*).
   * **Coerenza Prefisso Punteggio:** `*p` deve incrementare tassativamente il punteggio di Casa, `ap` deve incrementare quello di Ospite.
