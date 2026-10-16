"""Local web service for Markdown conversion."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote
from uuid import UUID
import logging

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.converter import ConversionError, convert_bytes, safe_name
from app.store import ensure_schema, get_conversion, list_conversions, save_conversion

logger = logging.getLogger("mdcreator")
STATIC = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    try:
        ensure_schema()
        app.state.store_ready = True
    except Exception:
        logger.exception("History storage is unavailable")
        app.state.store_ready = False
    yield


app = FastAPI(title="MD Creator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/convert")
async def convert(file: UploadFile = File(...)):
    name = safe_name(file.filename or "upload")
    data = await file.read()
    try:
        result = convert_bytes(name, data)
    except ConversionError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except Exception as exc:
        logger.exception("Conversion failed")
        raise HTTPException(status_code=500, detail="The file could not be converted.") from exc

    body = result.as_dict()
    body["id"] = None
    body["created_at"] = None
    if not app.state.store_ready:
        body["warning"] = _join(body.get("warning"), "History storage is unavailable.")
        return body
    try:
        saved = save_conversion(result)
    except Exception:
        logger.exception("Could not save conversion history")
        body["warning"] = _join(body.get("warning"), "The conversion was not saved to history.")
        return body
    body["id"] = saved["id"]
    body["created_at"] = saved["created_at"]
    return body


@app.get("/api/history")
def history():
    _require_store()
    try:
        return list_conversions()
    except Exception as exc:
        logger.exception("Could not list history")
        raise HTTPException(status_code=503, detail="History storage is unavailable.") from exc


@app.get("/api/history/{conversion_id}")
def history_item(conversion_id: str):
    _require_store()
    row = _load(conversion_id)
    return row


@app.get("/api/history/{conversion_id}/download")
def download(conversion_id: str):
    _require_store()
    row = _load(conversion_id)
    filename = _download_name(row.get("filename") or "document.md")
    ascii_name = "".join(
        char if char.isascii() and char not in '"\\/' else "_" for char in filename
    ) or "document.md"
    disposition = (
        f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
    )
    return PlainTextResponse(
        row.get("markdown") or "",
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )


def _require_store() -> None:
    if not app.state.store_ready:
        raise HTTPException(status_code=503, detail="History storage is unavailable.")


def _load(conversion_id: str) -> dict:
    try:
        parsed = str(UUID(conversion_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown conversion.") from exc
    try:
        row = get_conversion(parsed)
    except Exception as exc:
        logger.exception("Could not load conversion")
        raise HTTPException(status_code=503, detail="History storage is unavailable.") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="That conversion is not in history.")
    return row


def _join(existing: str | None, extra: str) -> str:
    if existing:
        return f"{existing} {extra}"
    return extra


def _download_name(filename: str) -> str:
    stem = Path(filename).stem or "document"
    return f"{stem}.md"
