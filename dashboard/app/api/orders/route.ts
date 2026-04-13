import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

type Row = {
  id: number;
  created_at: string | null;
  synced_at: string | null;
  total_sum: number | string | null;
};

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
          "Задайте SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY (серверные переменные, не в браузер).",
      },
      { status: 500 },
    );
  }

  const url = `${base}/rest/v1/retailcrm_orders?select=id,created_at,synced_at,total_sum`;
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
      { status: 502 },
    );
  }

  const rows = (await res.json()) as Row[];
  const byDay = new Map<
    string,
    { count: number; sum: number }
  >();

  for (const r of rows) {
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

  return NextResponse.json({
    series,
    totalOrders: rows.length,
    totalSum: Math.round(totalSum * 100) / 100,
  });
}
