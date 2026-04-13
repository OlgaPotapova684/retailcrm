import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const JSON_UTF8 = { "Content-Type": "application/json; charset=utf-8" };

type Row = {
  id: number;
  number: string | null;
  created_at: string | null;
  synced_at: string | null;
  total_sum: number | string | null;
  status: string | null;
  order_method: string | null;
  order_type: string | null;
  site: string | null;
};

function rowSum(r: Row): number {
  const s = r.total_sum;
  const n =
    typeof s === "number"
      ? s
      : s != null
        ? parseFloat(String(s).replace(",", "."))
        : 0;
  return Number.isNaN(n) ? 0 : n;
}

function dayKey(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString().slice(0, 10);
}

export async function GET() {
  const base = process.env.SUPABASE_URL?.replace(/\/$/, "");
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!base || !key) {
    return NextResponse.json(
      {
        error:
          "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in Vercel → Settings → Environment Variables (Production), then Redeploy. / Задайте эти переменные в настройках Vercel и выполните Redeploy.",
        hint:
          "Names must match exactly: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (no NEXT_PUBLIC_ prefix).",
      },
      { status: 500, headers: JSON_UTF8 },
    );
  }

  const url = `${base}/rest/v1/retailcrm_orders?select=id,number,created_at,synced_at,total_sum,status,order_method,order_type,site`;
  const res = await fetch(url, {
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      Accept: "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text();
    return NextResponse.json(
      { error: `Supabase ${res.status}: ${text.slice(0, 500)}` },
      { status: 502, headers: JSON_UTF8 },
    );
  }

  const rows = (await res.json()) as Row[];
  const byDay = new Map<
    string,
    { count: number; sum: number }
  >();

  const bump = (m: Map<string, number>, key: string) => {
    const k = key.trim() || "—";
    m.set(k, (m.get(k) ?? 0) + 1);
  };
  const byStatus = new Map<string, number>();
  const byMethod = new Map<string, number>();
  const byType = new Map<string, number>();

  for (const r of rows) {
    bump(byStatus, r.status ?? "—");
    bump(byMethod, r.order_method ?? "—");
    bump(byType, r.order_type ?? "—");

    const dk = dayKey(r.created_at) ?? dayKey(r.synced_at);
    if (!dk) continue;
    const cur = byDay.get(dk) ?? { count: 0, sum: 0 };
    cur.count += 1;
    const s = r.total_sum;
    const n =
      typeof s === "number"
        ? s
        : s != null
          ? parseFloat(String(s).replace(",", "."))
          : 0;
    if (!Number.isNaN(n)) cur.sum += n;
    byDay.set(dk, cur);
  }

  const series = [...byDay.entries()]
    .map(([date, v]) => ({
      date,
      count: v.count,
      sum: Math.round(v.sum * 100) / 100,
    }))
    .sort((a, b) => a.date.localeCompare(b.date));

  const totalSum = series.reduce((a, b) => a + b.sum, 0);

  const ordersBars = [...rows]
    .sort((a, b) => a.id - b.id)
    .map((r) => {
      const sum = Math.round(rowSum(r) * 100) / 100;
      const num = r.number?.trim();
      const label = num ? num.slice(0, 16) : `#${r.id}`;
      return { id: r.id, label, sum };
    });

  const seen = new Set<string>();
  for (const o of ordersBars) {
    let L = o.label;
    if (seen.has(L)) L = `${o.label} (${o.id})`;
    seen.add(L);
    o.label = L;
  }

  const toSortedList = (m: Map<string, number>) =>
    [...m.entries()]
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);

  return NextResponse.json(
    {
      series,
      totalOrders: rows.length,
      totalSum: Math.round(totalSum * 100) / 100,
      uniqueDays: series.length,
      singleDayHint:
        series.length === 1
          ? "Все заказы попали в одну дату по полю дня — столбец один. Ниже срезы по статусу и способу оформления."
          : null,
      byStatus: toSortedList(byStatus),
      byMethod: toSortedList(byMethod),
      byOrderType: toSortedList(byType),
      ordersBars,
    },
    { headers: JSON_UTF8 },
  );
}
