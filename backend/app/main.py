import asyncio
import os
import re
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from serial_manager import SerialManager

LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

manager = SerialManager(log_dir=LOG_DIR, baud_rate=BAUD_RATE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager.start()
    yield
    manager.stop()


app = FastAPI(title="Serial Logger", lifespan=lifespan)


# --- REST API ---


@app.get("/api/ports")
async def list_ports():
    return manager.get_ports_info()


@app.get("/api/logs/{port_id}/dates")
async def available_dates(port_id: str):
    port_dir = Path(LOG_DIR) / port_id
    if not port_dir.exists():
        return {"dates": []}
    dates = []
    for f in sorted(port_dir.glob("*.log")):
        try:
            date.fromisoformat(f.stem)
            dates.append(f.stem)
        except ValueError:
            continue
    return {"dates": dates}


def _tail_lines(filepath: Path, n: int) -> list[str]:
    """Read last *n* lines from a file without loading it entirely."""
    if not filepath.exists() or filepath.stat().st_size == 0:
        return []
    lines: list[str] = []
    block_size = 8192
    with open(filepath, "rb") as f:
        f.seek(0, 2)
        remaining = f.tell()
        while remaining > 0 and len(lines) <= n:
            read_size = min(block_size, remaining)
            remaining -= read_size
            f.seek(remaining)
            block = f.read(read_size)
            lines = block.decode("utf-8", errors="replace").splitlines() + lines
    return lines[-n:]


@app.get("/api/logs/{port_id}/tail")
async def tail_logs(port_id: str, lines: int = Query(500, ge=1, le=10000)):
    port_dir = Path(LOG_DIR) / port_id
    if not port_dir.exists():
        return {"lines": [], "total": 0}

    log_files = sorted(port_dir.glob("*.log"), reverse=True)
    result: list[str] = []
    remaining = lines

    for lf in log_files:
        if remaining <= 0:
            break
        chunk = _tail_lines(lf, remaining)
        result = chunk + result
        remaining -= len(chunk)

    return {"lines": result[-lines:], "total": len(result)}


@app.get("/api/logs/{port_id}")
async def get_logs(
    port_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(5000, ge=1, le=50000),
    search: Optional[str] = Query(None),
):
    port_dir = Path(LOG_DIR) / port_id
    if not port_dir.exists():
        return {"lines": [], "has_more": False}

    d_from = date.fromisoformat(date_from) if date_from else date(2000, 1, 1)
    d_to = date.fromisoformat(date_to) if date_to else date.today()

    log_files = sorted(port_dir.glob("*.log"))
    relevant = []
    for lf in log_files:
        try:
            fd = date.fromisoformat(lf.stem)
            if d_from <= fd <= d_to:
                relevant.append(lf)
        except ValueError:
            continue

    lines: list[str] = []
    skipped = 0
    search_lower = search.lower() if search else None

    for lf in relevant:
        with open(lf, "r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.rstrip("\n")
                if search_lower:
                    clean = ANSI_RE.sub("", line).lower()
                    if search_lower not in clean:
                        continue
                if skipped < offset:
                    skipped += 1
                    continue
                lines.append(line)
                if len(lines) >= limit:
                    break
        if len(lines) >= limit:
            break

    return {"lines": lines, "has_more": len(lines) >= limit}


# --- WebSocket ---


@app.websocket("/api/ws/{port_id}")
async def websocket_logs(websocket: WebSocket, port_id: str):
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
    loop = asyncio.get_running_loop()

    def on_line(line: str):
        try:
            loop.call_soon_threadsafe(queue.put_nowait, line)
        except asyncio.QueueFull:
            pass

    manager.subscribe(port_id, on_line)
    try:
        while True:
            line = await queue.get()
            await websocket.send_text(line)
    except WebSocketDisconnect:
        pass
    finally:
        manager.unsubscribe(port_id, on_line)


# --- Static frontend (must be last) ---

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
