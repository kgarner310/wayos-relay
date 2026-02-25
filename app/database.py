from sqlmodel import SQLModel, Session, create_engine

from app.config import settings

connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def create_db_and_tables() -> None:
    import app.models  # noqa: F401 — ensure all tables are registered
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
