# AI Report – Image Processing Worker

## Použití AI

Při implementaci Image Processing Workera byl využit AI asistent (Gemini Code Assist / opencode) následujícím způsobem:

### Architektura a návrh
- AI navrhla celkovou architekturu řešení – rozdělení na `worker/image_ops.py` (NumPy operace) a `worker/worker.py` (asynchronní smyčka, komunikace s brokerem a gateway).
- AI pomohla definovat formát zpráv pro topics `image.jobs` a `image.done` včetně payload struktur.

### Generování kódu
- **`worker/image_ops.py`** – všech 5 NumPy operací (invert, flip, crop, brightness, grayscale) bylo napsáno AI na základě zadání. AI správně implementovala vektorizaci, saturaci pomocí `np.clip` a vážený průměr pro grayscale (ITU-R BT.601).
- **`worker/worker.py`** – AI vygenerovala kompletní asynchronní worker loop včetně WebSocket komunikace s brokerem, HTTP download/upload přes `aiohttp`, error handlingu a graceful zpracování neplatných operací.
- **`src/endpoints/process.py`** – AI vytvořila nový REST endpoint `POST /buckets/{bucket_id}/objects/{file_id}/process` s validací operací a integrací s interním brokerem.
- **`tests/test_worker.py`** – AI napsala 4 integrační testy: batch 10 úloh, neplatná operace, crop mimo rozměry a verifikace správnosti pixelů po invertu.

### Debugging
- Při import chybě v testech (`from worker import worker`) AI identifikovala problém s Python path a navrhla opravu – použití project root místo `worker/` adresáře v `sys.path`.

### Revize
- Po implementaci AI provedla systematickou kontrolu vůči zadání a identifikovala chybějící validaci operací v gateway endpointu (operace se přijímaly bez kontroly). Na základě toho byla přidána validace s `VALID_OPERATIONS` setem.

---
# AI Report – Frontend (SvelteKit)

## Použití AI

Při úpravách frontendu byl využit AI asistent (opencode) následujícím způsobem:

### Adaptace Haystack Node na samostatnou subpage

Na základě OpenAPI specifikace (`openapi-haystack-node.json`) AI vytvořila:

- **`src/routes/haystack/+page.svelte`** – Dashboard s health indikátorem, tabulkou volumes a tlačítkem pro kompakci.
- **`src/routes/haystack/api/[...path]/+server.ts`** – API proxy přeposílající požadavky na Haystack Node backend.
- **`src/lib/haystack-api.ts`** – API klient s funkcemi `getHealth()`, `listVolumes()`, `compactVolume()`.
- **`src/lib/types.ts`** (úprava) – Přidány typy `VolumeInfo`, `VolumeListResponse`.

### Implementace TODO úkolů z TODO.md

AI postupně implementovala všechny úkoly:

1. **Oprava `VolumeInfo.size` → `size_bytes`** – Pole `size` bylo přejmenováno na `size_bytes` podle skutečné API odpovědi.
2. **Create Bucket UI** – Přidán formulář pro vytvoření bucketu do hlavní stránky.
3. **`x-user-id` hlavička do `createBucket()`** – Chybějící hlavička přidána pro konzistenci s ostatními API voláními.
4. **Bucket list/switcher** – Přidán `<select>` dropdown načítající seznam bucketů z `GET /buckets/`.
5. **Upload status** – `FileBrowser` nyní zobrazuje spinner u souborů se statusem `"uploading"`.
6. **File type ikony** – Implementovány ikony pro PDF, TXT, video, audio, ZIP/archive.

### Služby Status Page

- **`src/routes/services/+page.svelte`** – Unified dashboard zobrazující health všech 4 služeb (S3 Gateway, Haystack Node, Message Broker, Worker) s auto-refreshem každých 15s.
- **`src/routes/services/worker/api/[...path]/+server.ts`** – Proxy na Worker (:8083).
- **`src/routes/services/broker/api/[...path]/+server.ts`** – Proxy na Message Broker (:8082).
- **Oprava S3 health check** – S3 Gateway nemá `/health` endpoint, používá `GET /`.

### Vylepšení Job Status

- **Jméno souboru v jobech** – `JobStatus` nyní zobrazuje název souboru vedle operace.
- **Auto-refetch po dokončení** – Když všechny active joby přejdou do completed stavu, automaticky se refetchuje seznam souborů.
- **Separace active/completed** – Active joby jsou zvýrazněny modře, completed jsou schované pod `<details>`.

### Navigace a layout

- **`src/routes/+layout.svelte`** – Přidána horní navigační lišta s odkazy na File Browser, Haystack Node a Services.

## Co AI nedělala
- Základní architektura S3 Gateway a Message Brokeru byla implementována ručně předem.
- Zadání samo bylo poskytnuto vyučujícím.
- Testování finálního řešení a spouštění testů probíhalo interaktivně.
- Backendová logika pro bucket list endpoint (`GET /buckets/`) byla napsána ručně.
