from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "sqlite:///app.db"

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False))

class Base(DeclarativeBase):
    pass

def init_db() -> None:
    from models import Base as ModelsBase  # noqa: F401
    Base.metadata.create_all(bind=engine)
