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

## Backup e ripristino

Arresta il container prima di copiare le tre cartelle. Copiale nello stesso backup, ad esempio su un disco USB. Conserva `.env` separatamente con accesso limitato. Il fermo evita scritture a metà copia e mantiene allineati SQLite e i file DVW.

Per provare un ripristino, usa una seconda cartella e una seconda istanza, modificando il nome del container e la porta pubblicata. Ripristina tutte e tre le cartelle prima dell'avvio. Dopo l'accesso, verifica elenco partite, dettaglio e rivalidazione di una partita il cui DVW è nel backup.
