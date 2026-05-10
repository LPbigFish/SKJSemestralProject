# Haystack Storage Node

Implementace Haystack architektury pro ukládání souborů inspirovaná Facebook Haystack.
Systém se skládá ze dvou samostatných aplikací: **S3 Gateway** (hlavní API) a **Haystack Node** (úložiště).

---

## Prerequisites

### Windows (PowerShell)
```powershell
pip install -r requirements.txt
```

### Linux / macOS
```bash
pip install -r requirements.txt
```

---

## Database Migration

Před spuštěním je nutné přidat nové sloupce (`volume_id`, `haystack_offset`, `haystack_size`, `status`) do tabulky `files`.

### Windows (PowerShell)
```powershell
$env:PYTHONPATH = "src;$env:PYTHONPATH"
alembic upgrade head
```

### Linux / macOS
```bash
PYTHONPATH=src alembic upgrade head
```

---

## Start the Servers

Haystack Node běží jako **samostatná aplikace** na portu `8081`. S3 Gateway zůstává na portu `8080`.

### Windows (PowerShell)

```powershell
# Terminál 1 – S3 Gateway (broker + API)
$env:PYTHONPATH = "src"
python src\main.py

# Terminál 2 – Haystack Node (úložiště)
python src\haystack\haystack_node.py
```

### Linux / macOS

```bash
# Terminál 1 – S3 Gateway
PYTHONPATH=src python main.py

# Terminál 2 – Haystack Node
python haystack_node.py
```

### Volitelné parametry Haystack Node

| Flag | Výchozí hodnota | Popis |
|------|----------------|-------|
| `--host` | `0.0.0.0` | Bind adresa |
| `--port` | `8081` | Port |
| `--broker-uri` | `ws://localhost:8080/broker` | WebSocket URI brokeru |
| `--gateway-url` | `http://localhost:8080` | HTTP URL S3 Gateway |
| `--volume-dir` | `haystack_volumes/` | Složka pro volume soubory |
| `--max-volume-size` | `104857600` (100 MB) | Max velikost jednoho svazku v bajtech |

Příklad s vlastními parametry:
```bash
python haystack_node.py --port 8081 --max-volume-size 10485760 --volume-dir ./my_volumes
```

---

## Run Tests

### Windows (PowerShell)
```powershell
$env:PYTHONPATH = "src"
# Všechny testy
pytest tests/ -v

# Pouze Haystack testy
pytest tests/test_haystack.py -v

# Broker testy
pytest tests/test_broker.py -v

# Worker testy
pytest tests/test_worker.py -v
```

### Linux / macOS
```bash
# Všechny testy
PYTHONPATH=src pytest tests/ -v

# Pouze Haystack testy
PYTHONPATH=src pytest tests/test_haystack.py -v

# Broker testy
PYTHONPATH=src pytest tests/test_broker.py -v

# Worker testy
PYTHONPATH=src pytest tests/test_worker.py -v
```

> **Poznámka:** Haystack testy (`test_haystack.py`) spouštějí vlastní instanci obou serverů na portech `18770` a `18771` – není potřeba mít spuštěné servery ručně.

---

## Showcase

### 1. Health Check – S3 Gateway

**Windows:**
```powershell
curl.exe http://localhost:8080/
```
**Linux:**
```bash
curl http://localhost:8080/
```

### 2. Health Check – Haystack Node

**Windows:**
```powershell
curl.exe http://localhost:8081/health
```
**Linux:**
```bash
curl http://localhost:8081/health
```

Příklad odpovědi:
```json
{
  "status": "ok",
  "active_volume": 1,
  "volume_size_bytes": 10485760,
  "max_volume_bytes": 104857600
}
```

### 3. Create a Bucket

**Windows:**
```powershell
curl.exe -X POST http://localhost:8080/buckets/ -H "Content-Type: application/json" -d '{\"name\": \"my-bucket\"}'
```
**Linux:**
```bash
curl -X POST http://localhost:8080/buckets/ -H "Content-Type: application/json" -d '{"name": "my-bucket"}'
```

### 4. Upload a File (asynchronní – Haystack)

Upload nyní vrátí **HTTP 202 Accepted** – soubor se fyzicky zapisuje na pozadí přes broker do Haystack Node.

**Windows:**
```powershell
"Hello from Haystack!" | Out-File -FilePath testfile.txt -Encoding ascii
curl.exe -X POST http://localhost:8080/files/upload -F "bucket_id=1" -F "file=@testfile.txt" -H "X-User-Id: alice"
```
**Linux:**
```bash
echo "Hello from Haystack!" > testfile.txt
curl -X POST http://localhost:8080/files/upload -F "bucket_id=1" -F "file=@testfile.txt" -H "X-User-Id: alice"
```

Příklad odpovědi (soubor se ještě nahrává):
```json
{"id": "uuid-zde", "filename": "testfile.txt", "size": 21, "content_type": null}
```

### 5. Download a File

Po chvíli (jakmile Haystack Node potvrdí zápis) je soubor dostupný ke stažení. Gateway ho automaticky načte z Haystack Node.

**Windows:**
```powershell
curl.exe http://localhost:8080/files/<file_id> -H "X-User-Id: alice"
```
**Linux:**
```bash
curl http://localhost:8080/files/<file_id> -H "X-User-Id: alice"
```

> Pokud soubor ještě není ready, vrátí se `HTTP 202` se zprávou `"Soubor se ještě nahrává"`. Zkus znovu za chvíli.

### 6. List Files

**Windows:**
```powershell
curl.exe http://localhost:8080/files/ -H "X-User-Id: alice"
```
**Linux:**
```bash
curl http://localhost:8080/files/ -H "X-User-Id: alice"
```

### 7. Delete a File (soft delete)

Soubor se pouze označí jako smazaný v databázi. Haystack Node se o mazání **nedozví** – data ve volume souboru fyzicky zůstávají.

**Windows:**
```powershell
curl.exe -X DELETE http://localhost:8080/files/<file_id> -H "X-User-Id: alice"
```
**Linux:**
```bash
curl -X DELETE http://localhost:8080/files/<file_id> -H "X-User-Id: alice"
```

### 8. List Volumes (Haystack Node)

**Windows:**
```powershell
curl.exe http://localhost:8081/volumes
```
**Linux:**
```bash
curl http://localhost:8081/volumes
```

Příklad odpovědi:
```json
{
  "volumes": [
    {"volume_id": 1, "size_bytes": 52428800, "path": "haystack_volumes/volume_1.dat"},
    {"volume_id": 2, "size_bytes": 10485760, "path": "haystack_volumes/volume_2.dat"}
  ]
}
```

### 9. Read Directly from Haystack Node

Přímé čtení dat ze svazku (interně používá Gateway, ale lze volat i ručně):

**Windows:**
```powershell
curl.exe http://localhost:8081/volume/1/0/21
```
**Linux:**
```bash
curl http://localhost:8081/volume/1/0/21
```

### 10. Compaction (Defragmentace)

Kompakce odstraní „díry" po smazaných souborech a ušetří místo na disku.

#### Přes skript `compact.py`

**Windows:**
```powershell
# Kompaktuj konkrétní svazek
python compact.py --volume-id 1

# Kompaktuj všechny neaktivní svazky
python compact.py --all
```
**Linux:**
```bash
python compact.py --volume-id 1
python compact.py --all
```

#### Přes HTTP endpoint (Haystack Node)

**Windows:**
```powershell
curl.exe -X POST "http://localhost:8081/compact/1?gateway_url=http://localhost:8080"
```
**Linux:**
```bash
curl -X POST "http://localhost:8081/compact/1?gateway_url=http://localhost:8080"
```

Příklad odpovědi:
```json
{"status": "compacted", "volume_id": 1, "objects_moved": 42}
```

> **Poznámka:** Aktivní svazek (ten, do kterého se právě zapisuje) nelze kompaktovat – endpoint vrátí `HTTP 409`. Počkej na rotaci nebo nastav menší `--max-volume-size`.

#### Automatické spouštění přes cron (Linux)

```bash
# Každou noc ve 2:00
0 2 * * * /usr/bin/python3 /opt/mycloud/compact.py --all >> /var/log/compact.log 2>&1
```

---

## Datový tok (přehled)

```
POST /files/upload
  → Gateway uloží záznam (status = "uploading") → HTTP 202
  → broker publish → topic: storage.write
  → Haystack Node přijme, zapíše do volume_N.dat (append-only)
  → broker publish → topic: storage.ack {object_id, volume_id, offset, size}
  → Gateway ACK listener aktualizuje DB → status = "ready"

GET /files/{id}
  → Gateway přečte volume_id / offset / size z DB
  → interní GET na Haystack Node: /volume/{id}/{offset}/{size}
  → data přeposlána uživateli

DELETE /files/{id}
  → is_deleted = True v DB
  → Haystack Node se nedozví nic, data zůstávají na disku

python compact.py --volume-id 1
  → Haystack POST /compact/1
  → načte živé objekty z Gateway
  → přepíše je do volume_1_compacted.dat bez mezer
  → Gateway aktualizuje offsety
  → starý soubor smazán
```

---

## API Endpoints Summary

### S3 Gateway (`localhost:8080`)

| Metoda | Cesta | Popis |
|--------|-------|-------|
| `GET` | `/` | Health check |
| `POST` | `/buckets/` | Vytvoř bucket |
| `GET` | `/buckets/{id}/objects/` | Seznam souborů v bucketu |
| `GET` | `/buckets/{id}/billing/` | Billing statistiky |
| `GET` | `/files/` | Seznam souborů (filtr: `X-User-Id`) |
| `POST` | `/files/upload` | Nahrání souboru → HTTP 202 (async Haystack) |
| `GET` | `/files/{id}` | Stažení souboru (přes Haystack nebo disk) |
| `DELETE` | `/files/{id}` | Soft delete |
| `WS` | `/broker` | WebSocket message broker |

### Haystack Node (`localhost:8081`)

| Metoda | Cesta | Popis |
|--------|-------|-------|
| `GET` | `/health` | Stav node + aktivní svazek |
| `GET` | `/volumes` | Seznam všech svazků |
| `GET` | `/volume/{id}/{offset}/{size}` | Přímé čtení dat ze svazku |
| `POST` | `/compact/{volume_id}` | Spustí kompakci svazku |
