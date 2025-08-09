from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    String,
    Numeric,
    Integer,
    Date,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base

class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String, unique=True, index=True)
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    avg_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Trade(Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String(4))
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    slippage: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class CashLedger(Base):
    __tablename__ = "cash_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delta: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    kind: Mapped[str] = mapped_column(String(20))
    ref_trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class EquityHistory(Base):
    __tablename__ = "equity_history"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uix_equity_history_user_date"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[date] = mapped_column(Date)
    portfolio_equity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    benchmark_equity: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    process_type: Mapped[str] = mapped_column(String(10), default="regular")
    is_final: Mapped[bool] = mapped_column(Boolean, default=True)

class Setting(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True)
    value: Mapped[str] = mapped_column(Text)
