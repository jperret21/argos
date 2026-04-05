#!/usr/bin/env python3
# main.py — Backend FastAPI SeerControl
# Usage : pip install fastapi uvicorn httpx && uvicorn backend.main:app --port 5123

import socket
import json
import asyncio
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="SeerControl", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CLIENT_ID = 1
_tx_counter = 0


def _next_tx() -> int:
    global _tx_counter
    _tx_counter += 1
    return _tx_counter


# ---------------------------------------------------------------------------
# Discovery UDP
# ---------------------------------------------------------------------------

def _discover_alpaca_sync(timeout: float = 8.0) -> list[dict]:
    results = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    sock.bind(("", 0))
    try:
        sock.sendto(b"alpacadiscovery1", ("255.255.255.255", 32227))
        print(f"[Discovery] Broadcast envoyé sur :32227, attente {timeout}s…")
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                resp = json.loads(data.decode())
                port = resp.get("AlpacaPort", 80)
                entry = {"host": addr[0], "port": port}
                results.append(entry)
                print(f"[Discovery] Trouvé : {addr[0]}:{port}")
            except socket.timeout:
                break
            except Exception as exc:
                print(f"[Discovery] Erreur parsing : {exc}")
    finally:
        sock.close()
    return results


@app.get("/discover")
async def discover(timeout: float = Query(default=8.0, ge=1.0, le=30.0)):
    """Scan UDP Alpaca sur le LAN et retourne la liste des devices trouvés."""
    devices = await asyncio.get_event_loop().run_in_executor(
        None, _discover_alpaca_sync, timeout
    )
    print(f"[Discovery] {len(devices)} appareil(s) trouvé(s).")
    return {"devices": devices}


# ---------------------------------------------------------------------------
# Proxy Alpaca GET
# ---------------------------------------------------------------------------

@app.get("/alpaca/get")
async def alpaca_get(
    host: str = Query(..., description="IP ou hostname du device Alpaca"),
    port: int = Query(..., description="Port Alpaca du device"),
    device: str = Query(..., description="Type de device (telescope, camera, focuser, filterwheel)"),
    device_number: int = Query(default=0),
    property: str = Query(..., description="Propriété Alpaca à lire"),
):
    """Proxifie un GET Alpaca vers le device pour éviter les problèmes CORS."""
    url = f"http://{host}:{port}/api/v1/{device}/{device_number}/{property}"
    params = {"ClientID": CLIENT_ID, "ClientTransactionID": _next_tx()}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Timeout contacting {host}:{port}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Proxy Alpaca PUT
# ---------------------------------------------------------------------------

class AlpacaPutRequest(BaseModel):
    host: str
    port: int
    device: str
    device_number: int = 0
    method: str
    params: dict[str, Any] = {}


@app.put("/alpaca/put")
async def alpaca_put(req: AlpacaPutRequest):
    """Proxifie un PUT Alpaca vers le device pour éviter les problèmes CORS."""
    url = f"http://{req.host}:{req.port}/api/v1/{req.device}/{req.device_number}/{req.method}"

    form_data = {
        "ClientID": str(CLIENT_ID),
        "ClientTransactionID": str(_next_tx()),
        **{k: str(v) for k, v in req.params.items()},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.put(
                url,
                content="&".join(f"{k}={v}" for k, v in form_data.items()),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Timeout contacting {req.host}:{req.port}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "SeerControl Backend"}


# ---------------------------------------------------------------------------
# Entrypoint direct
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    print("=" * 55)
    print("  SeerControl Backend — FastAPI")
    print("  http://localhost:5123")
    print("  GET  /discover              → scan UDP Alpaca LAN")
    print("  GET  /alpaca/get            → proxy GET Alpaca")
    print("  PUT  /alpaca/put            → proxy PUT Alpaca")
    print("  GET  /health                → statut")
    print("  GET  /docs                  → Swagger UI")
    print("=" * 55)
    uvicorn.run("main:app", host="localhost", port=5123, reload=False)
