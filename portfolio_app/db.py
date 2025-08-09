from sqlalchemy import create_engine, text, inspect
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

    # Ensure existing databases include new columns/constraints
    with engine.begin() as conn:
        insp = inspect(conn)
        if insp.has_table("equity_history"):
            columns = [col["name"] for col in insp.get_columns("equity_history")]
            if "user_id" not in columns:
                conn.execute(text("ALTER TABLE equity_history ADD COLUMN user_id INTEGER"))
                conn.execute(text("UPDATE equity_history SET user_id = 1 WHERE user_id IS NULL"))
                conn.execute(text("DROP INDEX IF EXISTS uix_equity_history_user_date"))
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX uix_equity_history_user_date ON equity_history (user_id, date)"
                    )
                )
