"""FastAPI application: REST API for the SMS gateway."""

from __future__ import annotations

import asyncio
import logging
import pathlib
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

_STATIC_DIR = pathlib.Path(__file__).parent / "static"

from . import db, rate_limiter, worker
from .auth import require_auth
from .config import Settings, get_settings


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(settings.log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings)
    db.init_db(settings.db_path)

    stop = asyncio.Event()
    task = asyncio.create_task(worker.worker_loop(settings, stop))
    try:
        yield
    finally:
        stop.set()
        await task
        db.close_db()


app = FastAPI(title="Self-hosted SMS Gateway", lifespan=lifespan)


class SendRequest(BaseModel):
    recipient: str = Field(..., description="E.164 phone number, e.g. +15551234567")
    message: str = Field(..., min_length=1)


class SendResponse(BaseModel):
    id: int
    status: str
    queue_position: int


class StatusResponse(BaseModel):
    queue_length: int
    sent_today: int
    daily_limit: int
    remaining_daily_quota: int
    min_interval_seconds: float


@app.post("/send", response_model=SendResponse)
def send(
    req: SendRequest,
    _: str = Depends(require_auth),
    settings: Settings = Depends(get_settings),
) -> SendResponse:
    recipient = req.recipient.strip()
    if not recipient:
        raise HTTPException(status_code=422, detail="recipient is required")

    message_id = db.enqueue(recipient, req.message)
    db.add_log(message_id, recipient, "queued", None)
    return SendResponse(
        id=message_id,
        status="queued",
        queue_position=db.queue_length(),
    )


@app.get("/status", response_model=StatusResponse)
def status(
    _: str = Depends(require_auth),
    settings: Settings = Depends(get_settings),
) -> StatusResponse:
    return StatusResponse(
        queue_length=db.queue_length(),
        sent_today=db.sent_today_count(),
        daily_limit=settings.rate_limit_per_day,
        remaining_daily_quota=rate_limiter.remaining_daily_quota(settings),
        min_interval_seconds=settings.rate_limit_min_interval_seconds,
    )


@app.get("/messages")
def list_messages(
    limit: int = 50,
    _: str = Depends(require_auth),
) -> list[dict]:
    return db.list_messages(limit)


@app.get("/messages/{message_id}")
def get_message(
    message_id: int,
    _: str = Depends(require_auth),
) -> dict:
    msg = db.get_message(message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="message not found")
    return msg


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the web UI. Auth happens client-side per API call."""
    return FileResponse(_STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


def _port_is_free(host: str, port: int) -> bool:
    """True if we can bind host:port right now."""
    import socket

    # 0.0.0.0 binds all interfaces; test that, otherwise the specific host.
    bind_host = "" if host in ("0.0.0.0", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, port))
            return True
        except OSError:
            return False


def run() -> None:
    """Entry point: ``python -m app.main`` or the console use in README."""
    import sys

    import uvicorn

    settings = get_settings()
    if not _port_is_free(settings.server_host, settings.server_port):
        sys.exit(
            f"ERROR: port {settings.server_port} is already in use on "
            f"{settings.server_host}. Set a different SERVER_PORT in .env."
        )

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
    )


if __name__ == "__main__":
    run()
