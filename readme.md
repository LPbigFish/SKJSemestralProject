# SKJ Project

## Authors

- Filip Štegner
- Vojtěch Niedelský

## AI SLOP

- Model: Claude 4.6
- Využit pro `metadata.py`, `storage_service.py` a logiku ve `file_router`.

- Model: Step 3.5 Flash (free)

- Model: GLM-5.1
- Využit pro implementaci message brokeru (WebSocket endpoint, ConnectionManager, queues, klient, benchmark, testy).
- Promty: Napiš v Pythonu třídu ConnectionManager pro WebSockety, která bude mít seznam active_connections a metody connect, disconnect a broadcast. Potřebuji, aby metoda broadcast v cyklu odesílala zprávy všem připojeným, a pokud jeden z nich selže, aby ho to přeskočilo a pokračovalo na další. K tomu vytvoř soubor s testy přes pytest a pytest-asyncio. Použij v nich asynchronní fixture pro ten manažer a AsyncMock na simulaci WebSocketu, aby šlo ověřit volání metody send_json. Zařiď, aby testy správně awaitovaly všechny operace a neházely chyby s event loopem nebo coroutine was never awaited.
Napiš skript benchmark.py, který pomocí knihovny httpx nebo websockets nasimuluje připojení většího počtu klientů najednou a změří časovou odezvu metody broadcast. Výstupem benchmarku by mělo být jednoduché shrnutí průměrné doby doručení zprávy a počet úspěšně zpracovaných požadavků za sekundu.
Napiš sadu asynchronních testů v pytest pro třídu ConnectionManager, kde pomocí AsyncMock otestuješ metody connect, disconnect a broadcast. Potřebuju, aby testy pokrývaly scénáře úspěšného odeslání zprávy i situaci, kdy jeden klient selže, a aby byly správně ošetřeny přes pytest-asyncio fixtures. K tomu vytvoř soubor run.md, kde bude stručný návod, jak projekt spustit. Do run.md napiš příkazy pro vytvoření virtuálního prostředí, instalaci závislostí z requirements.txt, spuštění samotné aplikace přes uvicorn a příkaz pro spuštění všech testů.
