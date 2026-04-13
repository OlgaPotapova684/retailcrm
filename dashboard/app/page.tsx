import { OrdersChart } from "./OrdersChart";

export default function Home() {
  return (
    <main
      style={{
        maxWidth: 960,
        margin: "0 auto",
        padding: "2.5rem 1.25rem 4rem",
      }}
    >
      <header style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.75rem", fontWeight: 600, margin: "0 0 0.5rem" }}>
          Заказы по дням
        </h1>
        <p style={{ margin: 0, color: "var(--muted)", fontSize: "0.95rem" }}>
          Данные из таблицы <code>retailcrm_orders</code> в Supabase (синхронизация
          из RetailCRM).
        </p>
      </header>

      <section
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          padding: "1.25rem 1rem 1.5rem",
        }}
      >
        <OrdersChart />
      </section>
    </main>
  );
}
