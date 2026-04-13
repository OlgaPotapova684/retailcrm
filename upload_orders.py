#!/usr/bin/env python3
"""
Загрузка заказов из mock_orders.json в RetailCRM (API v5, orders/create).
Читает ключи из keys.env в той же папке, что и скрипт.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEYS_PATH = ROOT / "keys.env"
MOCK_PATH = ROOT / "mock_orders.json"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    # utf-8-sig — если файл сохранён из Блокнота/Excel с BOM
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        val = v.strip().strip('"').strip("'")
        # убрать невидимые символы из ключа (копипаст из PDF/мессенджера)
        val = "".join(ch for ch in val if ch.isprintable())
        env[k.strip()] = val
    return env


def ssl_context_for(env: dict[str, str]) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    flag = (
        env.get("RETAILCRM_INSECURE_SSL")
        or os.environ.get("RETAILCRM_INSECURE_SSL")
        or ""
    ).strip().lower()
    if flag in ("1", "true", "yes"):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def url_with_api_key(url: str, api_key: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}apiKey={urllib.parse.quote(api_key, safe='')}"


def request_json(
    method: str,
    url: str,
    *,
    api_key: str,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    context: ssl.SSLContext | None = None,
) -> dict:
    full_url = url_with_api_key(url, api_key)
    h = {"X-API-KEY": api_key, "Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(full_url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60, context=context) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body)
        except json.JSONDecodeError:
            raise SystemExit(f"HTTP {e.code}: {body[:500]}") from e
        raise SystemExit(f"HTTP {e.code}: {json.dumps(err, ensure_ascii=False)}") from e
    return json.loads(body) if body else {}


def resolve_site(
    api_base: str, api_key: str, from_env: str, *, context: ssl.SSLContext | None
) -> str:
    if from_env:
        return from_env
    url = f"{api_base.rstrip('/')}/reference/sites"
    r = request_json("GET", url, api_key=api_key, context=context)
    if not r.get("success"):
        raise SystemExit(f"Не удалось получить список сайтов: {r}")
    raw = r.get("sites")
    if raw is None:
        raw = []
    # API может вернуть массив сайтов или объект { "code": { ... } }
    if isinstance(raw, dict):
        if not raw:
            raise SystemExit(
                "В аккаунте нет сайтов. Укажите RETAILCRM_SITE в keys.env "
                "(код магазина: Администрирование → Магазины)."
            )
        first_key = next(iter(raw))
        first_val = raw[first_key]
        if isinstance(first_val, dict) and first_val.get("code"):
            return str(first_val["code"])
        return str(first_key)
    if not raw:
        raise SystemExit(
            "В аккаунте нет сайтов или список пуст. "
            "Укажите RETAILCRM_SITE в keys.env (код магазина из админки)."
        )
    first = raw[0]
    if isinstance(first, dict) and first.get("code"):
        return str(first["code"])
    raise SystemExit(f"Неожиданный формат sites в ответе API: {r!r}")


def reference_as_map(payload) -> dict[str, dict]:
    """Справочник из API: объект { code: {...} } или массив с полем code."""
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return {str(k): v for k, v in payload.items() if isinstance(v, dict)}
    if isinstance(payload, list):
        out: dict[str, dict] = {}
        for x in payload:
            if isinstance(x, dict) and x.get("code"):
                out[str(x["code"])] = x
        return out
    return {}


def resolve_order_catalog(
    api_base: str,
    api_key: str,
    *,
    context: ssl.SSLContext | None,
    env: dict[str, str],
    mock_sample: dict,
) -> tuple[str, str, str]:
    """
    Коды orderType / orderMethod / status под вашу CRM.
    В моке могут быть коды из другого демо (например eshop-individual) — подменяем на существующие.
    """
    ot_env = env.get("RETAILCRM_ORDER_TYPE", "").strip()
    om_env = env.get("RETAILCRM_ORDER_METHOD", "").strip()
    st_env = env.get("RETAILCRM_ORDER_STATUS", "").strip()

    base = api_base.rstrip("/")
    r_ot = request_json("GET", f"{base}/reference/order-types", api_key=api_key, context=context)
    r_om = request_json("GET", f"{base}/reference/order-methods", api_key=api_key, context=context)
    # /reference/statuses без site — с параметром site часто 403
    r_st = request_json("GET", f"{base}/reference/statuses", api_key=api_key, context=context)

    types_m = reference_as_map(r_ot.get("orderTypes"))
    methods_m = reference_as_map(r_om.get("orderMethods"))
    statuses_m = reference_as_map(r_st.get("statuses"))

    pref_t = (mock_sample.get("orderType") or "").strip()
    pref_m = (mock_sample.get("orderMethod") or "").strip()
    pref_s = (mock_sample.get("status") or "").strip()

    if ot_env:
        order_type = ot_env
    elif pref_t in types_m:
        order_type = pref_t
    else:
        order_type = ""
        for code, meta in types_m.items():
            if isinstance(meta, dict) and meta.get("defaultForApi"):
                order_type = code
                break
        if not order_type and types_m:
            order_type = sorted(types_m.keys(), key=lambda c: types_m[c].get("ordering", 999))[0]

    if om_env:
        order_method = om_env
    elif pref_m in methods_m:
        order_method = pref_m
    else:
        order_method = next(
            (x for x in ("shopping-cart", "phone", "landing-page", "one-click") if x in methods_m),
            "",
        )
        if not order_method and methods_m:
            order_method = sorted(methods_m.keys())[0]

    if st_env:
        status = st_env
    elif pref_s in statuses_m:
        status = pref_s
    else:
        status = "new" if "new" in statuses_m else (sorted(statuses_m.keys())[0] if statuses_m else "")

    if not order_type or not order_method or not status:
        raise SystemExit(
            "Не удалось сопоставить справочники заказа. "
            f"types={list(types_m)}, methods={list(methods_m)}, statuses={list(statuses_m)[:5]}..."
        )

    print(
        f"Справочники: orderType={order_type}, orderMethod={order_method}, status={status}",
        flush=True,
    )
    return order_type, order_method, status


def map_items_for_api(items: list) -> list:
    """Минимальная структура позиций для создания заказа без каталога."""
    out = []
    for it in items:
        name = it.get("productName") or it.get("name")
        if not name:
            continue
        out.append(
            {
                "productName": name,
                "quantity": it.get("quantity", 1),
                "initialPrice": it.get("initialPrice", 0),
            }
        )
    return out


def build_order(
    raw: dict,
    external_id: str,
    *,
    order_type: str,
    order_method: str,
    status: str,
) -> dict:
    order = {
        "externalId": external_id,
        "firstName": raw.get("firstName"),
        "lastName": raw.get("lastName"),
        "phone": raw.get("phone"),
        "email": raw.get("email"),
        "orderType": order_type,
        "orderMethod": order_method,
        "status": status,
        "items": map_items_for_api(raw.get("items") or []),
        "customFields": raw.get("customFields") or {},
    }
    if raw.get("delivery"):
        order["delivery"] = raw["delivery"]
    return order


def create_order(
    api_base: str,
    api_key: str,
    site: str,
    order: dict,
    *,
    context: ssl.SSLContext | None,
) -> dict:
    url = f"{api_base.rstrip('/')}/orders/create"
    body = urllib.parse.urlencode(
        {
            "site": site,
            "order": json.dumps(order, ensure_ascii=False),
        }
    ).encode("utf-8")
    return request_json(
        "POST",
        url,
        api_key=api_key,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        context=context,
    )


def main() -> None:
    if not KEYS_PATH.is_file():
        raise SystemExit(f"Нет файла {KEYS_PATH}")
    if not MOCK_PATH.is_file():
        raise SystemExit(f"Нет файла {MOCK_PATH}")

    env = load_env(KEYS_PATH)
    api_base = env.get("RETAILCRM_API_BASE", "").strip().rstrip("/")
    api_key = env.get("RETAILCRM_API_KEY", "").strip()
    site_env = env.get("RETAILCRM_SITE", "").strip()

    if not api_base or not api_key:
        raise SystemExit("В keys.env задайте RETAILCRM_API_BASE и RETAILCRM_API_KEY")

    ctx = ssl_context_for(env)
    orders = json.loads(MOCK_PATH.read_text(encoding="utf-8-sig"))
    if not isinstance(orders, list):
        raise SystemExit("mock_orders.json должен быть массивом заказов")

    site = resolve_site(api_base, api_key, site_env, context=ctx)
    print(f"Магазин (site): {site}", flush=True)

    order_type, order_method, status = resolve_order_catalog(
        api_base,
        api_key,
        context=ctx,
        env=env,
        mock_sample=orders[0] if orders else {},
    )

    ok = 0
    for i, raw in enumerate(orders, start=1):
        ext = f"gbc-mock-{i:04d}"
        payload = build_order(
            raw,
            ext,
            order_type=order_type,
            order_method=order_method,
            status=status,
        )
        r = create_order(api_base, api_key, site, payload, context=ctx)
        if r.get("success"):
            oid = r.get("id")
            print(f"[{i}/{len(orders)}] OK externalId={ext} id={oid}", flush=True)
            ok += 1
        else:
            print(
                f"[{i}/{len(orders)}] FAIL externalId={ext}: {json.dumps(r, ensure_ascii=False)}",
                flush=True,
            )
        time.sleep(0.15)

    print(f"Готово: создано {ok} из {len(orders)}", flush=True)
    if ok < len(orders):
        sys.exit(1)


if __name__ == "__main__":
    main()
