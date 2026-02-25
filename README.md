# ServiceInbox Lite — AI-Powered Service Triage for Insurance Producers

A standalone tool that ingests your service emails/SMS, classifies them by intent, and delivers organized digest work packets so you know exactly what needs to be done each morning.

**$9.99/mo per producer** — no AMS integration required.

## Quick Start

```bash
# 1. Clone and enter the project
cd serviceinbox

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -e .

# 4. Create your .env (copy from example)
cp .env.example .env
# Edit .env with your credentials (optional for demo mode)

# 5. Run the server
make server
# Or: uvicorn app.main:app --reload --port 8000

# 6. Open http://localhost:8000 — click "Load Seeds" to populate demo data
```

## What It Does

1. **Connect your inbox** — point your agency email at ServiceInbox (IMAP) or forward SMS via Twilio
2. **Auto-triage** — every inbound message is classified, scored, and prepped
3. **Digest delivery** — 2-3x daily, get a formatted work packet:
   > "You have 4 COIs, 2 endorsements, 1 address change — all prepped and ready"
4. **Review & send** — approve drafts with one click, or edit before sending

## Features

- **Classify** intent: COI, vehicle add, driver add, address change, payroll change, coverage change
- **Extract** entities: customer name, policy number, VIN, dates, addresses, amounts
- **Score** urgency (0-100) and confidence (0-100) for triage prioritization
- **Detect** missing required information per intent category
- **Generate** draft replies: client reply, carrier email, AMS note
- **Digest** organized work packets grouped by category, delivered on schedule
- **Dashboard** at-a-glance stats: urgent items, pending review, category breakdown
- **Review** in a web UI with filters, Approve / Edit / Reject workflow
- **Send** outbound emails (SMTP) and SMS (Twilio) on approval
- **Timeline** full compliance timeline with E&O report export

## Demo Mode

No Twilio or email credentials needed for demo:

1. Start the server: `make server`
2. Click **Load Seeds** to load 7 sample messages
3. Click **Generate Digest Now** to create a work packet
4. Click **View** on the digest to see the formatted HTML
5. Navigate to **Inbox** to see individual requests
6. Click any row for the detail view with generated drafts
7. Edit drafts, then Approve or Reject

## Digest System

ServiceInbox Lite generates formatted digest work packets — grouped by category, sorted by urgency, with missing-info flags.

### Schedule
Configure delivery times in `.env`:
```env
DIGEST_SCHEDULE=08:00,12:00,16:00   # 3x daily (default)
DIGEST_RECIPIENTS=producer@agency.com
DIGEST_TIMEZONE=America/New_York
```

### Manual Trigger
Click **Generate Digest Now** on the dashboard, or:
```bash
curl -X POST http://localhost:8000/api/digest/generate
```

### What's in a Digest
- Urgent items banner (items scoring 70+)
- Summary: item counts by category
- Per-category tables with urgency score, customer, subject, channel, timestamp
- Missing information flags (red = required, yellow = optional)

## Running with Email Polling

To run the web server **and** the IMAP email poller together:

```bash
# Both at once (Unix/Mac):
make run

# Or run them separately in two terminals:
make server    # Terminal 1: web server on port 8000
make poller    # Terminal 2: IMAP poller (checks every 30s)
```

On Windows (where `make` is unavailable), run in two terminals:
```powershell
# Terminal 1
uvicorn app.main:app --reload --port 8000

# Terminal 2
python poller.py
```

## Gmail App Password Setup

To use Gmail for inbound (IMAP) and outbound (SMTP) email:

1. Enable **2-Step Verification** at [Google Account Security](https://myaccount.google.com/security)
2. Generate an App Password at [App Passwords](https://myaccount.google.com/apppasswords)
3. Add to `.env` — the password includes spaces, enter exactly as shown

## Twilio Setup (Inbound SMS)

1. Sign up at [twilio.com](https://www.twilio.com), get a phone number
2. Set "A message comes in" webhook to: `https://your-domain.com/webhooks/twilio/sms`
3. Add credentials to `.env`
4. For local dev, use [ngrok](https://ngrok.com): `ngrok http 8000`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard (stats, category breakdown, digests) |
| GET | `/inbox` | Inbox list (with filters) |
| GET | `/request/{id}` | Request detail |
| GET | `/digests` | Digest history |
| GET | `/api/requests` | List all requests (JSON) |
| GET | `/api/requests/{id}` | Get single request (JSON) |
| POST | `/api/simulate` | Simulate an inbound message |
| POST | `/api/seed` | Load seed data |
| POST | `/api/requests/{id}/approve` | Approve and send |
| POST | `/api/requests/{id}/reject` | Reject with reason |
| POST | `/api/digest/generate` | Generate digest now |
| GET | `/api/digests` | List digest runs (JSON) |
| GET | `/api/digests/{id}/html` | View digest HTML |
| GET | `/api/requests/{id}/compliance` | Compliance timeline |
| GET | `/api/requests/{id}/eo-report` | E&O report (plain text) |
| POST | `/webhooks/twilio/sms` | Twilio SMS webhook |

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make install` | Install dependencies |
| `make server` | Run web server only (port 8000) |
| `make poller` | Run IMAP poller only |
| `make run` | Run server + poller together |
| `make test` | Run test suite |
| `make seed` | Load seed data via API |
| `make clean` | Remove SQLite database |

## Project Structure

```
app/
  main.py            — FastAPI app, startup
  config.py          — Settings from .env
  models.py          — SQLModel tables (7 tables, UUID PKs)
  database.py        — DB engine/session
  parser.py          — Intent classification (regex/keywords)
  artifacts.py       — Draft generation with missing-info detection
  digest.py          — Digest generator (group, format, persist)
  ingest.py          — Core ingestion pipeline
  seeds.py           — Seed data loader
  routes/
    inbox.py         — Web UI: dashboard, inbox, detail, digests
    api.py           — JSON API + simulate + digest + compliance
    webhooks.py      — Twilio webhook with signature verification
  services/
    email_ingest.py  — IMAP polling + attachment metadata
    email_send.py    — SMTP outbound
    sms.py           — Twilio SMS
  templates/         — Jinja2 HTML (dashboard, inbox, detail, digests)
  static/            — CSS
poller.py            — Standalone IMAP poller script
seeds/
  sample_messages.json
tests/
  test_parser.py     — Parser/classifier tests
  test_artifacts.py  — Draft generation tests
  test_digest.py     — Digest generation tests
```

## Architecture

```
Inbound:    Twilio webhook ──┐
            IMAP poller ─────┤
            Simulate UI ─────┴──> ingest_message()
                                      │
                              ┌───────┴────────┐
                              │  parse_message  │  → intent, entities, scores
                              └───────┬────────┘
                              ┌───────┴────────┐
                              │ generate_drafts │  → client reply, carrier email
                              └───────┬────────┘
                                      │
                              status = "review"
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                    │
            ┌───────┴────────┐                  ┌───────┴────────┐
            │  Digest Engine │                  │   Web UI / API  │
            │  (scheduled)   │                  │  approve / edit  │
            └───────┬────────┘                  └───────┬────────┘
                    │                                    │
            Work packet email              Outbound: SMTP / Twilio
```
