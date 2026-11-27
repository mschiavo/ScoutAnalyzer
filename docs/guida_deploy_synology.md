# ScoutAnalyzer su Synology con SQLite

ScoutAnalyzer usa un container applicativo e salva database, file DVW e roster sul NAS.

| Cartella del progetto | Contenuto |
| --- | --- |
| `data/` | Database SQLite `scoutanalyzer.db` |
| `storage/` | File DVW e roster sotto `storage/dvw/` |
| `config/` | Configurazione e regole di validazione |

## Primo avvio o aggiornamento

1. Copia il progetto sul NAS, ad esempio in `/volume1/docker/scoutanalyzer`. Se stai aggiornando un'installazione esistente, arresta il progetto, salva `data/`, `storage/` e `config/` e conserva queste cartelle durante l'aggiornamento. Per una nuova installazione usa la cartella `config/` inclusa nei sorgenti.
2. Copia `.env.synology.example` come `.env` nella stessa cartella di `docker-compose.yml`. Imposta `JWT_SECRET` con un valore casuale stabile, ad esempio generato con `openssl rand -hex 32`. Imposta `SCOUT_ADMIN_PASSWORD` con una password nuova, tra 12 e 72 byte, per la prima installazione o per sostituire la password amministrativa predefinita di un'installazione esistente. All'avvio una password amministrativa già personalizzata viene conservata.
3. In Container Manager apri il progetto nella cartella scelta e usa il `docker-compose.yml` incluso. Se usi la CLI dalla stessa cartella, esegui `docker compose up -d --build`.
4. Controlla i log di avvio. Apri `http://<IP-del-NAS>:8000` dalla rete di casa e accedi con l'account amministrativo.
5. Dopo aver verificato l'accesso, puoi rimuovere `SCOUT_ADMIN_PASSWORD` dal file `.env` e ricreare il container. Conserva `JWT_SECRET` per mantenere valide le sessioni dopo un riavvio.

Il progetto monta solo le cartelle di dati e configurazione. Per distribuire modifiche al codice, ricostruisci l'immagine. La sincronizzazione facoltativa dei roster ufficiali resta un download da Volley Network Italia.

## Deploy da Windows via SSH

Per aggiornare un'istanza già installata, abilita SSH in DSM e configura l'accesso con chiave dal PC. Verifica la connessione con `ssh -o BatchMode=yes utente@nome-nas`. L'account deve poter accedere alla cartella del progetto, scriverci il blocco del deploy ed eseguire Docker Compose. Puoi usare anche un alias in `~/.ssh/config`.

Dal repository locale esegui il comando con il tuo host o alias SSH.

```powershell
.\scripts\deploy_synology.ps1 -Nas utente@nome-nas
```

Se il progetto è in un'altra cartella, aggiungi `-ProjectPath /volume1/docker/altra-cartella`. Usa `-UseSudo` se l'account è già configurato per eseguire `sudo -n docker` sul NAS. Se sudo chiede la password, esegui il comando dal tuo terminale con -PromptForSudo e inseriscila quando richiesta. Lo script richiede il Compose Synology con i mount di `data/`, `storage/` e `config/` descritti sopra.

Lo script trasferisce i sorgenti correnti, comprese le modifiche locali, in una cartella temporanea del NAS. Compila l'immagine, aggiorna il container e controlla che l'API risponda. Il trasferimento esclude `.env`, `data/`, `storage/` e `config/`. Le regole di validazione restano quelle configurate sul NAS. Il Compose presente sul NAS resta la definizione del servizio, quindi i cambiamenti a `docker-compose.yml` vanno applicati a parte. L'aggiornamento può interrompere brevemente l'app durante la sostituzione del container.


## Backup e ripristino

Arresta il container prima di copiare le tre cartelle. Copiale nello stesso backup, ad esempio su un disco USB. Conserva `.env` separatamente con accesso limitato. Il fermo evita scritture a metà copia e mantiene allineati SQLite e i file DVW.

Per automatizzare la copia, usa `scripts/backup_synology.sh`. In Utilità di pianificazione DSM, configura un'attività pianificata con script definito dall'utente, mantenendo l'orario esistente se l'attività è già configurata. Usa un account con accesso a Docker (ad esempio `root`) e conserva lo script in una cartella modificabile solo dagli amministratori. La destinazione deve esistere e trovarsi fuori dalla cartella del progetto. Adatta i percorsi al NAS.

```sh
sh /volume1/docker/scoutanalyzer/scripts/backup_synology.sh /volume1/docker/scoutanalyzer /volume1/backup/scoutanalyzer
```

Lo script riavvia il servizio dopo la copia se era attivo. Controlla l'esito dell'attività e la presenza dell'archivio dopo la prima esecuzione pianificata.

Per provare un ripristino, usa una seconda cartella e una seconda istanza, modificando il nome del container e la porta pubblicata. Ripristina tutte e tre le cartelle prima dell'avvio. Dopo l'accesso, verifica elenco partite, dettaglio e rivalidazione di una partita il cui DVW è nel backup.
