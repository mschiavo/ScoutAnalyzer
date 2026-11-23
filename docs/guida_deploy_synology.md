# Guida Deploy ScoutAnalyzer su Synology NAS (Docker / Container Manager)

Questa guida illustra come avviare **ScoutAnalyzer** direttamente sul proprio Synology NAS utilizzando **Container Manager** (DSM 7.2+) o il pacchetto **Docker** (DSM 7.0/7.1 e DSM 6).

---

## 🌟 Vantaggi del Deploy su Synology NAS
1. **Zero Cold Start:** Il server è sempre online 24/7. L'apertura della pagina è istantanea (meno di 100 ms).
2. **Massima Velocità Database:** Il file SQLite e i file DVW risiedono direttamente sui dischi del NAS, senza alcuna latenza cloud.
3. **Controllo e Privacy Totale:** Nessun dato o file di gara transita o risiede su server terzi.

---

## 📁 1. Preparazione delle Cartelle sul NAS (File Station)

1. Apri **File Station** sul Synology DSM.
2. All'interno della cartella condivisa `docker/` (creata automaticamente all'installazione di Container Manager), crea una cartella denominata `scoutanalyzer`:
   ```text
   /docker/scoutanalyzer/
   ```
3. All'interno di `/docker/scoutanalyzer/`, crea le tre cartelle persistenti:
   - `/docker/scoutanalyzer/data/` (conterrà il database `scoutanalyzer.db`)
   - `/docker/scoutanalyzer/storage/` (conterrà i file `.dvw` caricati)
   - `/docker/scoutanalyzer/config/` (conterrà la configurazione e le regole)

> **Nota:** Se vuoi trasferire il database con le partite che avevi già in locale, ti basta copiare il file `scoutanalyzer.db` dentro la cartella `/docker/scoutanalyzer/data/`.

---

## 🚀 2. Deploy con Container Manager (DSM 7.2+)

Container Manager supporta nativamente i progetti Docker Compose.

1. Apri l'applicazione **Container Manager** dal menu principale di DSM.
2. Nel menu a sinistra, clicca su **Progetto** (Project), quindi clicca su **Crea** (Create).
3. Compila la schermata guidata:
   - **Nome progetto:** `scoutanalyzer`
   - **Percorso:** seleziona `/docker/scoutanalyzer`
   - **Origine:** seleziona *"Crea docker-compose.yml"*
4. Incolla il seguente contenuto nell'editor:

```yaml
services:
  scoutanalyzer:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: scoutanalyzer
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - STORAGE_BACKEND=local
      - SCOUT_DB_PATH=/app/data/scoutanalyzer.db
      - JWT_SECRET_KEY=synology-scoutanalyzer-secret-key-super-sicura
    volumes:
      - ./data:/app/data
      - ./storage:/app/storage
      - ./config:/app/config
      - ./src:/app/src
      - ./static:/app/static
      - ./database:/app/database
```

5. Clicca su **Avanti**, conferma i passaggi e clicca su **Fine**.
6. Container Manager scaricherà l'immagine, compilerà il container e avvierà ScoutAnalyzer.

---

## 🌐 3. Accesso all'Applicazione

Una volta che il container è in stato **In esecuzione** (verde):
- Apri il browser da qualsiasi computer, tablet o smartphone connesso alla rete Wi-Fi di casa.
- Digita l'indirizzo IP del tuo NAS seguito dalla porta `8000`:
  ```text
  http://192.168.1.XXX:8000
  ```
  *(Sostituisci `192.168.1.XXX` con l'indirizzo IP locale del tuo Synology NAS)*
- Effettua il login con l'utente amministratore standard:
  - **Username:** `admin`
  - **Password:** `adminpassword`

---

## 🔒 4. Accesso da Fuori Casa (Opzionale e Gratuito)

Se desideri accedere a ScoutAnalyzer anche quando sei fuori casa o in palestra senza aprire porte sul router:

### Metodo A: Cloudflare Tunnel (Consigliato - Zero Porte Aperte)
1. Installa il container `cloudflared` sul Synology (o configura il tunnel dalla dashboard di Cloudflare Zero Trust, gratuito).
2. Il tunnel punta a `http://localhost:8000`.
3. Ottieni un dominio sicuro (es. `https://scout.tuodominio.it`) con certificato SSL automatico.

### Metodo B: Tailscale VPN (Pronto in 2 minuti)
1. Installa il pacchetto **Tailscale** dal *Centro Pacchetti* del Synology.
2. Installa l'app Tailscale sul tuo laptop/smartphone.
3. Potrai aprire ScoutAnalyzer ovunque tu sia digitando l'IP Tailscale del NAS (es. `http://100.x.y.z:8000`).

---

## 🔄 5. Manutenzione e Backup
- Per fare il backup di tutto ScoutAnalyzer (gare, database e statistiche), ti basta fare una copia della cartella `/docker/scoutanalyzer/data/` e `/docker/scoutanalyzer/storage/` tramite Hyper Backup di Synology.
