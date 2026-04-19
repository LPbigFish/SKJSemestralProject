from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.repo import repo

engine = create_engine("sqlite:///./repo.db", echo=True)


def get_db():
    db = Session(bind=engine.connect())
    try:
        yield db
    finally:
        db.close()
