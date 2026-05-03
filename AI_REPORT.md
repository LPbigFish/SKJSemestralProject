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

## Co AI nedělala
- Základní architektura S3 Gateway a Message Brokeru byla implementována ručně předem.
- Zadání samo bylo poskytnuto vyučujícím.
- Testování finálního řešení a spouštění testů probíhalo interaktivně.
