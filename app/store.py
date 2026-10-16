"""Conversion history in Supabase.

The table is created with the database role. Rows are written with the
secret key, and the browser never receives that key.
"""

from __future__ import annotations

from typing import Any

import psycopg

from app.config import env
from app.converter import Conversion

SCHEMA = """
create table if not exists public.conversions (
    id uuid primary key default gen_random_uuid(),
    filename text not null,
    extension text,
    source_tokens integer,
    markdown_tokens integer not null,
    savings_pct numeric,
    markdown text not null,
    warning text,
    created_at timestamptz not null default now()
);
create index if not exists conversions_created_at_idx
    on public.conversions (created_at desc);
alter table public.conversions enable row level security;
"""

_CLIENT = None


def ensure_schema() -> None:
    url = env("SUPABASE_DATABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_DATABASE_URL is not set.")
    with psycopg.connect(url, prepare_threshold=None, connect_timeout=20, autocommit=True) as conn:
        conn.execute(SCHEMA)


def _client():
    global _CLIENT
    if _CLIENT is None:
        url = env("SUPABASE_URL")
        key = env("SUPABASE_SECRET_KEY")
        if not url or not key:
            raise RuntimeError("Supabase URL or secret key is not set.")
        from supabase import create_client

        _CLIENT = create_client(url, key)
    return _CLIENT


def save_conversion(result: Conversion) -> dict[str, Any]:
    payload = {
        "filename": result.filename,
        "extension": result.extension,
        "source_tokens": result.source_tokens,
        "markdown_tokens": result.markdown_tokens,
        "savings_pct": result.savings_pct,
        "markdown": result.markdown,
        "warning": result.warning,
    }
    response = _client().table("conversions").insert(payload).execute()
    rows = response.data or []
    if not rows:
        raise RuntimeError("Supabase did not return the saved conversion.")
    return _normalize(rows[0])


def list_conversions(limit: int = 50) -> list[dict[str, Any]]:
    response = (
        _client()
        .table("conversions")
        .select(
            "id,filename,extension,source_tokens,markdown_tokens,savings_pct,warning,created_at"
        )
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [_normalize(row) for row in response.data or []]


def get_conversion(conversion_id: str) -> dict[str, Any] | None:
    response = (
        _client()
        .table("conversions")
        .select(
            "id,filename,extension,source_tokens,markdown_tokens,savings_pct,markdown,warning,created_at"
        )
        .eq("id", conversion_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return None
    return _normalize(rows[0])


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    savings = row.get("savings_pct")
    source = row.get("source_tokens")
    markdown_tokens = row.get("markdown_tokens")
    return {
        "id": str(row["id"]),
        "filename": row.get("filename"),
        "extension": row.get("extension"),
        "source_tokens": int(source) if source is not None else None,
        "markdown_tokens": int(markdown_tokens) if markdown_tokens is not None else None,
        "savings_pct": float(savings) if savings is not None else None,
        "markdown": row.get("markdown"),
        "warning": row.get("warning"),
        "created_at": row.get("created_at"),
    }
