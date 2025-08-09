from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from db import SessionLocal
from models import Position, Trade, CashLedger, EquityHistory, Setting

@contextmanager
def begin_tx() -> Iterable[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_positions(session: Session) -> list[Position]:
    return session.execute(select(Position).order_by(Position.ticker)).scalars().all()

def get_position(session: Session, ticker: str) -> Position | None:
    return session.execute(select(Position).where(Position.ticker == ticker)).scalar_one_or_none()

def upsert_position(session: Session, ticker: str, shares: Decimal, avg_price: Decimal, stop_loss: Decimal | None) -> Position:
    pos = get_position(session, ticker)
    if pos is None:
        pos = Position(ticker=ticker, shares=shares, avg_price=avg_price, stop_loss=stop_loss)
        session.add(pos)
    else:
        pos.shares = shares
        pos.avg_price = avg_price
        pos.stop_loss = stop_loss
        pos.updated_at = datetime.utcnow()
    return pos

def delete_position(session: Session, ticker: str) -> None:
    pos = get_position(session, ticker)
    if pos:
        session.delete(pos)

def log_trade(session: Session, side: str, ticker: str, shares: Decimal, price: Decimal, fees: Decimal = Decimal("0"), slippage: Decimal = Decimal("0"), reason: str = "") -> Trade:
    trade = Trade(side=side, ticker=ticker, shares=shares, price=price, fees=fees, slippage=slippage, reason=reason)
    session.add(trade)
    session.flush()
    return trade

def apply_cash(session: Session, delta: Decimal, kind: str, ref_trade_id: int | None = None) -> CashLedger:
    ledger = CashLedger(delta=delta, kind=kind, ref_trade_id=ref_trade_id)
    session.add(ledger)
    return ledger

def get_cash_balance(session: Session) -> Decimal:
    return session.execute(select(func.coalesce(func.sum(CashLedger.delta), 0))).scalar_one()

def record_equity(session: Session, date_val: date, portfolio_equity: Decimal, benchmark_equity: Decimal | None = None) -> None:
    stmt = insert(EquityHistory).values(
        date=date_val,
        portfolio_equity=portfolio_equity,
        benchmark_equity=benchmark_equity,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[EquityHistory.date],
        set_={
            "portfolio_equity": portfolio_equity,
            "benchmark_equity": benchmark_equity,
        },
    )
    session.execute(stmt)

def get_equity_series(session: Session, start: date | None = None, end: date | None = None) -> list[EquityHistory]:
    stmt = select(EquityHistory).order_by(EquityHistory.date)
    if start:
        stmt = stmt.where(EquityHistory.date >= start)
    if end:
        stmt = stmt.where(EquityHistory.date <= end)
    return session.execute(stmt).scalars().all()

# Settings

def set_setting(session: Session, key: str, value: str) -> None:
    row = session.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))

def get_setting(session: Session, key: str) -> str | None:
    row = session.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
    return row.value if row else None
