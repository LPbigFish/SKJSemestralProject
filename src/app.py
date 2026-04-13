from repository.database import engine
from repository.repo import User, Post
from sqlalchemy.orm import Session
from sqlalchemy import select

with Session(engine) as session:
    u1 = User(name = "Alice", email = "alice@example.com")
    u2 = User(name = "Bob", email = "bob@example.com")
    session.add_all([u1, u2])
    session.commit()
    
with Session(engine) as session:
    stmt = select(User)
    results = session.execute(stmt).scalars().all()
    for result in results:
        print(result.name, result.email)