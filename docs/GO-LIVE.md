# ACE Canteen — go-live guide

This is the practical path from "it runs on my laptop" to "students use it". Do the steps in order and
do not skip the pilot.

## 0. Decide the basics
- **Who owns the money?** Razorpay needs a business/KYC account (college, trust or canteen contractor). Start this first; approval can take days.
- **Where does it run?** A small Linux VPS (1 GB RAM is enough for a pilot) with Docker, or any host that can run the `Dockerfile` plus managed PostgreSQL.
- **Domain + email.** A domain/subdomain (e.g. `canteen.your-college.edu`) and an SMTP account for password-reset emails.

## 1. Prepare the server
```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 nginx certbot python3-certbot-nginx git
git clone <your repo> ace-canteen && cd ace-canteen
cp .env.production.example .env      # then fill in every value
python3 scripts/deployment_preflight.py            # must show no errors
```
Use `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` for `SECRET_KEY` and `METRICS_TOKEN`.

## 2. Start the stack
```bash
docker compose --profile ops run --rm migrate      # creates/updates the database schema (Alembic)
docker compose up -d --build app db
docker compose run --rm app python -m app.create_admin --email you@college.edu --name "Canteen Admin"
curl -s http://127.0.0.1:8000/api/ready
```
Create the admin first, then sign in at the site and add staff from **Staff & permissions**. New staff must
change their temporary password at first sign-in (enforced by the server).

## 3. HTTPS
Copy `deploy/nginx-https-example.conf` to `/etc/nginx/sites-available/`, replace the hostname, enable it, then
`sudo certbot --nginx -d canteen.your-college.edu`. Confirm `https://…/api/ready` works and set
`HTTPS_TERMINATED=true` in `.env` only after that.

## 4. Payments (Razorpay)
1. Put **test** keys in `.env` and restart `app`.
2. In the Razorpay dashboard add a webhook: `https://canteen.your-college.edu/api/payments/webhook`, event `payment.captured` (and failures), with the same secret as `RAZORPAY_WEBHOOK_SECRET`.
3. Test: a successful payment, a failed payment, closing the browser mid-payment, and a repeated webhook delivery. Check each order in **Admin → Orders**.
4. Only after the pilot, swap to live keys.
5. The app has **no refunds by design**. Decide who handles a wrong charge (via the Razorpay dashboard) and publish that policy where students see it before paying.

## 5. Email (password reset)
Fill the `SMTP_*` variables, restart, then use **Forgot your password?** with a real address. Check the spam folder.
If email is not set up, students cannot recover accounts — the preflight reports this as a warning.

## 6. Real data
Replace the demo menu: add real categories and items, prices, photos and stock in the management area.
`SEED_DEMO_DATA` must stay `false` in production.

## 7. Backups
```bash
./scripts/backup_db.sh                 # run from cron daily, copy the file OFF the server
```
Restore it once into a scratch database before launch. A backup you have never restored is not a backup.

## 8. Monitoring
Point a free uptime checker (UptimeRobot, Better Stack) at `https://…/api/ready`. Watch `docker compose logs -f app`.

## 9. Pilot (1 week)
One counter, 10–20 students, the canteen staff. Check: ordering on a phone, payment, token on the pickup board,
kitchen flow, stock going down, daily report matching Razorpay's settlement. Fix what breaks, then open to everyone.

## Known limits (be honest with the college)
- Login throttling and metrics live in process memory, so run **one** app worker (the Dockerfile does).
- Order updates use 15-second polling, not push.
- No automated test has run against live Razorpay or a real phone yet — the pilot is that test.
