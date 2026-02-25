# ServiceInbox — AI Service Inbox for Insurance Agencies

## Project Overview
MVP demo for an insurance agency inbound message triage system.
Ingests SMS (Twilio) and email (IMAP), classifies intent, generates draft replies,
and lets staff approve/edit/reject before sending.

## Tech Stack
- Python 3.11, FastAPI, Uvicorn
- SQLite via SQLModel (SQLAlchemy under the hood)
- Jinja2 server-rendered templates (simplest for MVP)
- Twilio for inbound SMS webhook
- IMAP for email ingestion, SMTP for outbound email
- No external LLM — deterministic regex/keyword classifier

## Conventions
- All source code lives under `app/`.
- Database file: `serviceinbox.db` (gitignored).
- Environment config via `.env` loaded by pydantic-settings.
- Templates in `app/templates/`, static assets in `app/static/`.
- Use `snake_case` for Python, kebab-case for URL paths where sensible.
- Keep files small (<300 lines). Split into modules by domain.
- Type hints on all function signatures.
- Imports sorted: stdlib → third-party → local, separated by blank lines.

## Key Directories
```
app/
  main.py          — FastAPI app factory, startup events
  config.py        — Settings from .env
  models.py        — SQLModel table definitions
  database.py      — Engine/session setup
  parser.py        — Message classification & extraction
  artifacts.py     — Draft generation (client reply, carrier email, AMS note)
  routes/
    inbox.py       — Web UI routes (list, detail, approve, reject)
    webhooks.py    — Twilio SMS webhook
    api.py         — JSON API + simulate endpoint
  services/
    email_ingest.py  — IMAP polling
    email_send.py    — SMTP outbound
    sms.py           — Twilio helpers
  templates/        — Jinja2 HTML templates
  static/           — CSS, JS
seeds/
  sample_messages.json — Demo seed data
```

## Running
```bash
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Testing
```bash
pytest tests/
```
