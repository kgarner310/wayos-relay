# ServiceInbox — AI Service Inbox for Insurance Agencies

A demo-ready MVP that ingests inbound SMS and email messages, classifies them by intent, generates draft replies, and lets agents approve/edit/reject before sending.

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

## Features

- **Ingest** inbound messages via SMS (Twilio webhook) or email (IMAP polling)
- **Classify** intent: COI, vehicle add, driver add, address change, payroll change, coverage change
- **Extract** entities: customer name, policy number, VIN, dates, addresses, amounts
- **Score** urgency (0-100) and confidence (0-100) for triage prioritization
- **Detect** missing required information per intent category
- **Generate** draft replies: client reply, carrier email, AMS note with professional templates
- **Review** in a web UI with filters, Approve / Edit / Reject workflow
- **Send** outbound emails (SMTP) and SMS (Twilio) on approval
- **Timeline** full compliance timeline with E&O report export

## Demo Mode

No Twilio or email credentials needed for demo:

1. Start the server: `make server`
2. Click **Load Seeds** to load 7 sample messages
3. Click **+ Simulate Message** to create custom test messages
4. Click any row to see the detail view with generated drafts
5. Edit drafts, then Approve or Reject
6. View the compliance timeline and export E&O reports

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

The poller checks for new emails every 30 seconds (configurable via `IMAP_POLL_INTERVAL_SECONDS` in `.env`). Each new email is automatically:
1. Saved as a `RawMessage` with attachment metadata
2. Parsed for intent, entities, urgency, and confidence
3. Draft replies generated (client, carrier, AMS note)
4. Status set to `review` — ready for agent action in the web UI

## Gmail App Password Setup

To use Gmail for inbound (IMAP) and outbound (SMTP) email:

### Step 1: Enable 2-Factor Authentication
1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Under "Signing in to Google", enable **2-Step Verification**

### Step 2: Generate an App Password
1. Go to [App Passwords](https://myaccount.google.com/apppasswords)
2. Select app: **Mail**, device: **Other** (enter "ServiceInbox")
3. Click **Generate** — copy the 16-character password

### Step 3: Configure .env
```env
# Same credentials for both IMAP and SMTP
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=your-agency@gmail.com
IMAP_PASSWORD=abcd efgh ijkl mnop

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-agency@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop
SMTP_FROM_EMAIL=your-agency@gmail.com
```

> **Note:** The app password includes spaces — enter it exactly as shown by Google.

### Step 4: Test It
```bash
# Start the poller
python poller.py

# Send a test email to your-agency@gmail.com from another account
# Watch the poller log — it should pick it up within 30 seconds
```

## Twilio Setup (Inbound SMS)

### Step 1: Create a Twilio Account
1. Sign up at [twilio.com](https://www.twilio.com)
2. Get a phone number with SMS capability

### Step 2: Configure the Webhook
1. In the Twilio console, go to **Phone Numbers** > your number > **Messaging**
2. Set "A message comes in" to: `https://your-domain.com/webhooks/twilio/sms` (POST)
3. For local development, use [ngrok](https://ngrok.com):
   ```bash
   ngrok http 8000
   # Use the https URL ngrok gives you as the webhook URL
   ```

### Step 3: Add Credentials to .env
```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+15551234567

# Optional: enable signature verification in production
TWILIO_VERIFY_SIGNATURE=false
APP_BASE_URL=https://your-ngrok-url.ngrok.io
```

### Signature Verification
Set `TWILIO_VERIFY_SIGNATURE=true` in production to validate that requests
actually come from Twilio. This requires the `twilio` Python package:
```bash
pip install twilio
```

When behind a reverse proxy (ngrok, Cloudflare, etc.), set `APP_BASE_URL`
to the public URL so signature validation uses the correct URL.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Inbox UI (with filters) |
| GET | `/request/{id}` | Request detail UI |
| GET | `/api/requests` | List all requests (JSON) |
| GET | `/api/requests/{id}` | Get single request (JSON) |
| POST | `/api/simulate` | Simulate an inbound message |
| POST | `/api/seed` | Load seed data |
| POST | `/api/requests/{id}/approve` | Approve and send |
| POST | `/api/requests/{id}/reject` | Reject with reason |
| GET | `/api/requests/{id}/audit` | Get audit log |
| GET | `/api/requests/{id}/compliance` | Compliance timeline (JSON) |
| GET | `/api/requests/{id}/eo-report` | E&O report (JSON) |
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
  models.py          — SQLModel tables (5 tables, UUID PKs)
  database.py        — DB engine/session
  parser.py          — Intent classification (regex/keywords)
  artifacts.py       — Draft generation with missing-info detection
  ingest.py          — Core ingestion pipeline
  seeds.py           — Seed data loader
  routes/
    inbox.py         — Web UI routes (list with filters, detail, timeline)
    api.py           — JSON API + simulate + compliance
    webhooks.py      — Twilio webhook with signature verification
  services/
    email_ingest.py  — IMAP polling + attachment metadata
    email_send.py    — SMTP outbound
    sms.py           — Twilio SMS
  templates/         — Jinja2 HTML
  static/            — CSS
poller.py            — Standalone IMAP poller script
seeds/
  sample_messages.json
tests/
  test_parser.py     — Parser/classifier tests
  test_artifacts.py  — Draft generation tests
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
                              │ generate_drafts │  → client reply, carrier email, AMS note
                              └───────┬────────┘
                                      │
                              status = "review"
                                      │
                              ┌───────┴────────┐
                              │   Web UI / API  │  → approve / edit / reject
                              └───────┬────────┘
                                      │
Outbound:   SMTP email ──────┤
            Twilio SMS ──────┘
```

## Adding LLM Later

The parser (`app/parser.py`) and artifact generator (`app/artifacts.py`) are isolated modules.
To add LLM-powered classification:

1. Add your LLM client to a new `app/services/llm.py`
2. Create an `llm_parse_message()` function with the same return type as `parse_message()`
3. Swap in `app/ingest.py` — the rest of the pipeline stays the same
