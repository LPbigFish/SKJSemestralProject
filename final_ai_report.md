# AI Report – Haystack Storage Node

## Použití AI

Při implementaci Haystack Storage Node byl využit AI asistent (Claude, Anthropic) následujícím způsobem:

### Architektura a návrh
- AI navrhla formát ACK zpráv mezi Haystack Node a S3 Gateway (topics `storage.write` a `storage.ack`) a strukturu payload pro přenos binárních dat přes MessagePack.
- AI navrhla schéma eventual consistency – stav `uploading` → `ready` a kdy přesně zaúčtovat billing (až po ACK, ne při přijetí uploadu).
- AI navrhla append-only přístup k zápisu do volume souborů včetně logiky rotace svazků při překročení limitu.

### Generování kódu
- **`src/haystack/haystack_node.py`** – AI vygenerovala kompletní implementaci Haystack Node včetně append-only zápisu, rotace svazků, broker listeneru na pozadí přes `asyncio.create_task`, HTTP endpointů pro čtení a kompakci.
- **`src/endpoints/files.py`** – AI přepsala upload endpoint na asynchronní tok přes broker, přidala `storage_ack_listener` běžící na pozadí, upravila GET endpoint pro čtení přes Haystack Node přes `httpx` a přidala interní endpointy pro kompakci.
- **`main.py`** – AI upravila startup event pro spuštění ACK listeneru jako background tasku.
- **`alembic/versions/`** – AI vygenerovala migraci přidávající sloupce `volume_id`, `haystack_offset`, `haystack_size` a `status` do tabulky `files`.
- **`repository/repo.py`** – AI rozšířila model `FileRecord` o nové Haystack sloupce.
- **`compact.py`** – AI napsala standalone kompakční skript s CLI rozhraním a podporou `--all` pro dávkovou kompakci.
- **`tests/test_haystack.py`** – AI napsala 11 integračních testů pokrývajících zdraví node, zápis a čtení, rotaci svazků, celý upload tok přes Gateway a soft delete.
- **`HOW_TO_RUN.md`** – AI sepsala instrukční dokumentaci pro Windows i Linux.

### Debugging a opravy chyb
- AI opravila sérii typových chyb hlášených Pyrightem – zejména `msgpack.packb()` vracející `bytes | None`, nesprávnou anotaci `file: File(...) = File(...)`, `Optional` parametry a narrowing přes `assert` pro type checker.
- AI diagnostikovala a opravila problém s Alembic historií – projekt měl dvě větve migrací (`processing_jobs` a `haystack columns`), které bylo nutné sloučit přes `alembic merge heads`.
- AI identifikovala a opravila konfigurační problém v testech – `BROKER_URI` v `files.py` bylo hardcoded na `localhost:8080`, zatímco testovací server běžel na jiném portu. Oprava spočívala v dynamickém čtení přes `import endpoints.files as _self` a nastavení hodnoty na modulu před spuštěním serveru v testu.
- AI opravila `ModuleNotFoundError: No module named 'haystack_node'` v testech nahrazením relativního `sys.path.insert(0, ".")` za absolutní cestu přes `Path(__file__).resolve()`.
- AI opravila logickou chybu v testu `test_multiple_needles_correct_offsets` – párování ACK zpráv s původními daty se dělo podle pořadí místo podle `object_id`, což selhávalo při jiném pořadí doručení. Oprava zavedla `payload_map` a filtrování `our_ids`.

### Revize
- Po implementaci AI provedla kontrolu vůči zadání a identifikovala že kompakce odesílá offsety hromadně na konci místo průběžně – toto bylo zdokumentováno jako vědomá odchylka (atomičtější operace).
- AI systematicky prošla všechny 4 úkoly zadání a ověřila pokrytí každého požadavku.

## Co AI nedělala
- Rozhodnutí o struktuře projektu (`src/haystack/` jako samostatný modul) bylo provedeno samostatně.
- Spouštění testů, interpretace výstupů a rozhodování o dalším postupu při každé iteraci probíhalo interaktivně – student řídil celý debugging proces.
- Integrace výsledného kódu do projektu, řešení path konfliktů a finální ověření funkčnosti proběhlo samostatně.
- Zadání bylo poskytnuto vyučujícím.
