#!/usr/bin/env python3
"""
Синхронизация заказов: RetailCRM API v5 → Supabase (PostgREST).

Перед первым запуском выполните SQL из supabase_retailcrm_orders.sql в проекте Supabase.

Конфигурация: keys.env (рядом со скриптом):
  RETAILCRM_API_BASE, RETAILCRM_API_KEY, RETAILCRM_SITE (опц.), RETAILCRM_INSECURE_SSL (опц.)
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
  SUPABASE_INSECURE_SSL (опц.) — отключить проверку SSL к Supabase; если пусто, при RETAILCRM_INSECURE_SSL=1
  используется тот же обход (часто нужно на Mac, если нет certifi / Install Certificates).
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from upload_orders import (
    KEYS_PATH,
    load_env,
    request_json,
    resolve_site,
    ssl_context_for,
)

ROOT = Path(__file__).resolve().parent
TABLE = "retailcrm_orders"
PAGE_SIZE = 100


def _env_truthy(env: dict[str, str], name: str) -> bool:
    v = (env.get(name) or os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes")


def https_context_supabase(env: dict[str, str]) -> ssl.SSLContext:
    """SSL для PostgREST: certifi при наличии, иначе обход при флаге (как у RetailCRM на том же Mac)."""
    if _env_truthy(env, "SUPABASE_INSECURE_SSL") or _env_truthy(
        env, "RETAILCRM_INSECURE_SSL"
    ):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi  # type: ignore[import-untyped]

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _parse_num(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(Decimal(str(v).replace(",", ".")))
    except (InvalidOperation, ValueError):
        return None


def _parse_ts(v) -> str | None:
    if not v:
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
        except (OSError, ValueError):
            return None
    s = str(v).strip()
    if not s:
        return None
    # RetailCRM часто отдаёт "Y-m-d H:i:s"
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    if s.endswith("+00:00"):
        return s
    if "+" not in s and not s.endswith("Z"):
        return s + "Z"
    return s


def order_to_row(order: dict) -> dict:
    oid = order.get("id")
    if oid is None:
        raise ValueError("order without id")
    total = _parse_num(order.get("totalSumm"))
    if total is None:
        total = _parse_num(order.get("summ"))
    return {
        "id": int(oid),
        "external_id": order.get("externalId"),
        "site": order.get("site"),
        "number": order.get("number"),
        "status": order.get("status"),
        "order_type": order.get("orderType"),
        "order_method": order.get("orderMethod"),
        "first_name": order.get("firstName"),
        "last_name": order.get("lastName"),
        "phone": order.get("phone"),
        "email": order.get("email"),
        "total_sum": total,
        "created_at": _parse_ts(order.get("createdAt")),
        "payload": order,
    }


def fetch_all_orders(api_base: str, api_key: str, site: str, *, context) -> list[dict]:
    base = api_base.rstrip("/")
    all_orders: list[dict] = []
    page = 1
    while True:
        q = urllib.parse.urlencode(
            {"site": site, "limit": PAGE_SIZE, "page": page},
            safe="",
        )
        url = f"{base}/orders?{q}"
        r = request_json("GET", url, api_key=api_key, context=context)
        if not r.get("success"):
            raise SystemExit(f"RetailCRM orders: {json.dumps(r, ensure_ascii=False)}")
        batch = r.get("orders") or []
        if not batch:
            break
        all_orders.extend(batch)
        pag = r.get("pagination") or {}
        total_pages = pag.get("totalPageCount")
        if total_pages is not None:
            if page >= int(total_pages):
                break
        elif len(batch) < PAGE_SIZE:
            break
        page += 1
        time.sleep(0.12)
    return all_orders


def supabase_upsert(
    env: dict[str, str],
    rows: list[dict],
    *,
    ssl_ctx: ssl.SSLContext,
    chunk: int = 80,
) -> None:
    supa_url = env.get("SUPABASE_URL", "").strip().rstrip("/")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supa_url or not key:
        raise SystemExit(
            "В keys.env задайте SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY "
            "(Settings → API → Project URL и service_role secret)."
        )
    endpoint = f"{supa_url}/rest/v1/{TABLE}"
    for i in range(0, len(rows), chunk):
        part = rows[i : i + chunk]
        body = json.dumps(part, ensure_ascii=False, default=str).encode("utf-8")
        target = f"{endpoint}?on_conflict=id"
        req = urllib.request.Request(
            target,
            data=body,
            method="POST",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal,resolution=merge-duplicates",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120, context=ssl_ctx) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            hint = ""
            if e.code == 404 and "PGRST205" in err and TABLE in err:
                hint = (
                    "\n\n→ Создайте таблицу: Supabase → SQL Editor → выполните скрипт "
                    "supabase_retailcrm_orders.sql из папки проекта, затем снова "
                    "запустите этот скрипт."
                )
            raise SystemExit(f"Supabase HTTP {e.code}: {err[:2000]}{hint}") from e


def main() -> None:
    if not KEYS_PATH.is_file():
        raise SystemExit(f"Нет файла {KEYS_PATH}")

    env = load_env(KEYS_PATH)
    api_base = env.get("RETAILCRM_API_BASE", "").strip().rstrip("/")
    api_key = env.get("RETAILCRM_API_KEY", "").strip()
    site_env = env.get("RETAILCRM_SITE", "").strip()

    if not api_base or not api_key:
        raise SystemExit("В keys.env задайте RETAILCRM_API_BASE и RETAILCRM_API_KEY")

    ctx = ssl_context_for(env)
    site = resolve_site(api_base, api_key, site_env, context=ctx)
    print(f"RetailCRM site={site!r}, забираем заказы…", flush=True)

    orders = fetch_all_orders(api_base, api_key, site, context=ctx)
    print(f"Получено заказов: {len(orders)}", flush=True)

    rows: list[dict] = []
    for o in orders:
        try:
            rows.append(order_to_row(o))
        except ValueError:
            continue

    if not rows:
        print("Нет строк для записи.", flush=True)
        return

    supa_ssl = https_context_supabase(env)
    supabase_upsert(env, rows, ssl_ctx=supa_ssl)
    print(f"Supabase: upsert в {TABLE!r}, строк: {len(rows)}", flush=True)


if __name__ == "__main__":
    main()
