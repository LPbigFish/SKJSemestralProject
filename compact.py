"""
compact.py – Kompakční skript pro Haystack svazky
=================================================
Spouštění:

    # Kompaktuj svazek č. 1
    python compact.py --volume-id 1

    # Všechny svazky kromě aktivního (zjistí se automaticky)
    python compact.py --all

    # Přepis výchozích URL
    python compact.py --volume-id 2 \\
        --haystack-url http://localhost:8081 \\
        --gateway-url  http://localhost:8080

Doporučené spouštění přes cron (každou noc ve 2:00):
    0 2 * * * /usr/bin/python3 /opt/mycloud/compact.py --all >> /var/log/compact.log 2>&1

Algoritmus:
  1. Zeptá se S3 Gateway na seznam živých objektů pro daný svazek.
  2. Zavolá Haystack Node POST /compact/{volume_id} nebo POST /compact-all:
     --volume-id: kompaktuje jeden svazek interně (odstraní smazaná data, zhustí)
     --all: provede globální kompakci – zkompatkuje každý svazek, pak přesune
            objekty z vyšších svazků do uvolněného místa v nižších svazcích.
            Prázdné svazky po přesunu jsou odstraněny. DB záznamy smazaných
            souborů jsou vymazány.
"""

import argparse
import asyncio
import logging
import sys

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [COMPACT] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

HAYSTACK_URL = "http://localhost:8081"
GATEWAY_URL = "http://localhost:8080"


async def get_active_volume(haystack_url: str) -> int:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{haystack_url}/health") as resp:
            if resp.status != 200:
                raise RuntimeError(f"Haystack health check selhal: HTTP {resp.status}")
            data = await resp.json()
            return data["active_volume"]


async def get_all_volumes(haystack_url: str) -> list[int]:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{haystack_url}/volumes") as resp:
            if resp.status != 200:
                raise RuntimeError(f"Nelze získat seznam svazků: HTTP {resp.status}")
            data = await resp.json()
            return [v["volume_id"] for v in data["volumes"]]


async def compact_volume(volume_id: int, haystack_url: str, gateway_url: str) -> dict:
    url = f"{haystack_url}/compact/{volume_id}?gateway_url={gateway_url}"
    log.info("Spouštím kompakci svazku %d …", volume_id)

    async with aiohttp.ClientSession() as session:
        async with session.post(url, timeout=aiohttp.ClientTimeout(total=3600)) as resp:
            body = await resp.json()
            if resp.status == 200:
                log.info(
                    "Svazek %d: kompakce OK – přesunuto %d objektů",
                    volume_id,
                    body.get("objects_moved", "?"),
                )
                return body
            elif resp.status == 409:
                log.warning("Svazek %d: aktivní svazek, přeskakuji", volume_id)
                return {"status": "skipped_active", "volume_id": volume_id}
            else:
                log.error("Svazek %d: chyba kompakce – %s", volume_id, body)
                return {"status": "error", "volume_id": volume_id, "detail": body}


async def compact_all(haystack_url: str, gateway_url: str) -> dict:
    """
    Globální kompakce: zkompatkuje všechny svazky, přesune objekty mezi
    svazky pro maximální zhutnění, odstraní prázdné svazky a vymaže
    DB záznamy smazaných souborů.
    """
    url = f"{haystack_url}/compact-all?gateway_url={gateway_url}"
    log.info("Spouštím globální kompakci (compact-all) …")

    async with aiohttp.ClientSession() as session:
        async with session.post(url, timeout=aiohttp.ClientTimeout(total=3600)) as resp:
            body = await resp.json()
            if resp.status == 200:
                details = body.get("details", [])
                for d in details:
                    log.info(
                        "  Svazek %d: %s",
                        d.get("volume_id", "?"),
                        d.get("status", "?"),
                    )
                log.info("Globální kompakce dokončena")
                return body
            else:
                log.error("Globální kompakce selhala: %s", body)
                return {"status": "error", "detail": body}


async def run(args):
    haystack_url = args.haystack_url
    gateway_url = args.gateway_url

    if args.all:
        try:
            await get_active_volume(haystack_url)
        except RuntimeError as e:
            log.error("Haystack Node nedostupný: %s", e)
            sys.exit(1)

        result = await compact_all(haystack_url, gateway_url)
        if result.get("status") == "error":
            sys.exit(1)

    elif args.volume_id is not None:
        await compact_volume(args.volume_id, haystack_url, gateway_url)
    else:
        log.error("Zadej --volume-id <N> nebo --all")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Haystack Compaction Script")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--volume-id", type=int, help="ID svazku ke kompakci")
    group.add_argument("--all", action="store_true", help="Kompaktuj všechny neaktivní svazky")
    parser.add_argument("--haystack-url", default=HAYSTACK_URL)
    parser.add_argument("--gateway-url", default=GATEWAY_URL)
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()