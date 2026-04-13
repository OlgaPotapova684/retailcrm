"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Point = { date: string; count: number; sum: number };

type ApiOk = {
  series: Point[];
  totalOrders: number;
  totalSum: number;
};

export function OrdersChart() {
  const [data, setData] = useState<ApiOk | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/orders");
        const j = await r.json();
        if (!r.ok) {
          throw new Error(j.error || `HTTP ${r.status}`);
        }
        if (!cancelled) setData(j as ApiOk);
      } catch (e) {
        if (!cancelled)
          setErr(e instanceof Error ? e.message : "Ошибка загрузки");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <p style={{ color: "var(--muted)" }}>Загрузка данных из Supabase…</p>
    );
  }
  if (err) {
    return (
      <p style={{ color: "#f87171" }} role="alert">
        {err}
      </p>
    );
  }
  if (!data || data.series.length === 0) {
    return (
      <p style={{ color: "var(--muted)" }}>
        Нет данных для графика. Синхронизируйте заказы (
        <code>sync_retailcrm_to_supabase.py</code>).
      </p>
    );
  }

  return (
    <>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "0.75rem",
          marginBottom: "1.25rem",
        }}
      >
        <div
          style={{
            padding: "0.85rem 1rem",
            background: "var(--bg)",
            borderRadius: 8,
            border: "1px solid var(--border)",
          }}
        >
          <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
            Всего заказов
          </div>
          <div style={{ fontSize: "1.35rem", fontWeight: 600 }}>
            {data.totalOrders}
          </div>
        </div>
        <div
          style={{
            padding: "0.85rem 1rem",
            background: "var(--bg)",
            borderRadius: 8,
            border: "1px solid var(--border)",
          }}
        >
          <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
            Сумма (по строкам)
          </div>
          <div style={{ fontSize: "1.35rem", fontWeight: 600 }}>
            {data.totalSum.toLocaleString("ru-RU")}
          </div>
        </div>
      </div>
      <div style={{ width: "100%", height: 420 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data.series}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#2a3344" />
            <XAxis
              dataKey="date"
              tick={{ fill: "#8b95a8", fontSize: 12 }}
              tickLine={false}
            />
            <YAxis
              yAxisId="left"
              tick={{ fill: "#8b95a8", fontSize: 12 }}
              tickLine={false}
              allowDecimals={false}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fill: "#8b95a8", fontSize: 12 }}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "#151a22",
                border: "1px solid #2a3344",
                borderRadius: 8,
              }}
              labelStyle={{ color: "#e8ecf2" }}
            />
            <Legend />
            <Bar
              yAxisId="left"
              dataKey="count"
              name="Заказов"
              fill="#5b8def"
              radius={[4, 4, 0, 0]}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="sum"
              name="Сумма"
              stroke="#34d399"
              strokeWidth={2}
              dot={{ r: 3 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}
