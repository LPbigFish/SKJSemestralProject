"""
Haystack Storage Node
=====================
Samostatná FastAPI aplikace. Spouštěj příkazem:

    python haystack_node.py
    # nebo
    python haystack_node.py --host 0.0.0.0 --port 8081 \
        --broker-uri ws://localhost:8080/broker \
        --volume-dir ./haystack_volumes \
        --max-volume-size 104857600

Zodpovědnosti:
  - Naslouchá na tématu storage.write (přes WebSocket broker)
  - Append-only zápis binárních dat do volume souborů
  - Rotace svazků při překročení limitu
  - GET /volume/{volume_id}/{offset}/{size} – rychlé čtení
  - POST /compact/{volume_id} – kompakce svazku (Úkol 4)
"""

import argparse
import asyncio
import json
import logging
from io import BufferedRandom
from pathlib import Path
from typing import Optional

import msgpack
import uvicorn
import websockets
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [HAYSTACK] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ── Konfigurace (lze přepsat CLI argumenty) ──────────────────────────────────
BROKER_URI: str = "ws://localhost:8082/broker"
GATEWAY_URL: str = "http://localhost:8080"
VOLUME_DIR: Path = Path("haystack_volumes")
MAX_VOLUME_BYTES: int = 100 * 1024 * 1024  # 100 MB

# ── Stav aktivního svazku ────────────────────────────────────────────────────
_current_volume_id: int = 1
_current_file: Optional[BufferedRandom] = None  # otevřený file objekt v režimu "ab+"
_volume_lock = asyncio.Lock()  # chrání před souběžným zápisem


# ── Pomocné funkce pro práci se svazky ───────────────────────────────────────

def _volume_path(volume_id: int) -> Path:
    return VOLUME_DIR / f"volume_{volume_id}.dat"


def _detect_last_volume() -> int:
    """Najde nejvyšší existující volume_N.dat při startu."""
    VOLUME_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(VOLUME_DIR.glob("volume_*.dat"))
    if not existing:
        return 1
    # Parsujeme číslo z názvu souboru
    nums = []
    for p in existing:
        try:
            nums.append(int(p.stem.split("_")[1]))
        except (IndexError, ValueError):
            pass
    return max(nums) if nums else 1


def _open_volume(volume_id: int):
    """Otevře (nebo vytvoří) volume soubor v append+read binárním režimu."""
    path = _volume_path(volume_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # "ab+" = append binary + readable; tell() vrací konec souboru
    f = open(path, "ab+")  # noqa: WPS515
    log.info("Otevřen svazek %s (velikost: %d B)", path, f.seek(0, 2) or f.tell())
    return f


def _get_volume_size(volume_id: int) -> int:
    path = _volume_path(volume_id)
    return path.stat().st_size if path.exists() else 0


async def _rotate_volume():
    """Uzavře aktuální svazek a otevře nový s vyšším číslem."""
    global _current_volume_id, _current_file
    if _current_file:
        _current_file.close()
        log.info("Svazek volume_%d.dat uzavřen", _current_volume_id)
    _current_volume_id += 1
    _current_file = _open_volume(_current_volume_id)
    log.info("Rotace → nový svazek volume_%d.dat", _current_volume_id)


# ── Append-only zápis (voláno z broker listeneru) ────────────────────────────

async def write_needle(object_id: str, data: bytes) -> dict:
    """
    Zapíše data na konec aktivního svazku.
    Pokud by zápis způsobil překročení MAX_VOLUME_BYTES, nejprve rotuje.
    Vrátí ACK slovník: {object_id, volume_id, offset, size}.
    """
    global _current_file, _current_volume_id

    async with _volume_lock:
        # Zkontroluj, zda by zápis nepřekročil limit
        current_size = _get_volume_size(_current_volume_id)
        if current_size + len(data) > MAX_VOLUME_BYTES and current_size > 0:
            await _rotate_volume()

        # Seek na konec (pro jistotu – "ab+" vždy zapisuje na konec,
        # ale tell() nemusí být aktuální po reopen)
        assert _current_file is not None, "Aktivní svazek není otevřen"
        _current_file.seek(0, 2)
        offset = _current_file.tell()

        _current_file.write(data)
        _current_file.flush()  # zajistí okamžité uložení na disk

        size = len(data)
        volume_id = _current_volume_id

    log.info(
        "Uloženo: object_id=%s volume=%d offset=%d size=%d",
        object_id, volume_id, offset, size,
    )
    return {
        "object_id": object_id,
        "volume_id": volume_id,
        "offset": offset,
        "size": size,
    }


# ── Broker listener (běží jako asyncio task na pozadí) ───────────────────────

async def broker_listener():
    """
    Připojí se k brokeru jako subscriber na storage.write.
    Po zpracování každé zprávy publikuje ACK na storage.ack.
    Automaticky se reconnectuje při výpadku.
    """
    reconnect_delay = 2  # sekundy mezi pokusy o reconnect

    while True:
        try:
            log.info("Připojuji se k brokeru: %s", BROKER_URI)
            async with websockets.connect(
                BROKER_URI,
                max_queue=None,
                compression=None,
                ping_interval=None,
                ping_timeout=None,
            ) as ws:
                # Přihlásíme se k odběru tématu storage.write
                # Používáme msgpack (binární) pro efektivní přenos dat obrázků
                subscribe_msg: bytes = msgpack.packb(  # type: ignore[assignment]
                    {"action": "subscribe", "topic": "storage.write"}
                )
                await ws.send(subscribe_msg)
                log.info("Subscribován na storage.write")

                reconnect_delay = 2  # reset po úspěšném připojení

                async for raw in ws:
                    try:
                        if isinstance(raw, bytes):
                            msg = msgpack.unpackb(raw, raw=False)
                        else:
                            msg = json.loads(raw)
                    except Exception as e:
                        log.error("Chyba dekódování zprávy: %s", e)
                        continue

                    action = msg.get("action", "")

                    if action == "subscribed":
                        log.info("Broker potvrdil subscribe: %s", msg.get("topic"))
                        continue

                    if action == "deliver":
                        message_id = msg.get("message_id")
                        payload = msg.get("payload", {})
                        await _handle_write_message(ws, message_id, payload)

        except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            log.warning("Broker nedostupný (%s), zkouším znovu za %ds…", e, reconnect_delay)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)  # exponential backoff


async def _handle_write_message(ws, message_id: int, payload: dict):
    """Zpracuje jednu zprávu ze storage.write."""
    object_id = payload.get("object_id")
    # Data jsou zakódována jako seznam intů (msgpack bytes → list) nebo bytes
    raw_data = payload.get("data")

    if not object_id or raw_data is None:
        log.error("Neplatná zpráva (chybí object_id nebo data), msg_id=%s", message_id)
        # ACK stejně odešleme, aby se zpráva neblokovala v brokeru
        await _send_msgpack(ws, {"action": "ack", "message_id": message_id})
        return

    # msgpack může binární data deserializovat jako bytes nebo bytearray
    if isinstance(raw_data, (list, tuple)):
        data = bytes(raw_data)
    elif isinstance(raw_data, (bytes, bytearray)):
        data = bytes(raw_data)
    else:
        log.error("Neočekávaný typ dat: %s, msg_id=%s", type(raw_data), message_id)
        await _send_msgpack(ws, {"action": "ack", "message_id": message_id})
        return

    try:
        ack = await write_needle(object_id, data)
    except Exception as e:
        log.error("Zápis selhal pro object_id=%s: %s", object_id, e)
        await _send_msgpack(ws, {"action": "ack", "message_id": message_id})
        return

    # Odeslat ACK brokeru (potvrdit doručení zprávy)
    await _send_msgpack(ws, {"action": "ack", "message_id": message_id})

    # Publikovat výsledek na storage.ack (pro S3 Gateway)
    ack_publish = {
        "action": "publish",
        "topic": "storage.ack",
        "payload": ack,
    }
    await _send_msgpack(ws, ack_publish)
    log.info("Odesláno storage.ack pro object_id=%s", object_id)


async def _send_msgpack(ws, data: dict):
    try:
        packed: bytes = msgpack.packb(data)  # type: ignore[assignment]
        await ws.send(packed)
    except Exception as e:
        log.error("Chyba při odesílání zprávy: %s", e)


# ── FastAPI aplikace ──────────────────────────────────────────────────────────

app = FastAPI(title="Haystack Storage Node")


@app.on_event("startup")
async def startup():
    """Inicializace svazků a spuštění broker listeneru na pozadí."""
    global _current_volume_id, _current_file
    _current_volume_id = _detect_last_volume()
    _current_file = _open_volume(_current_volume_id)
    asyncio.create_task(broker_listener())
    log.info("Haystack Node spuštěn, aktivní svazek: volume_%d.dat", _current_volume_id)


@app.on_event("shutdown")
async def shutdown():
    """Bezpečné uzavření aktivního svazku."""
    global _current_file
    if _current_file:
        _current_file.close()
        log.info("Aktivní svazek uzavřen")


@app.get("/volume/{volume_id}/{offset}/{size}")
async def read_needle(volume_id: int, offset: int, size: int):
    """
    Přečte přesně `size` bajtů ze souboru volume_{volume_id}.dat
    začínaje od pozice `offset`.

    Používá se interně S3 Gateway při stahování souborů.
    """
    path = _volume_path(volume_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Svazek {volume_id} neexistuje")

    try:
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read(size)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Chyba čtení: {e}")

    if len(data) != size:
        raise HTTPException(
            status_code=416,
            detail=f"Očekáváno {size} B, přečteno {len(data)} B (offset={offset})",
        )

    return Response(content=data, media_type="application/octet-stream")


@app.get("/health")
async def health():
    """Healthcheck endpoint."""
    return {
        "status": "ok",
        "active_volume": _current_volume_id,
        "volume_size_bytes": _get_volume_size(_current_volume_id),
        "max_volume_bytes": MAX_VOLUME_BYTES,
    }


@app.get("/volumes")
async def list_volumes():
    """Vrátí seznam všech svazků a jejich velikostí."""
    VOLUME_DIR.mkdir(parents=True, exist_ok=True)
    volumes = []
    for p in sorted(VOLUME_DIR.glob("volume_*.dat")):
        try:
            vid = int(p.stem.split("_")[1])
            volumes.append({"volume_id": vid, "size_bytes": p.stat().st_size, "path": str(p)})
        except (IndexError, ValueError):
            pass
    return {"volumes": volumes}


# ── Kompakce (Úkol 4) ────────────────────────────────────────────────────────

@app.post("/compact/{volume_id}")
async def compact_volume(volume_id: int, gateway_url: Optional[str] = None):
    """
    Spustí kompakci svazku volume_{volume_id}.dat.
    Tento endpoint může být volán z compact.py nebo přímo.

    gateway_url: přepíše globální GATEWAY_URL (volitelné)
    """
    import aiohttp

    gw_url = gateway_url or GATEWAY_URL
    src_path = _volume_path(volume_id)
    if not src_path.exists():
        raise HTTPException(status_code=404, detail=f"Svazek {volume_id} neexistuje")

    # Nechceme kompaktovat aktivní svazek (mohl by se právě zapisovat)
    if volume_id == _current_volume_id:
        raise HTTPException(
            status_code=409,
            detail="Nelze kompaktovat aktivní svazek. Nejprve proveď rotaci.",
        )

    dst_path = VOLUME_DIR / f"volume_{volume_id}_compacted.dat"

    # 1. Získáme seznam nesmazaných objektů z S3 Gateway pro tento svazek
    async with aiohttp.ClientSession() as session:
        url = f"{gw_url}/files/internal/volume/{volume_id}/objects"
        async with session.get(url) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise HTTPException(
                    status_code=502,
                    detail=f"Gateway vrátila chybu: HTTP {resp.status} {body}",
                )
            objects = await resp.json()  # list of {id, offset, size}

    if not objects:
        log.info("Svazek %d nemá žádné živé objekty, není co kompaktovat", volume_id)
        return {"status": "nothing_to_compact", "volume_id": volume_id}

    log.info("Kompakce svazku %d: %d objektů", volume_id, len(objects))

    # 2. Vytvoříme nový kompaktovaný soubor a přepíšeme objekty těsně za sebe
    new_offset = 0
    updates = []  # seznam {object_id, new_offset, new_size}

    with open(src_path, "rb") as src, open(dst_path, "wb") as dst:
        for obj in objects:
            obj_id = obj["id"]
            old_offset = obj["haystack_offset"]
            size = obj["haystack_size"]

            src.seek(old_offset)
            data = src.read(size)

            if len(data) != size:
                log.warning(
                    "Objekt %s: očekáváno %d B, přečteno %d B – přeskakuji",
                    obj_id, size, len(data),
                )
                continue

            dst.write(data)
            updates.append({
                "object_id": obj_id,
                "volume_id": volume_id,   # volume_id zůstává stejné
                "new_offset": new_offset,
                "new_size": size,
            })
            new_offset += size

    # 3. Odešleme na Gateway aktualizované offsety
    async with aiohttp.ClientSession() as session:
        url = f"{gw_url}/files/internal/bulk-update-location"
        async with session.post(url, json={"updates": updates}) as resp:
            if resp.status != 200:
                body = await resp.text()
                # Kompaktovaný soubor smažeme – offsety nejsou aktualizované
                dst_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=502,
                    detail=f"Gateway odmítla aktualizaci offsetů: HTTP {resp.status} {body}",
                )

    # 4. Nahradíme starý soubor kompaktovaným
    src_path.unlink()
    dst_path.rename(src_path)
    log.info(
        "Kompakce svazku %d dokončena. Přesunuto %d objektů, ušetřeno ~%d B",
        volume_id,
        len(updates),
        (src_path.stat().st_size if src_path.exists() else 0),
    )

    return {
        "status": "compacted",
        "volume_id": volume_id,
        "objects_moved": len(updates),
    }


# ── Vstupní bod ───────────────────────────────────────────────────────────────

def main():
    global BROKER_URI, GATEWAY_URL, VOLUME_DIR, MAX_VOLUME_BYTES

    parser = argparse.ArgumentParser(description="Haystack Storage Node")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--broker-uri", default="ws://localhost:8082/broker")
    parser.add_argument("--gateway-url", default="http://localhost:8080")
    parser.add_argument("--volume-dir", default="haystack_volumes")
    parser.add_argument(
        "--max-volume-size",
        type=int,
        default=100 * 1024 * 1024,
        help="Maximální velikost jednoho svazku v bajtech (výchozí: 100 MB)",
    )
    args = parser.parse_args()

    BROKER_URI = args.broker_uri
    GATEWAY_URL = args.gateway_url
    VOLUME_DIR = Path(args.volume_dir)
    MAX_VOLUME_BYTES = args.max_volume_size

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()