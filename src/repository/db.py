from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import repo

engine = create_engine("sqlite:///repo.db", echo=True)

repo.Base.metadata.create_all(bind=engine)

def get_db():
    db = Session(bind=engine.connect())
    try:
        yield db
    finally:
        db.close()