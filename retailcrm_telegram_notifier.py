#!/usr/bin/env python3
"""
Уведомления в Telegram, если в RetailCRM появился заказ > порога.

Как работает:
- Скрипт периодически опрашивает /api/v5/orders (страницами, отсортировано по id desc по умолчанию)
- Берёт только новые заказы (id > last_seen_id из state/telegram_notifier.json)
- Для заказов с totalSumm >= TELEGRAM_MIN_SUM_KZT отправляет сообщение в Telegram
- После успешной обработки сохраняет last_seen_id

Настройки (keys.env рядом с проектом):
  RETAILCRM_API_BASE, RETAILCRM_API_KEY, RETAILCRM_SITE (опц.), RETAILCRM_INSECURE_SSL (опц.)
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  TELEGRAM_MIN_SUM_KZT (опц., по умолчанию 50000)
  TELEGRAM_POLL_SECONDS (опц., по умолчанию 30)
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import ssl
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from upload_orders import KEYS_PATH, load_env, request_json, resolve_site, ssl_context_for

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state" / "telegram_notifier.json"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"last_seen_id": 0}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"last_seen_id": 0}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_int(v, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def as_float(v, default: float) -> float:
    try:
        return float(str(v).replace(",", ".").strip())
    except Exception:
        return default


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def fetch_new_orders(
    *,
    api_base: str,
    api_key: str,
    site: str,
    context,
    last_seen_id: int,
    limit: int = 100,
) -> list[dict]:
    """
    Возвращает новые заказы (id > last_seen_id), от старых к новым.
    """
    if limit not in (20, 50, 100):
        limit = 100
    base = api_base.rstrip("/")
    page = 1
    found: list[dict] = []

    while True:
        q = urllib.parse.urlencode({"site": site, "limit": limit, "page": page})
        url = f"{base}/orders?{q}"
        r = request_json("GET", url, api_key=api_key, context=context)
        if not r.get("success"):
            raise SystemExit(f"RetailCRM orders error: {json.dumps(r, ensure_ascii=False)}")
        batch = r.get("orders") or []
        if not batch:
            break

        # batch идёт по id desc. Сохраняем только новые.
        for o in batch:
            oid = o.get("id")
            if oid is None:
                continue
            if int(oid) > last_seen_id:
                found.append(o)

        # если в этой странице все id <= last_seen_id — дальше только старее
        try:
            min_id = min(int(o.get("id")) for o in batch if o.get("id") is not None)
        except ValueError:
            min_id = last_seen_id
        if min_id <= last_seen_id:
            break

        pag = r.get("pagination") or {}
        total_pages = pag.get("totalPageCount")
        if total_pages is not None and page >= int(total_pages):
            break
        page += 1
        time.sleep(0.12)

    # чтобы уведомления были по порядку появления
    found.sort(key=lambda o: int(o.get("id", 0)))
    return found


def send_telegram(
    *,
    api_base: str,
    token: str,
    chat_id: str,
    text: str,
    ssl_ctx: ssl.SSLContext | None,
) -> None:
    url = f"{api_base.rstrip('/')}/bot{token}/sendMessage"
    body = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
    )
    attempt = 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(body_txt) if body_txt else {}
            except json.JSONDecodeError:
                body = {"raw": body_txt}
            if e.code == 429 and attempt <= 5:
                retry_after = 3
                if isinstance(body, dict):
                    retry_after = int(
                        body.get("parameters", {}).get("retry_after", retry_after)
                    )
                time.sleep(max(1, retry_after))
                continue
            raise SystemExit(f"Telegram HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise SystemExit(
                "Не удалось подключиться к Telegram Bot API. "
                "Похоже на DNS/сеть (например, api.telegram.org не резолвится). "
                "Проверьте на Mac: `nslookup api.telegram.org` / DNS / VPN. "
                f"Текст ошибки: {e!r}. "
                "Также можно задать TELEGRAM_API_BASE в keys.env или TELEGRAM_INSECURE_SSL=1."
            ) from e

        if not payload.get("ok"):
            raise SystemExit(f"Telegram API error: {payload}")
        return


def env_truthy(env: dict[str, str], name: str) -> bool:
    v = (env.get(name) or "").strip().lower()
    return v in ("1", "true", "yes")


def ssl_context_telegram(env: dict[str, str]) -> ssl.SSLContext:
    if env_truthy(env, "TELEGRAM_INSECURE_SSL"):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi  # type: ignore[import-untyped]

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def parse_created_date(created_at: str | None) -> date | None:
    if not created_at:
        return None
    s = str(created_at).strip()
    if not s:
        return None
    # RetailCRM: "YYYY-MM-DD HH:MM:SS"
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.fromisoformat(s + "+00:00")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.date()


def filter_orders_by_date(orders: list[dict], d: date) -> list[dict]:
    out: list[dict] = []
    for o in orders:
        cd = parse_created_date(o.get("createdAt"))
        if cd == d:
            out.append(o)
    return out


def fmt_money_kzt(amount) -> str:
    try:
        n = float(amount)
    except Exception:
        return str(amount)
    # без копеек, как правило, для ₸
    return f"{int(round(n)):,}".replace(",", " ")


def order_one_line(o: dict) -> str:
    oid = int(o.get("id", 0))
    number = o.get("number") or f"#{oid}"
    created = (o.get("createdAt") or "").replace("<", "").replace(">", "")
    status = o.get("status") or ""
    total = o.get("totalSumm")
    try:
        total_f = float(str(total).replace(",", "."))
    except Exception:
        total_f = 0.0
    return f"• <b>{number}</b> (id {oid}) — <b>{fmt_money_kzt(total_f)} ₸</b> — <code>{status}</code> — <code>{created}</code>"


def main() -> None:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument(
        "--yesterday",
        action="store_true",
        help="Разово отправить уведомления по всем вчерашним заказам > порога (без цикла).",
    )
    ap.add_argument(
        "--once",
        action="store_true",
        help="Один проход: проверить новые заказы и выйти (без бесконечного цикла).",
    )
    args = ap.parse_args()

    if not KEYS_PATH.is_file():
        raise SystemExit(f"Нет файла {KEYS_PATH}")

    env = load_env(KEYS_PATH)
    api_base = env.get("RETAILCRM_API_BASE", "").strip().rstrip("/")
    api_key = env.get("RETAILCRM_API_KEY", "").strip()
    site_env = env.get("RETAILCRM_SITE", "").strip()

    tg_token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = env.get("TELEGRAM_CHAT_ID", "").strip()
    tg_api_base = (env.get("TELEGRAM_API_BASE") or "https://api.telegram.org").strip()
    tg_ssl = ssl_context_telegram(env)

    threshold = as_float(env.get("TELEGRAM_MIN_SUM_KZT"), 50000.0)
    poll_seconds = as_int(env.get("TELEGRAM_POLL_SECONDS"), 30)

    if not api_base or not api_key:
        raise SystemExit("В keys.env задайте RETAILCRM_API_BASE и RETAILCRM_API_KEY")
    if not tg_token or not tg_chat:
        raise SystemExit("В keys.env задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID")

    ctx = ssl_context_for(env)
    site = resolve_site(api_base, api_key, site_env, context=ctx)
    print(f"RetailCRM site={site!r}, порог={threshold} ₸, poll={poll_seconds}s", flush=True)

    state = load_state()
    last_seen_id = as_int(state.get("last_seen_id"), 0)
    print(f"State last_seen_id={last_seen_id}", flush=True)

    def handle_orders(orders: list[dict]) -> tuple[int, int]:
        nonlocal last_seen_id
        max_seen_this_round = last_seen_id
        sent = 0
        for o in orders:
            oid = int(o.get("id", 0))
            max_seen_this_round = max(max_seen_this_round, oid)

            total = o.get("totalSumm")
            try:
                total_f = float(str(total).replace(",", "."))
            except Exception:
                total_f = 0.0
            if total_f < threshold:
                continue

            number = o.get("number") or f"#{oid}"
            created = o.get("createdAt") or ""
            status = o.get("status") or ""
            first = (o.get("firstName") or "").strip()
            last = (o.get("lastName") or "").strip()
            phone = (o.get("phone") or "").strip()

            who = " ".join(x for x in [first, last] if x) or "Без имени"
            msg = (
                f"<b>Заказ &gt; {fmt_money_kzt(threshold)} ₸</b>\n"
                f"<b>{number}</b> (id {oid})\n"
                f"Сумма: <b>{fmt_money_kzt(total_f)} ₸</b>\n"
                f"Статус: <code>{status}</code>\n"
                f"Создан: <code>{created}</code>\n"
                f"Клиент: {who}\n"
                + (f"Тел: <code>{phone}</code>\n" if phone else "")
                + f"Site: <code>{site}</code>\n"
            )

            send_telegram(
                api_base=tg_api_base,
                token=tg_token,
                chat_id=tg_chat,
                text=msg,
                ssl_ctx=tg_ssl,
            )
            sent += 1
            time.sleep(0.35)

        if max_seen_this_round > last_seen_id:
            last_seen_id = max_seen_this_round
            state["last_seen_id"] = last_seen_id
            state["updatedAt"] = now_iso()
            save_state(state)
        return sent, last_seen_id

    if args.yesterday:
        # забираем последние страницы, пока не упремся в "позавчера"
        y = (datetime.now(tz=timezone.utc) - timedelta(days=1)).date()
        print(f"Backfill: дата={y.isoformat()}", flush=True)
        # для backfill игнорируем last_seen_id и берём всё "сверху", фильтруем по createdAt
        page = 1
        collected: list[dict] = []
        while True:
            q = urllib.parse.urlencode({"site": site, "limit": 100, "page": page})
            url = f"{api_base.rstrip('/')}/orders?{q}"
            r = request_json("GET", url, api_key=api_key, context=ctx)
            if not r.get("success"):
                raise SystemExit(f"RetailCRM orders error: {json.dumps(r, ensure_ascii=False)}")
            batch = r.get("orders") or []
            if not batch:
                break
            # отфильтруем вчерашние
            y_orders = filter_orders_by_date(batch, y)
            collected.extend(y_orders)
            # если самые старые в странице уже < вчера — можно остановиться
            dates = [parse_created_date(o.get("createdAt")) for o in batch]
            dates = [d for d in dates if d is not None]
            if dates and min(dates) < y:
                break
            page += 1
            time.sleep(0.12)

        # оставим только те, что >= threshold
        big: list[dict] = []
        for o in collected:
            try:
                total_f = float(str(o.get("totalSumm")).replace(",", "."))
            except Exception:
                total_f = 0.0
            if total_f >= threshold:
                big.append(o)
        big.sort(key=lambda o: int(o.get("id", 0)))

        print(f"Найдено вчерашних заказов: {len(collected)}, больших: {len(big)}", flush=True)
        if not big:
            return

        header = f"<b>Вчерашние заказы &gt; {fmt_money_kzt(threshold)} ₸</b>\nДата: <code>{y.isoformat()}</code>\nВсего: <b>{len(big)}</b>\n\n"
        lines = [order_one_line(o) for o in big]

        # Telegram лимит ~4096 символов; отправим чанками
        chunk: list[str] = []
        cur_len = len(header)
        sent_msgs = 0
        for ln in lines:
            if cur_len + len(ln) + 1 > 3600 and chunk:
                send_telegram(
                    api_base=tg_api_base,
                    token=tg_token,
                    chat_id=tg_chat,
                    text=header + "\n".join(chunk),
                    ssl_ctx=tg_ssl,
                )
                sent_msgs += 1
                time.sleep(1.0)
                chunk = []
                cur_len = len(header)
            chunk.append(ln)
            cur_len += len(ln) + 1
        if chunk:
            send_telegram(
                api_base=tg_api_base,
                token=tg_token,
                chat_id=tg_chat,
                text=header + "\n".join(chunk),
                ssl_ctx=tg_ssl,
            )
            sent_msgs += 1

        print(f"Отправлено сообщений: {sent_msgs}", flush=True)
        return

    while True:
        new_orders = fetch_new_orders(
            api_base=api_base,
            api_key=api_key,
            site=site,
            context=ctx,
            last_seen_id=last_seen_id,
        )

        sent, last_seen_id = handle_orders(new_orders)
        if sent:
            print(f"[{now_iso()}] sent={sent}, last_seen_id={last_seen_id}", flush=True)

        if args.once:
            return
        time.sleep(max(5, poll_seconds))


if __name__ == "__main__":
    main()

