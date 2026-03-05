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
uvicorn app.main:app --reload --port 8000

# 6. Open http://localhost:8000 — click "Load Seeds" to populate demo data
```

## Features

- **Ingest** inbound messages via SMS (Twilio webhook) or email (IMAP polling)
- **Classify** intent: COI, vehicle add, driver add, address change, payroll change, coverage change
- **Extract** customer name, policy number hints, urgency score
- **Generate** draft replies: client reply, carrier email, AMS note
- **Review** in a web UI with Approve / Edit / Reject workflow
- **Send** outbound emails (SMTP) and SMS (Twilio) on approval
- **Audit** full log of every action with timestamps

## Demo Mode

No Twilio or email credentials needed for demo:

1. Start the server
2. Click **Load Seeds** to load 7 sample messages
3. Click **+ Simulate Message** to create custom test messages
4. Click any row to see the detail view with generated drafts
5. Edit drafts, then Approve or Reject

## Twilio Setup (for live SMS)

1. Create a Twilio account at https://www.twilio.com
2. Get a phone number with SMS capability
3. Set your webhook URL in the Twilio console:
   - Go to **Phone Numbers** > your number > **Messaging**
   - Set "A message comes in" to: `https://your-domain.com/webhooks/twilio/sms` (POST)
   - For local dev, use [ngrok](https://ngrok.com): `ngrok http 8000`
4. Add credentials to `.env`:
   ```
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_PHONE_NUMBER=+15551234567
   ```

## Email Setup (IMAP/SMTP)

### Gmail with App Passwords

1. Enable 2-Factor Authentication on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Generate an app password for "Mail"
4. Add to `.env`:
   ```
   IMAP_HOST=imap.gmail.com
   IMAP_PORT=993
   IMAP_USER=your-email@gmail.com
   IMAP_PASSWORD=your-app-password

   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   ```

### IMAP Polling

IMAP polling is not auto-started in the MVP. To poll manually or on a cron:
```bash
python -c "from app.services.email_ingest import fetch_new_emails; print(fetch_new_emails())"
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Inbox UI |
| GET | `/request/{id}` | Request detail UI |
| GET | `/api/requests` | List all requests (JSON) |
| GET | `/api/requests/{id}` | Get single request (JSON) |
| POST | `/api/simulate` | Simulate an inbound message |
| POST | `/api/seed` | Load seed data |
| POST | `/api/requests/{id}/approve` | Approve and send |
| POST | `/api/requests/{id}/reject` | Reject request |
| GET | `/api/requests/{id}/audit` | Get audit log |
| POST | `/webhooks/twilio/sms` | Twilio SMS webhook |

## Project Structure

```
app/
  main.py            — FastAPI app, startup
  config.py          — Settings from .env
  models.py          — SQLModel tables
  database.py        — DB engine/session
  parser.py          — Intent classification (regex/keywords)
  artifacts.py       — Draft generation templates
  ingest.py          — Core ingestion pipeline
  seeds.py           — Seed data loader
  routes/
    inbox.py         — Web UI routes
    api.py           — JSON API
    webhooks.py      — Twilio webhook
  services/
    email_ingest.py  — IMAP polling
    email_send.py    — SMTP outbound
    sms.py           — Twilio SMS
  templates/         — Jinja2 HTML
  static/            — CSS
seeds/
  sample_messages.json
```

## Adding LLM Later

The parser (`app/parser.py`) and artifact generator (`app/artifacts.py`) are isolated modules.
To add LLM-powered classification:

1. Add your LLM client to a new `app/services/llm.py`
2. Create an `llm_parse_message()` function with the same return type as `parse_message()`
3. Swap in `app/ingest.py` — the rest of the pipeline stays the same
