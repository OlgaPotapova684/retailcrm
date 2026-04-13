"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Point = { date: string; count: number; sum: number };
type NamedCount = { name: string; value: number };
type OrderBar = { id: number; label: string; sum: number };

type ApiOk = {
  series: Point[];
  totalOrders: number;
  totalSum: number;
  uniqueDays: number;
  singleDayHint: string | null;
  byStatus: NamedCount[];
  byMethod: NamedCount[];
  byOrderType: NamedCount[];
  ordersBars?: OrderBar[];
};

type ChartMode =
  | "daily"
  | "perOrder"
  | "status"
  | "method"
  | "orderType";

const PIE_COLORS = [
  "#5b8def",
  "#34d399",
  "#fbbf24",
  "#f472b6",
  "#a78bfa",
  "#2dd4bf",
  "#fb923c",
  "#94a3b8",
];

const MODE_OPTIONS: { value: ChartMode; label: string }[] = [
  { value: "perOrder", label: "Каждый заказ — отдельный столбец (сумма)" },
  { value: "daily", label: "По дням — столбцы и сумма линией" },
  { value: "status", label: "По статусу — круговая" },
  { value: "method", label: "По способу оформления — горизонтальные столбцы" },
  { value: "orderType", label: "По типу заказа — горизонтальные столбцы" },
];

const selectStyle: CSSProperties = {
  width: "100%",
  maxWidth: 440,
  padding: "10px 12px",
  borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--bg)",
  color: "var(--text)",
  fontSize: "0.95rem",
  cursor: "pointer",
};

const tooltipStyle = {
  contentStyle: {
    background: "#151a22",
    border: "1px solid #2a3344",
    borderRadius: 8,
  },
  labelStyle: { color: "#e8ecf2" },
};

export function OrdersChart() {
  const [data, setData] = useState<ApiOk | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<ChartMode>("perOrder");

  useEffect(() => {
    if (!data) return;
    const showOt =
      data.byOrderType.length > 1 ||
      (data.byOrderType.length === 1 && data.byOrderType[0].name !== "—");
    if (mode === "orderType" && !showOt) setMode("daily");
  }, [data, mode]);

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
  if (!data || data.totalOrders === 0) {
    return (
      <p style={{ color: "var(--muted)" }}>
        Нет заказов в таблице. Синхронизируйте данные (
        <code>sync_retailcrm_to_supabase.py</code>).
      </p>
    );
  }

  const showOrderTypeChart =
    data.byOrderType.length > 1 ||
    (data.byOrderType.length === 1 && data.byOrderType[0].name !== "—");

  const ordersBars = data.ordersBars ?? [];

  return (
    <>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "0.75rem",
          marginBottom: "1rem",
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
        <div
          style={{
            padding: "0.85rem 1rem",
            background: "var(--bg)",
            borderRadius: 8,
            border: "1px solid var(--border)",
          }}
        >
          <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
            Уникальных дней (агрегация)
          </div>
          <div style={{ fontSize: "1.35rem", fontWeight: 600 }}>
            {data.uniqueDays}
          </div>
        </div>
      </div>

      <div style={{ marginBottom: "1.25rem" }}>
        <label
          htmlFor="chart-mode"
          style={{
            display: "block",
            fontSize: "0.85rem",
            color: "var(--muted)",
            marginBottom: 6,
          }}
        >
          Выберите график
        </label>
        <select
          id="chart-mode"
          value={mode}
          onChange={(e) => setMode(e.target.value as ChartMode)}
          style={selectStyle}
          aria-label="Тип графика"
        >
          {MODE_OPTIONS.filter(
            (o) => o.value !== "orderType" || showOrderTypeChart,
          ).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {mode === "daily" && data.singleDayHint ? (
        <p
          style={{
            margin: "0 0 1rem",
            fontSize: "0.9rem",
            color: "var(--muted)",
          }}
        >
          {data.singleDayHint}
        </p>
      ) : null}

      {mode === "daily" && (
        <>
          {data.series.length > 0 ? (
            <div style={{ width: "100%", height: 380 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={data.series}
                  margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
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
                  <Tooltip {...tooltipStyle} />
                  <Legend />
                  <Bar
                    yAxisId="left"
                    dataKey="count"
                    name="Заказов"
                    fill="#5b8def"
                    radius={[4, 4, 0, 0]}
                    maxBarSize={56}
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
          ) : (
            <p style={{ color: "var(--muted)" }}>
              Нет дат для графика по дням (проверьте{" "}
              <code>created_at</code> / <code>synced_at</code>).
            </p>
          )}
        </>
      )}

      {mode === "perOrder" && ordersBars.length > 0 && (
        <div style={{ width: "100%", height: 440 }}>
          <p
            style={{
              margin: "0 0 0.75rem",
              fontSize: "0.85rem",
              color: "var(--muted)",
            }}
          >
            По оси X — номер заказа или id; высота столбца — сумма заказа. Полоса
            внизу — масштаб (перетаскивание окна).
          </p>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={ordersBars}
              margin={{ top: 8, right: 12, left: 4, bottom: 72 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3344" />
              <XAxis
                dataKey="label"
                tick={{ fill: "#8b95a8", fontSize: 9 }}
                angle={-55}
                textAnchor="end"
                height={68}
                interval={0}
              />
              <YAxis
                tick={{ fill: "#8b95a8", fontSize: 12 }}
                tickLine={false}
              />
              <Tooltip
                {...tooltipStyle}
                formatter={(v: number) => [
                  v.toLocaleString("ru-RU"),
                  "Сумма",
                ]}
                labelFormatter={(_, payload) => {
                  const p = payload?.[0]?.payload as OrderBar | undefined;
                  return p ? `Заказ ${p.label} (id ${p.id})` : "";
                }}
              />
              <Bar
                dataKey="sum"
                name="Сумма заказа"
                fill="#5b8def"
                radius={[3, 3, 0, 0]}
                maxBarSize={32}
              />
              <Brush
                dataKey="label"
                height={22}
                stroke="#5b8def"
                travellerWidth={10}
                tickFormatter={() => ""}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {mode === "perOrder" && ordersBars.length === 0 && (
        <p style={{ color: "var(--muted)" }}>
          Нет данных для графика по заказам. Обновите API и пересоберите
          дашборд.
        </p>
      )}

      {mode === "status" && (
        <div style={{ width: "100%", height: 340 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data.byStatus}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={52}
                outerRadius={96}
                paddingAngle={2}
                label={({ name, percent }) =>
                  `${name} ${((percent ?? 0) * 100).toFixed(0)}%`
                }
              >
                {data.byStatus.map((entry, i) => (
                  <Cell
                    key={`${entry.name}-${i}`}
                    fill={PIE_COLORS[i % PIE_COLORS.length]}
                  />
                ))}
              </Pie>
              <Tooltip {...tooltipStyle} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}

      {mode === "method" && (
        <div
          style={{
            width: "100%",
            height: Math.max(240, data.byMethod.length * 40),
          }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              layout="vertical"
              data={data.byMethod}
              margin={{ top: 4, right: 16, left: 8, bottom: 4 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#2a3344"
                horizontal={false}
              />
              <XAxis
                type="number"
                tick={{ fill: "#8b95a8", fontSize: 12 }}
                allowDecimals={false}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={120}
                tick={{ fill: "#8b95a8", fontSize: 11 }}
              />
              <Tooltip {...tooltipStyle} />
              <Bar
                dataKey="value"
                name="Заказов"
                fill="#a78bfa"
                radius={[0, 4, 4, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {mode === "orderType" && showOrderTypeChart && (
        <div
          style={{
            width: "100%",
            height: Math.max(220, data.byOrderType.length * 44),
          }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              layout="vertical"
              data={data.byOrderType}
              margin={{ top: 4, right: 16, left: 8, bottom: 4 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#2a3344"
                horizontal={false}
              />
              <XAxis
                type="number"
                tick={{ fill: "#8b95a8", fontSize: 12 }}
                allowDecimals={false}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={100}
                tick={{ fill: "#8b95a8", fontSize: 11 }}
              />
              <Tooltip {...tooltipStyle} />
              <Bar
                dataKey="value"
                name="Заказов"
                fill="#2dd4bf"
                radius={[0, 4, 4, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </>
  );
}
