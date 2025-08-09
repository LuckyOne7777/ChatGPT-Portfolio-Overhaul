"""Utilities for maintaining the ChatGPT micro cap portfolio backed by SQLite."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import numpy as np
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
    get_equity_series,
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

def is_valid_ticker(ticker: str) -> bool:
    try:
        data = yf.Ticker(ticker).history(period="1d")
        return not data.empty
    except Exception:
        return False


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


def log_sell(
    ticker: str,
    shares: float,
    price: float,
    cost: float,
    pnl: float,
    portfolio: pd.DataFrame,
) -> pd.DataFrame:
    with begin_tx() as session:
        trade = log_trade(
            session,
            "SELL",
            ticker,
            Decimal(str(shares)),
            Decimal(str(price)),
            reason="AUTOMATED SELL - STOPLOSS TRIGGERED",
        )
        apply_cash(session, Decimal(str(price)) * Decimal(str(shares)), "TRADE_PNL", trade.id)
        delete_position(session, ticker)
        df = _positions_df(session)
    return df


def log_manual_buy(
    buy_price: float,
    shares: float,
    ticker: str,
    stoploss: float,
    cash: float,
    chatgpt_portfolio: pd.DataFrame,
    reason: str = "New position",
) -> tuple[float, pd.DataFrame]:
    data = yf.download(ticker, period="1d")
    if data.empty:
        print(f"Manual buy for {ticker} failed: no market data available.")
        with begin_tx() as session:
            cash_bal = float(get_cash_balance(session))
            df = _positions_df(session)
        return cash_bal, df
    day_high = float(data["High"].iloc[-1])
    day_low = float(data["Low"].iloc[-1])
    if not (day_low <= buy_price <= day_high):
        print(
            f"Manual buy for {ticker} at {buy_price} failed: price outside today's range {round(day_low, 2)}-{round(day_high, 2)}."
        )
        with begin_tx() as session:
            cash_bal = float(get_cash_balance(session))
            df = _positions_df(session)
        return cash_bal, df
    cost = Decimal(str(buy_price)) * Decimal(str(shares))
    with begin_tx() as session:
        cash_bal = get_cash_balance(session)
        if cost > cash_bal:
            print(f"Manual buy for {ticker} failed: cost {cost} exceeds cash balance {cash_bal}.")
            df = _positions_df(session)
            return float(cash_bal), df
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
    print(f"Manual buy for {ticker} complete!")
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
            print(f"Manual sell for {ticker} failed: ticker not in portfolio.")
            cash_bal = float(get_cash_balance(session))
            df = _positions_df(session)
            return cash_bal, df
        if Decimal(str(shares_sold)) > pos.shares:
            print(
                f"Manual sell for {ticker} failed: trying to sell {shares_sold} shares but only own {float(pos.shares)}."
            )
            cash_bal = float(get_cash_balance(session))
            df = _positions_df(session)
            return cash_bal, df
        data = yf.download(ticker, period="1d")
        if data.empty:
            print(f"Manual sell for {ticker} failed: no market data available.")
            cash_bal = float(get_cash_balance(session))
            df = _positions_df(session)
            return cash_bal, df
        day_high = float(data["High"].iloc[-1])
        day_low = float(data["Low"].iloc[-1])
        if not (day_low <= sell_price <= day_high):
            print(
                f"Manual sell for {ticker} at {sell_price} failed: price outside today's range {round(day_low, 2)}-{round(day_high, 2)}."
            )
            cash_bal = float(get_cash_balance(session))
            df = _positions_df(session)
            return cash_bal, df
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
    print(f"manual sell for {ticker} complete!")
    return float(cash_bal), df


def process_portfolio(
    portfolio: pd.DataFrame | dict[str, list[object]] | list[dict[str, object]],
    cash: float,
    manual_trades: list[dict[str, object]] | None = None,
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
            if action == "b":
                stop_loss = float(trade.get("stop_loss", 0) or 0)
                reason = str(trade.get("reason", "")).strip() or "New position"
                cash, _ = log_manual_buy(price, shares, ticker, stop_loss, cash, pd.DataFrame(), reason)
            elif action == "s":
                reason = str(trade.get("reason", "")).strip() or "No reason provided"
                cash, _ = log_manual_sell(price, shares, ticker, cash, pd.DataFrame(), reason)

    today = datetime.today().strftime("%Y-%m-%d")
    day = datetime.today().weekday()
    if day in (5, 6):
        print("Warning: processing portfolio on weekend; using last available market data.")

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
            data = yf.Ticker(ticker).history(period="1d")
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
        record_equity(session, datetime.today().date(), total_value + final_cash)
        portfolio_df = _positions_df(session)
    df = pd.DataFrame(results)[COLUMNS]
    return portfolio_df, float(final_cash)


def daily_results(chatgpt_portfolio: pd.DataFrame, cash: float) -> None:
    today = datetime.today().strftime("%Y-%m-%d")
    portfolio_dict = chatgpt_portfolio.to_dict(orient="records")
    print(f"prices and updates for {today}")
    for stock in portfolio_dict + [{"ticker": "^RUT"}] + [{"ticker": "IWO"}] + [{"ticker": "XBI"}]:
        ticker = stock["ticker"]
        try:
            data = yf.download(ticker, period="2d", progress=False)
            price = float(data["Close"].iloc[-1])
            last_price = float(data["Close"].iloc[-2])
            percent_change = ((price - last_price) / last_price) * 100
            volume = float(data["Volume"].iloc[-1])
        except Exception as e:
            raise Exception(f"Download for {ticker} failed. {e} Try checking internet connection.")
        print(f"{ticker} closing price: {price:.2f}")
        print(f"{ticker} volume for today: ${volume:,}")
        print(f"percent change from the day before: {percent_change:.2f}%")
    with begin_tx() as session:
        history = get_equity_series(session)
    if not history:
        return
    chatgpt_totals = pd.DataFrame(
        {"Date": [h.date for h in history], "Total Equity": [float(h.portfolio_equity) for h in history]}
    )
    chatgpt_totals["Date"] = pd.to_datetime(chatgpt_totals["Date"])
    final_date = chatgpt_totals["Date"].max()
    final_value = chatgpt_totals[chatgpt_totals["Date"] == final_date]
    final_equity = float(final_value["Total Equity"].values[0])
    equity_series = chatgpt_totals["Total Equity"].astype(float).reset_index(drop=True)
    daily_pct = equity_series.pct_change().dropna()
    total_return = (equity_series.iloc[-1] - equity_series.iloc[0]) / equity_series.iloc[0]
    n_days = len(chatgpt_totals)
    rf_annual = 0.045
    rf_period = (1 + rf_annual) ** (n_days / 252) - 1
    std_daily = daily_pct.std()
    negative_pct = daily_pct[daily_pct < 0]
    negative_std = negative_pct.std()
    sharpe_total = (total_return - rf_period) / (std_daily * np.sqrt(n_days))
    sharpe_normalized = (total_return - rf_period) / (std_daily * np.sqrt(252))
    sortino_total = (total_return - rf_period) / (negative_std * np.sqrt(n_days))
    sortino_normalized = (total_return - rf_period) / (negative_std * np.sqrt(252))
    print(f"Total Sharpe Ratio over {n_days} days: {sharpe_total:.4f}")
    print(f"Total Sortino Ratio over {n_days} days: {sortino_total:.4f}")
    print(f"Total Sharpe Ratio normalized to years: {sharpe_normalized:.4f}")
    print(f"Total Sortino Ratio normalized to years: {sortino_normalized:.4f}")
    print(f"Latest ChatGPT Equity: ${final_equity:.2f}")
    print("today's portfolio:")
    print(chatgpt_portfolio)
    print(f"cash balance: {cash}")
    print(
        "Here are is your update for today. You can make any changes you see fit (if necessary),\n"
        "but you may not use deep research. You do have to ask premissons for any changes, as you have full control.\n"
        "You can however use the Internet and check current prices for potenial buys."
    )
