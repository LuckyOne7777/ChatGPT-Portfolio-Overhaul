"""Utilities for maintaining the ChatGPT micro cap portfolio backed by SQLite."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import pandas as pd
import yfinance as yf

from repo import (
    begin_tx,
    get_positions,
    get_position,
    upsert_position,
    delete_position,
    log_trade,
    apply_cash,
    get_cash_balance,
    record_equity,
)

COLUMNS = [
    "Date",
    "Ticker",
    "Shares",
    "Buy Price",
    "Cost Basis",
    "Stop Loss",
    "Current Price",
    "Total Value",
    "PnL",
    "Action",
    "Cash Balance",
    "Total Equity",
]


def _positions_df(session) -> pd.DataFrame:
    positions = get_positions(session)
    rows = []
    for p in positions:
        rows.append(
            {
                "ticker": p.ticker,
                "shares": float(p.shares),
                "buy_price": float(p.avg_price),
                "cost_basis": float(p.shares * p.avg_price),
                "stop_loss": float(p.stop_loss or 0),
            }
        )
    return pd.DataFrame(rows)


def load_latest_portfolio_state(file: str) -> tuple[pd.DataFrame | list[dict[str, Any]], float]:
    with begin_tx() as session:
        df = _positions_df(session)
        cash = float(get_cash_balance(session))
    return df, cash


def log_manual_buy(
    buy_price: float,
    shares: float,
    ticker: str,
    stoploss: float,
    cash: float,
    chatgpt_portfolio: pd.DataFrame,
    reason: str = "New position",
) -> tuple[float, pd.DataFrame]:
    try:
        data = yf.Ticker(ticker).history(period="1d")
    except Exception:  # pragma: no cover - network errors
        data = pd.DataFrame()
    if not data.empty:
        day_high = float(data["High"].iloc[-1])
        day_low = float(data["Low"].iloc[-1])
        if not (day_low <= buy_price <= day_high):
            raise ValueError(
                f"Manual buy for {ticker} at {buy_price} failed: price outside today's range {round(day_low, 2)}-{round(day_high, 2)}."
            )
    cost = Decimal(str(buy_price)) * Decimal(str(shares))
    with begin_tx() as session:
        cash_bal = get_cash_balance(session)
        if cost > cash_bal:
            raise ValueError(
                f"Manual buy for {ticker} failed: cost {cost} exceeds cash balance {cash_bal}."
            )
        trade = log_trade(
            session,
            "BUY",
            ticker,
            Decimal(str(shares)),
            Decimal(str(buy_price)),
            reason=f"MANUAL BUY - {reason}",
        )
        apply_cash(session, -cost, "TRADE_PNL", trade.id)
        pos = get_position(session, ticker)
        if pos:
            new_shares = pos.shares + Decimal(str(shares))
            new_cost = pos.avg_price * pos.shares + cost
            avg_price = new_cost / new_shares
            upsert_position(session, ticker, new_shares, avg_price, Decimal(str(stoploss)))
        else:
            upsert_position(session, ticker, Decimal(str(shares)), Decimal(str(buy_price)), Decimal(str(stoploss)))
        cash_bal = get_cash_balance(session)
        df = _positions_df(session)
    return float(cash_bal), df


def log_manual_sell(
    sell_price: float,
    shares_sold: float,
    ticker: str,
    cash: float,
    chatgpt_portfolio: pd.DataFrame,
    reason: str = "No reason provided",
) -> tuple[float, pd.DataFrame]:
    with begin_tx() as session:
        pos = get_position(session, ticker)
        if pos is None:
            raise ValueError(f"Manual sell for {ticker} failed: ticker not in portfolio.")
        if Decimal(str(shares_sold)) > pos.shares:
            raise ValueError(
                f"Manual sell for {ticker} failed: trying to sell {shares_sold} shares but only own {float(pos.shares)}."
            )
        try:
            data = yf.Ticker(ticker).history(period="1d")
        except Exception:  # pragma: no cover - network errors
            data = pd.DataFrame()
        if not data.empty:
            day_high = float(data["High"].iloc[-1])
            day_low = float(data["Low"].iloc[-1])
            if not (day_low <= sell_price <= day_high):
                raise ValueError(
                    f"Manual sell for {ticker} at {sell_price} failed: price outside today's range {round(day_low, 2)}-{round(day_high, 2)}."
                )
        proceeds = Decimal(str(sell_price)) * Decimal(str(shares_sold))
        trade = log_trade(
            session,
            "SELL",
            ticker,
            Decimal(str(shares_sold)),
            Decimal(str(sell_price)),
            reason=f"MANUAL SELL - {reason}",
        )
        apply_cash(session, proceeds, "TRADE_PNL", trade.id)
        remaining = pos.shares - Decimal(str(shares_sold))
        if remaining <= 0:
            delete_position(session, ticker)
        else:
            upsert_position(session, ticker, remaining, pos.avg_price, pos.stop_loss)
        cash_bal = get_cash_balance(session)
        df = _positions_df(session)
    return float(cash_bal), df


def process_portfolio(
    portfolio: pd.DataFrame | dict[str, list[object]] | list[dict[str, object]],
    cash: float,
    manual_trades: list[dict[str, object]] | None = None,
    user_id: int = 1,
) -> tuple[pd.DataFrame, float]:
    if manual_trades:
        for trade in manual_trades:
            action = str(trade.get("action", "")).lower()
            ticker = str(trade.get("ticker", "")).upper()
            try:
                shares = float(trade.get("shares", 0))
                price = float(trade.get("price", 0))
            except Exception:
                continue
            try:
                if action == "b":
                    stop_loss = float(trade.get("stop_loss", 0) or 0)
                    reason = str(trade.get("reason", "")).strip() or "New position"
                    cash, _ = log_manual_buy(price, shares, ticker, stop_loss, cash, pd.DataFrame(), reason)
                elif action == "s":
                    reason = str(trade.get("reason", "")).strip() or "No reason provided"
                    cash, _ = log_manual_sell(price, shares, ticker, cash, pd.DataFrame(), reason)
            except ValueError:
                continue

    today = datetime.today().strftime("%Y-%m-%d")

    results: list[dict[str, Any]] = []
    total_value = Decimal("0")
    total_pnl = Decimal("0")
    with begin_tx() as session:
        positions = get_positions(session)
        for pos in positions:
            ticker = pos.ticker
            shares = float(pos.shares)
            buy_price = float(pos.avg_price)
            cost_basis = buy_price * shares
            stop = float(pos.stop_loss or 0)
            try:
                data = yf.Ticker(ticker).history(period="1d")
            except Exception:  # pragma: no cover - network errors
                data = pd.DataFrame()
            if data.empty:
                row = {
                    "Date": today,
                    "Ticker": ticker,
                    "Shares": shares,
                    "Buy Price": buy_price,
                    "Cost Basis": cost_basis,
                    "Stop Loss": stop,
                    "Current Price": "",
                    "Total Value": "",
                    "PnL": "",
                    "Action": "NO DATA",
                    "Cash Balance": "",
                    "Total Equity": "",
                }
            else:
                low_price = float(data["Low"].iloc[-1])
                close_price = float(data["Close"].iloc[-1])
                if stop and low_price <= stop:
                    price = stop
                    value = price * shares
                    pnl = (price - buy_price) * shares
                    trade = log_trade(
                        session,
                        "SELL",
                        ticker,
                        Decimal(str(shares)),
                        Decimal(str(price)),
                        reason="AUTOMATED SELL - STOPLOSS TRIGGERED",
                    )
                    apply_cash(session, Decimal(str(value)), "TRADE_PNL", trade.id)
                    delete_position(session, ticker)
                    action = "SELL - Stop Loss Triggered"
                else:
                    price = close_price
                    value = price * shares
                    pnl = (price - buy_price) * shares
                    total_value += Decimal(str(value))
                    total_pnl += Decimal(str(pnl))
                    action = "HOLD"
                row = {
                    "Date": today,
                    "Ticker": ticker,
                    "Shares": shares,
                    "Buy Price": buy_price,
                    "Cost Basis": cost_basis,
                    "Stop Loss": stop,
                    "Current Price": price,
                    "Total Value": value,
                    "PnL": pnl,
                    "Action": action,
                    "Cash Balance": "",
                    "Total Equity": "",
                }
            results.append(row)
        final_cash = get_cash_balance(session)
        total_row = {
            "Date": today,
            "Ticker": "TOTAL",
            "Shares": "",
            "Buy Price": "",
            "Cost Basis": "",
            "Stop Loss": "",
            "Current Price": "",
            "Total Value": round(float(total_value), 2),
            "PnL": round(float(total_pnl), 2),
            "Action": "",
            "Cash Balance": round(float(final_cash), 2),
            "Total Equity": round(float(total_value + final_cash), 2),
        }
        results.append(total_row)
        record_equity(
            session,
            datetime.today().date(),
            total_value + final_cash,
            user_id=user_id,
        )
        portfolio_df = _positions_df(session)
    df = pd.DataFrame(results)[COLUMNS]
    return portfolio_df, float(final_cash)
