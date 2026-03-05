"""FastAPI application factory."""
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import create_db_and_tables
from app.routes import api, inbox, webhooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(title=settings.app_title)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(inbox.router)
app.include_router(api.router)
app.include_router(webhooks.router)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()
