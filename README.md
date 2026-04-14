# RetailCRM → Supabase → Dashboard (+ Telegram alerts)

Мини‑проект из тестового задания:

- **RetailCRM**: загрузка мок‑заказов и чтение заказов через API v5
- **Supabase**: хранение заказов в таблице `public.retailcrm_orders`
- **Dashboard (Next.js + Recharts)**: графики по заказам из Supabase (деплой на Vercel)
- **Telegram**: уведомления при заказе \(≥ 50 000 ₸\)

## Структура

- `mock_orders.json` — исходный мок (50 заказов)
- `upload_orders.py` — загрузка моков в RetailCRM (`POST /api/v5/orders/create`)
- `supabase_retailcrm_orders.sql` — SQL для создания таблицы в Supabase
- `sync_retailcrm_to_supabase.py` — синхронизация RetailCRM → Supabase (upsert по `id`)
- `dashboard/` — Next.js дашборд (Vercel Root Directory = `dashboard`)
- `retailcrm_telegram_notifier.py` — Telegram‑уведомления по новым/вчерашним заказам
- `keys.env` — **локальный файл с ключами** (в `.gitignore`, не коммитится)
- `state/telegram_notifier.json` — локальное состояние для Telegram‑скрипта (в `.gitignore`)

## Быстрый старт (локально)

1. Заполните `keys.env` (смотри `keys.env.example`).
2. Загрузить мок‑заказы в RetailCRM:

```bash
python3 upload_orders.py
```

3. Создайте таблицу в Supabase:

- Supabase → SQL Editor → выполнить `supabase_retailcrm_orders.sql`

4. Синхронизировать заказы в Supabase:

```bash
python3 sync_retailcrm_to_supabase.py
```

5. Запустить дашборд:

```bash
cd dashboard
npm install
cp .env.example .env.local
# заполните .env.local
npm run dev
```

## Деплой на Vercel (дашборд)

1. Импортируйте репозиторий в Vercel.
2. **Root Directory**: `dashboard`
3. Environment Variables (Production):
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`

## Telegram‑уведомления

### В реальном времени

```bash
python3 retailcrm_telegram_notifier.py
```

### Разовая отправка «за вчера» (≥ порога)

```bash
python3 retailcrm_telegram_notifier.py --yesterday
```

## Безопасность

- **Не коммитьте** `keys.env`, `.env*` и `state/` — они в `.gitignore`.
- Ключи `service_role` и Telegram Bot Token — секреты; хранить только в локальном `keys.env` и в Vercel Env Vars.

## Как я работала с Cursor (промпты + где застряла)

Ниже — краткий лог того, **какие запросы я давала Cursor** и **какие проблемы всплыли** в процессе (и как я их закрыла).

### Промпты, которые давала

- «Есть `mock_orders.json` — загрузи 50 заказов в RetailCRM через API. Дай не более одного шага за раз. Создай необходимые файлы и отдельный файл для ключей».
- «Ключ внесла. Что дальше?»
- «Напиши скрипт, который забирает заказы из RetailCRM API и кладёт в Supabase».
- «Сделай веб‑страницу с графиком заказов (данные из Supabase) и задеплой на Vercel».
- «Сделай уведомление в Telegram, когда в RetailCRM появляется заказ на сумму больше 50 000 ₸».

### Где я застряла (и что в итоге сделала)

- **API‑ключ RetailCRM**: сначала получала `403 Wrong "apiKey" value`.
  - **Решение**: проверила соответствие *ключ ↔ домен аккаунта*, пересоздала ключ в админке RetailCRM и перепроверила тестовым запросом к `GET /api/v5/reference/sites`.

- **SSL на Mac (CERTIFICATE_VERIFY_FAILED)**: Python не доверял цепочке сертификатов.
  - **Решение**: добавила флаги `*_INSECURE_SSL=1` как временный обход для локальной разработки. (Для «боевого» варианта лучше поставить корректные CA в систему/pyenv.)

- **Справочники RetailCRM**: мок содержал `orderType=eshop-individual`, а в демо‑аккаунте такого типа не было → `400 "OrderType ... does not exist"`.
  - **Решение**: подтянула справочники через `GET /reference/order-types`, `GET /reference/order-methods`, `GET /reference/statuses` и сделала автоподбор валидных кодов (`main`, `shopping-cart`, `new`).

- **Supabase / PostgREST (PGRST205)**: `404 Could not find the table ... in the schema cache`.
  - **Решение**: вынесла DDL в `supabase_retailcrm_orders.sql`, добавила `notify pgrst, 'reload schema';` и после выполнения SQL таблица стала доступна через REST.

- **Vercel env vars и кодировка JSON**: на `/api/orders` ловила 500 из‑за отсутствия `SUPABASE_URL` и `SUPABASE_SERVICE_ROLE_KEY`, а русские ошибки отображались «кракозябрами».
  - **Решение**: прописала env vars в Vercel (Production) + сделала `Redeploy`; в API‑роуте добавила `Content-Type: application/json; charset=utf-8`.

- **График выглядел как «прямоугольник»**: все заказы оказались в одном дне → один широкий столбец.
  - **Решение**: добавила переключатель графиков и более информативные срезы (по статусам, по способам оформления), а также режим «каждый заказ — отдельный столбец».

- **Telegram лимиты/ошибки сети**: ловила сетевые ошибки и `429 Too Many Requests` при массовой отправке.
  - **Решение**: добавила обработку `429` (retry_after) и режим `--yesterday`, который отправляет **сводку** по вчерашним крупным заказам (вместо 50 отдельных сообщений).

### Вопросы, на которые пришлось ответить по пути

1. **Почему /api/orders на Vercel «вечно грузится»?**
   - Потому что серверные переменные не применяются к уже собранному билду — нужен Redeploy.

2. **Почему Supabase URL в браузере отвечает `{\"error\":\"requested path is invalid\"}`?**
   - Потому что `https://<ref>.supabase.co/` — это API‑хост, а не «сайт». Смотреть нужно Vercel‑домен, а Supabase URL хранить только в env vars.

