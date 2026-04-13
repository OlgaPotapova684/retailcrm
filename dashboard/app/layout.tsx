import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Заказы — RetailCRM → Supabase",
  description: "Дашборд заказов из Supabase",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
