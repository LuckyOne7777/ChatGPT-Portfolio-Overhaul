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

            if "process_type" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE equity_history ADD COLUMN process_type VARCHAR(10) DEFAULT 'regular'"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE equity_history SET process_type = 'regular' WHERE process_type IS NULL"
                    )
                )

            if "is_final" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE equity_history ADD COLUMN is_final BOOLEAN DEFAULT 1"
                    )
                )
                conn.execute(
                    text(
                        "UPDATE equity_history SET is_final = 1 WHERE is_final IS NULL"
                    )
                )

            # Ensure the correct composite unique index exists and no legacy
            # single-column constraint on date remains. Older databases had
            # ``date`` marked as UNIQUE which conflicts with our upsert logic.
            uniques = insp.get_unique_constraints("equity_history")
            legacy_date_unique = any(uc.get("column_names") == ["date"] for uc in uniques)

            if legacy_date_unique:
                # Rebuild the table without the obsolete UNIQUE constraint.
                conn.execute(text("ALTER TABLE equity_history RENAME TO equity_history_old"))
                conn.execute(
                    text(
                        """
                        CREATE TABLE equity_history (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER,
                            date DATE,
                            portfolio_equity NUMERIC(18, 6),
                            benchmark_equity NUMERIC(18, 6),
                            process_type VARCHAR(10) DEFAULT 'regular',
                            is_final BOOLEAN DEFAULT 1
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO equity_history (id, user_id, date, portfolio_equity, benchmark_equity, process_type, is_final)
                        SELECT id,
                               COALESCE(user_id, 1),
                               date,
                               portfolio_equity,
                               benchmark_equity,
                               COALESCE(process_type, 'regular'),
                               COALESCE(is_final, 1)
                        FROM equity_history_old
                        """
                    )
                )
                conn.execute(text("DROP TABLE equity_history_old"))

            indexes = insp.get_indexes("equity_history")
            has_user_date_index = any(
                idx.get("unique") and idx.get("column_names") == ["user_id", "date"]
                for idx in indexes
            )
            if not has_user_date_index:
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX uix_equity_history_user_date ON equity_history (user_id, date)"
                    )
                )
