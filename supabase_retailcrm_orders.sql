-- Выполните в Supabase: SQL Editor → New query → Run
-- Таблица для синхронизации заказов из RetailCRM (скрипт sync_retailcrm_to_supabase.py)

create table if not exists public.retailcrm_orders (
  id bigint primary key,
  external_id text,
  site text,
  number text,
  status text,
  order_type text,
  order_method text,
  first_name text,
  last_name text,
  phone text,
  email text,
  total_sum numeric,
  created_at timestamptz,
  synced_at timestamptz not null default now(),
  payload jsonb not null
);

create index if not exists retailcrm_orders_site_idx on public.retailcrm_orders (site);
create index if not exists retailcrm_orders_status_idx on public.retailcrm_orders (status);
create index if not exists retailcrm_orders_created_at_idx on public.retailcrm_orders (created_at);

comment on table public.retailcrm_orders is 'Заказы, синхронизированные из RetailCRM API v5';

-- Права: сервисный ключ пишет; anon — только чтение для дашборда (при необходимости включите RLS)
grant all on public.retailcrm_orders to service_role;
grant usage on schema public to anon, authenticated;
grant select on public.retailcrm_orders to anon, authenticated;

-- Обновить кэш PostgREST (чтобы API сразу увидел таблицу)
notify pgrst, 'reload schema';
