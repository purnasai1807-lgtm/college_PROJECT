# Phase 49 — canteen hours, pause switch, pickup slots, ready alerts, shared throttling

## Canteen hours and the staff pause switch
- `CANTEEN_OPEN_TIME` / `CANTEEN_CLOSE_TIME` (HH:MM, in `CANTEEN_TIMEZONE`, default `Asia/Kolkata`) and `CANTEEN_OPEN_DAYS` (Mon=0 … Sun=6) define when orders are accepted. Leave both times empty to keep the old behaviour: always open, no slots.
- Staff and admins get an **Ordering switch** in the management area to pause/resume ordering with an optional message for students (rush hour, sold out, closing early). It is stored in the database (`app_settings`), recorded in the audit log, and applies to every worker immediately.
- `GET /api/canteen/status` (public) reports whether orders are accepted and why not. Quote and checkout creation return 409 with that message when closed or paused; the cart shows a banner and disables payment.

## Pickup time slots
- With hours configured, `GET /api/canteen/slots` lists today's remaining slots (`PICKUP_SLOT_MINUTES`, default 15; capacity `PICKUP_SLOT_CAPACITY` orders per slot; students cannot pick a time sooner than `PICKUP_MIN_LEAD_MINUTES`).
- Students choose a time in the cart (or "as soon as possible"); the server validates it again at quote and checkout, stores it on the order (`orders.pickup_slot`, UTC), and shows it in order lists. Cancelled and failed-payment orders free their slot.
- Limitation: capacity is checked before payment starts, so two students paying for the last place in a slot at the same moment could both succeed. For a campus pilot this is acceptable; slots are a scheduling aid, not a guarantee.

## Order-ready email
When staff mark an order **ready**, the student also gets an email (`EMAIL_ORDER_READY`, needs the `SMTP_*` settings; in development the email is only logged). In-app notifications are unchanged.
SMS/WhatsApp and browser push are **not** implemented: they need phone numbers and consent from students plus a paid provider account or VAPID keys, which should be decided with the college after the pilot.

## Shared login throttling
Set `REDIS_URL` (docker compose does this) and login / password-reset throttling is stored in Redis, so several app workers share one counter. If Redis is unreachable the app falls back to per-process memory and logs a warning. `/api/metrics` remains per-process.

## Migration
`0015_canteen_hours_slots` adds `app_settings` and `orders.pickup_slot`. Run the Alembic upgrade before starting this version.
