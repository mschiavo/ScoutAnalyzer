# Diario di Bordo: Test, Audit e Validazione dei File Scout (ScoutAnalyzer)

Questo file raccoglie lo storico cronologico di tutte le analisi, i test su partite reali e le scoperte tecniche effettuate durante lo sviluppo del motore di conformità per la **Serie B1 Femminile**.

---

## 1. Campagna di Test su File Reali di Campionato

Tutti i test sono stati condotti sui file originali salvati in `D:\Volley\B1FB\esempi\` e in `D:\Volley\B1FB\giornata_01\`.

### Sintesi Generale dei File Testati

| File Analizzato | Squadre | Set | Eventi Scout | Esito Audit | Note Tecniche |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `&01_COR-VOL_Vicenza_b1fb_26_s.dvw` | Vicenza Volley vs Cortina Imoco | 4 | 1.542 | **Conforme** | Catturato errore sintattico a riga 1540 (`z13DT=`) e gestito il doppio cambio diagonale |
| `&And02_aduna padova-clodia venezia_sync_marco.dvw` | Aduna Padova vs Clodia Venezia | 4 | 1.516 | **Anomalia rilevata** | Riga 12: tocco prosegue dopo attacco errore `*10AH=` |
| `&And04_aduna padova-peschiera_sync_marco.dvw` | Aduna Padova vs Peschiera | 4 | 1.659 | **100% Regolare** | 0 anomalie riscontrate su tutti e 4 i set |
| `&And01_aduna padova-arena verona_sync_marco.dvw` | Aduna Padova vs Arena Verona | 5 | 1.934 | **Anomalie rilevate** | Rilevati tutti i 4 casi limite reali (punti incongruenti e colpi terminali) |
| `&And06_aduna padova-volano_sync_marco.dvw` | Aduna Padova vs Volano | 3 | 1.379 | **Anomalie rilevate** | Rilevati errori di battuta su rotazione non allineata |

---

## 2. Dettaglio Casi Studio e Diagnosi Errori dello Scoutman

### Caso Studio A: Incongruenza Punteggio (`Arena Verona`, Set 1, Riga 248)
* **Codice Scout:**
  ```text
  [Riga 247] *12AT=X6~24~P2   (Attacco Errore della giocatrice #12 di Casa)
  [Riga 248] *p18:12          (Punteggio incrementato a favore di Casa!)
  ```
* **Diagnosi dello State Engine:**
  Lo scoutman ha assegnato il punto a Casa (`*p18:12`) nonostante l'azione si fosse chiusa con un errore diretto dell'attaccante di Casa (`*12AT=`). Il punto spettava ad Arena Verona (`ap17:13`).
* **Segnalazione emessa:**
  `[ERROR] Incongruenza punteggio: punto assegnato a Casa (*p18:12), ma l'azione precedente si chiudeva a favore di Ospite (*12AT=X6~24~P2 a riga 247)`.

---

### Caso Studio B: Azione che Prosegue Dopo Attacco Sbagliato (`Arena Verona`, Set 3, Riga 966)
* **Codice Scout:**
  ```text
  [Riga 966] a13AT=X5~45~H2   (Attacco Errore dell'Ospite #13)
  [Riga 967] *11DT+~~~45      (Difesa di Casa che rimette la palla in gioco)
  [Riga 968] *01EH+~~F        (Alzata di Casa)
  [Riga 969] *10AH#V5~41~H2X  (Attacco Punto di Casa)
  ```
* **Diagnosi dello State Engine:**
  L'attacco errore `a13AT=` doveva chiudere definitivamente il rally. Invece lo scoutman ha proseguito la registrazione come se la palla fosse ancora viva, chiudendo poi lo scambio con un secondo colpo terminale (`*10AH#`).
* **Segnalazione emessa:**
  `[ERROR] Azione prosegue illegalmente dopo colpo terminale: rilevato tocco '*11DT+~~~45' dopo a13AT=X5~45~H2 (riga 966)`.

---

### Caso Studio C: Attacco Murato e Muro Punto nel Mezzo dell'Azione (`Arena Verona`, Set 4, Righe 1395-1396)
* **Codice Scout:**
  ```text
  [Riga 1395] a02AQ/CF~26~H2  (Attacco Murato dell'Ospite)
  [Riga 1396] *13BQ#~~~~4~~2  (Muro Punto di Casa)
  [Riga 1397] a16DH-~~~~9     (Difesa dell'Ospite che prosegue il gioco)
  [Riga 1398] a12EH+~~F       (Alzata)
  [Riga 1399] a13AH-V5~45~H2  (Contrattacco)
  ```
* **Diagnosi dello State Engine:**
  Il muro punto `*13BQ#` sanciva matematicamente la fine dello scambio (punto per Casa). Lo scoutman ha invece continuato a scoutizzare altri 6 tocchi con contrattacco e punto finale a riga 1402.
* **Segnalazione emessa:**
  `[ERROR] Azione prosegue illegalmente dopo colpo terminale: rilevato tocco 'a16DH-~~~~9' dopo *13BQ#~~~~4~~2 (riga 1396)`.

---

### Caso Studio D: Il Doppio Cambio e il Ricalcolo Nominale (`Vicenza G01`, Set 1, Righe 302-308)
* **Codice Scout:**
  ```text
  [Riga 303] az4      (Cortina in rotazione P4)
  [Riga 304] ac09:21  (Esce la palleggiatrice #9, entra l'opposto #21)
  [Riga 305] ac01:05  (Esce l'opposto #1 in Zona 1, entra la nuova palleggiatrice #5)
  [Riga 306] aP5      (Nuova palleggiatrice: #5)
  [Riga 307] az1      (Ricalcolo rotazione palleggiatrice: P1)
  [Riga 308] a05SM-   (Battuta della nuova palleggiatrice #5)
  ```
* **Scelta Architetturale dello State Engine:**
  Il codice `az1` **non è stato interpretato come una rotazione fisica oraria**, ma come un allineamento nominale della zona in cui si trova la nuova palleggiatrice (#5). In questo modo lo State Engine ha verificato con successo che la #5 si trovava esattamente in Zona 1, **azzerando i falsi allarmi e validando la correttezza del doppio cambio**.

---

### Caso Studio E: Errore di Digitazione In-Line (`Vicenza G01`, Set 4, Riga 1540)
* **Codice Scout:**
  ```text
  [Riga 1540] z13DT=
  ```
* **Diagnosi del Parser Sintattico:**
  Lo scoutman ha premuto per errore la lettera `z` invece di `a` (voleva digitare `a13DT=`). Il parser sintattico in-line ha intercettato immediatamente il prefisso illegale senza mandare in crash il software:
* **Segnalazione emessa:**
  `[ERROR] Riga 1540 | z13DT= -> Prefisso squadra non valido: 'z'`.

---

## 3. Matrice dei Componenti di Validazione

```text
ScoutAnalyzer
├── config/
│    ├── config.json (Percorsi assoluti e parametri di tolleranza)
│    └── datavalley_specs.json (Mappa ruoli, fondamentali e colpi terminali)
├── src/dvw_parser.py
│    ├── Estrazione [3MATCH], [3TEAMS], [3SET], [3PLAYERS] (Livello 1 e 2)
│    └── Validazione sintattica in-line [3SCOUT] (Livello 3)
├── src/roster_manager.py
│    ├── Download .sq da Volley Network con backup intelligente MD5
│    ├── Soft-delete a DB (valid_to) per atlete non più presenti
│    └── Verifica conformità e tesseramenti FIPAV alla data di gara
├── src/state_engine.py
│    ├── Tracciamento formazioni, rotazioni orarie e doppi cambi (Livello 4.1)
│    ├── Controllo colpi terminali definitivi (Livello 4.2)
│    └── Congruenza esito rally vs punteggio a referto *p / ap (Livello 4.3)
└── main.py
     └── Menu CLI a 6 opzioni indipendenti per collaudo e audit completo
```
