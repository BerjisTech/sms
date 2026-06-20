# Self-hosted SMS Gateway

Send SMS from your own machine using an **Android phone as the modem**. A small
FastAPI server on your computer accepts messages over REST or a CLI, rate-limits
them to avoid carrier spam flags, queues anything over the limit in SQLite, and
forwards each message to the [capcom6 **android-sms-gateway**](https://github.com/capcom6/android-sms-gateway)
app running on the phone in **local server mode**.

No cloud provider, no paid SMS API — single machine + one phone on your LAN.

```
 CLI / REST client ──▶ FastAPI server ──▶ SQLite queue ──▶ worker ──▶ Phone (gateway app) ──▶ SMS
        (basic auth)        (rate limiting + logging)              (HTTP, basic auth)
```

## Features

- `POST /send` REST endpoint **and** a `cli.py send` command.
- Rate limiting: configurable, defaults to **100 messages/day** and **max 1 every 5 s**.
- SQLite-backed queue; over-limit messages are held and sent when the window opens.
- Every send attempt logged (timestamp, recipient, status, error) to a log file and the DB.
- `GET /status`: queue length, messages sent today, remaining daily quota.
- All endpoints protected by HTTP Basic auth. No hardcoded credentials — everything from `.env`.

---

## 1. Phone setup (one-time, manual)

This part is physical and can't be automated:

1. Install the **SMS Gateway** app (capcom6) on the Android phone — from the
   [GitHub releases](https://github.com/capcom6/android-sms-gateway) or Google Play.
2. Open the app and enable **Local server** mode.
3. Note the values it displays: **IP address**, **port** (usually `8080`),
   **username**, and **password**.
4. Keep the phone:
   - on the **same Wi-Fi network** as the computer running this server,
   - **plugged in**, and
   - with battery optimization disabled for the app — background SMS sending
     stops if the phone sleeps or drops off Wi-Fi.

### Finding the phone's local IP

The app shows it on the Local server screen. To double-check from the phone:
**Settings → About phone → Status → IP address**, or **Wi-Fi → (your network) → details**.
It will look like `192.168.1.50`.

---

## 2. Server setup (this machine)

Requires Python 3.10+.

```powershell
# from the project folder (E:\Berjis\Apps\Web\sms)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

(macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`)

### Configure `.env`

Copy the example and fill in the values from the phone app and your own chosen
server credentials:

```powershell
Copy-Item .env.example .env
notepad .env
```

| Variable | Meaning |
| --- | --- |
| `GATEWAY_HOST` / `GATEWAY_PORT` | The phone's LAN IP and port from the app |
| `GATEWAY_USERNAME` / `GATEWAY_PASSWORD` | Local-server credentials shown in the app |
| `SERVER_USERNAME` / `SERVER_PASSWORD` | Basic-auth login **you** pick for this server's API |
| `SERVER_HOST` / `SERVER_PORT` | Where this server listens (default `0.0.0.0:8200`) |
| `RATE_LIMIT_PER_DAY` | Max messages per day (default `100`) |
| `RATE_LIMIT_MIN_INTERVAL_SECONDS` | Min seconds between sends (default `5`) |
| `MAX_ATTEMPTS` | Retries before a message is marked failed (default `3`) |
| `DB_PATH` / `LOG_FILE` | SQLite file and log file paths |

> `.env` is git-ignored. Never commit real credentials.

---

## 3. Run the server

```powershell
python -m app.main
```

It starts on `http://0.0.0.0:8200` (or whatever you set) and launches the
background queue worker. Logs stream to the console and to `LOG_FILE`.

Interactive API docs: `http://127.0.0.1:8200/docs`.

---

## 4. Send a test message

### Via the web UI (easiest)

Open **`http://127.0.0.1:8200/`** in a browser. Sign in with your
`SERVER_USERNAME` / `SERVER_PASSWORD`, then use the page to send messages, watch
the live status (queue length, sent today, remaining quota), and browse recent
messages with their status/errors. It auto-refreshes every 5 seconds.

### Via the CLI

```powershell
python cli.py send +15551234567 "Hello from my self-hosted gateway"
python cli.py status
```

### Via REST

```powershell
curl -u admin:change-this-please http://127.0.0.1:8200/send `
  -H "Content-Type: application/json" `
  -d '{"recipient": "+15551234567", "message": "Hello"}'
```

```bash
# macOS/Linux
curl -u admin:change-this-please http://127.0.0.1:8200/send \
  -H "Content-Type: application/json" \
  -d '{"recipient": "+15551234567", "message": "Hello"}'
```

Check status:

```bash
curl -u admin:change-this-please http://127.0.0.1:8200/status
```

Send a text to your own number first to confirm the whole chain works.

---

## API reference

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/` | none* | Web UI (auth is performed client-side per API call). |
| `POST` | `/send` | Basic | Queue a message. Body: `{"recipient": "+1...", "message": "..."}`. Returns `{id, status, queue_position}`. |
| `GET` | `/status` | Basic | Queue length, sent today, daily limit, remaining quota, min interval. |
| `GET` | `/messages` | Basic | Recent messages (newest first). Query: `?limit=50`. |
| `GET` | `/messages/{id}` | Basic | Full record for one message (status, attempts, error, timestamps). |
| `GET` | `/health` | none | Liveness check. |

### Message lifecycle

`queued` → worker sends when the rate-limit window allows → `sent`. On gateway
errors the message stays `queued` and is retried up to `MAX_ATTEMPTS`, then
becomes `failed`. Both outcomes are written to the `send_log` table and the log file.

---

## Notes & troubleshooting

- **`could not reach gateway`** — phone asleep, off Wi-Fi, wrong `GATEWAY_HOST`,
  or the app's local server is off. Confirm you can open `http://<phone-ip>:8080`
  from this machine's browser.
- **Messages sit in the queue** — expected if you've hit the per-day cap or the
  5-second interval; the worker drains them automatically as the window opens.
  Inspect with `python cli.py status`.
- **401 from the CLI/curl** — `SERVER_USERNAME`/`SERVER_PASSWORD` mismatch.
- The server is intended for a trusted LAN. If you expose it beyond that, put it
  behind HTTPS (e.g. a reverse proxy) — basic auth alone is not enough over the
  open internet.
