from __future__ import annotations

from datetime import datetime, date, time, timedelta, UTC
from decimal import Decimal
from functools import wraps
import os
import sqlite3
from typing import Literal
import time as time_module
from json import JSONDecodeError

import jwt
import pandas as pd
import yfinance as yf
from flask import Flask, jsonify, request, render_template
from zoneinfo import ZoneInfo
from flask_bcrypt import Bcrypt
from requests.exceptions import RequestException

import trading_script as ts
from repo import (
    begin_tx,
    get_cash_balance,
    apply_cash,
    get_setting,
    set_setting,
    get_positions,
    get_equity_series,
    get_position,
    upsert_equity,
)
from db import init_db as init_models

app = Flask(__name__, static_folder=".", static_url_path="")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret")
bcrypt = Bcrypt(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "users.db")

def init_db() -> None:
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, email TEXT UNIQUE, password TEXT)"
        )
        conn.commit()

init_db()
init_models()


@app.route("/")
def home() -> str:
    return render_template("home.html")


@app.route("/login")
def login_page() -> str:
    return render_template("login.html")


@app.route("/signin")
def signin_page() -> str:
    return render_template("signin.html")


@app.route("/sample-portfolio")
def sample_portfolio() -> str:
    return render_template("sample_portfolio.html")


@app.route("/dashboard")
def dashboard_page() -> str:
    """Serve the main dashboard page."""
    return app.send_static_file("index.html")


@app.route("/about")
def about_page() -> str:
    """Serve the about page."""
    return app.send_static_file("about.html")


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        parts = auth_header.split()
        token = parts[1] if len(parts) == 2 and parts[0] == "Bearer" else None
        if not token:
            return jsonify({"message": "Token is missing!"}), 401
        try:
            data = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        except Exception:
            return jsonify({"message": "Token is invalid!"}), 401
        return f(data["id"], *args, **kwargs)

    return decorated


US_EASTERN = ZoneInfo("America/New_York")  # Eastern Time zone


def _us_holidays(year: int) -> set[date]:
    """Minimal U.S. market holiday set for *year* (no external deps)."""
    return {
        date(year, 1, 1),   # New Year's Day
        date(year, 1, 15),  # Martin Luther King Jr. Day
        date(year, 2, 19),  # Presidents' Day
        date(year, 3, 29),  # Good Friday
        date(year, 5, 27),  # Memorial Day
        date(year, 6, 19),  # Juneteenth
        date(year, 7, 4),   # Independence Day
        date(year, 9, 2),   # Labor Day
        date(year, 11, 28), # Thanksgiving Day
        date(year, 12, 25), # Christmas Day
    }


def _is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _us_holidays(d.year)


def _next_trading_day(d: date) -> date:
    nxt = d
    while True:
        nxt += timedelta(days=1)
        if _is_trading_day(nxt):
            return nxt


def _prev_trading_day(d: date) -> date:
    prev = d - timedelta(days=1)
    while not _is_trading_day(prev):
        prev -= timedelta(days=1)
    return prev


def looks_invalid_ticker(t: str) -> bool:
    return not t or any(ch.isspace() for ch in t) or len(t) > 10


def _stooq_symbol(ticker: str) -> str:
    t = ticker.lower()
    return t if "." in t else f"{t}.us"


def _safe_download(ticker: str, start: date, end: date) -> pd.DataFrame | None:
    try:
        df = yf.download(ticker, period="20d", progress=False)
        if isinstance(df, pd.DataFrame) and not df.empty:
            df = df.tail(60)
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC").tz_convert(US_EASTERN)
            else:
                df.index = df.index.tz_convert(US_EASTERN)
            if "Adj Close" not in df.columns:
                df["Adj Close"] = df["Close"]
            for col in ["Open", "High", "Low"]:
                if col not in df.columns:
                    df[col] = df["Close"]
            df = df[["Open", "High", "Low", "Close", "Adj Close", "Volume"]]
            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
    except Exception:
        pass

    period_days = max(1, (end - start).days) if start and end else 20
    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(period=f"{period_days}d", interval="1d", raise_errors=False)
        if isinstance(df, pd.DataFrame) and not df.empty:
            df = df.tail(60)
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC").tz_convert(US_EASTERN)
            else:
                df.index = df.index.tz_convert(US_EASTERN)
            if "Adj Close" not in df.columns:
                df["Adj Close"] = df["Close"]
            for col in ["Open", "High", "Low"]:
                if col not in df.columns:
                    df[col] = df["Close"]
            df = df[["Open", "High", "Low", "Close", "Adj Close", "Volume"]]
            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
        price = None
        try:
            price = ticker_obj.fast_info.get("last_price")
        except Exception:
            price = None
        if price:
            dt = datetime.now(US_EASTERN).replace(hour=0, minute=0, second=0, microsecond=0)
            df = pd.DataFrame(
                {
                    "Open": [price],
                    "High": [price],
                    "Low": [price],
                    "Close": [price],
                    "Adj Close": [price],
                    "Volume": [0],
                },
                index=pd.DatetimeIndex([dt], tz=US_EASTERN),
            )
            return df
    except Exception:
        pass

    try:
        symbol = _stooq_symbol(ticker)
        url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
        df = pd.read_csv(url, sep=None, engine="python")
        if df.empty:
            return None
        df = df.tail(60)
        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize("America/New_York")
        df.set_index("Date", inplace=True)
        if "Adj Close" not in df.columns:
            df["Adj Close"] = df["Close"]
        for col in ["Open", "High", "Low"]:
            if col not in df.columns:
                df[col] = df["Close"]
        for col in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df[["Open", "High", "Low", "Close", "Adj Close", "Volume"]]
        app.logger.info("stooq_fallback_used %s", ticker)
        print(f"[INFO] Using Stooq fallback for {ticker} — Yahoo returned bad/empty data.")
        return df
    except Exception as e:
        app.logger.warning("download_failed %s %s", ticker, e)
    return None


def _check_market_window(now: datetime) -> tuple[bool, str, datetime]:
    """Return (allowed, reason, reference_dt)."""
    today = now.date()
    if not _is_trading_day(today):
        next_day = _next_trading_day(today)
        next_window = datetime.combine(next_day, time(16, 10), tzinfo=US_EASTERN)
        return False, "closed_day", next_window
    cutoff = datetime.combine(today, time(16, 10), tzinfo=US_EASTERN)
    if now < cutoff:
        return False, "too_early", cutoff
    return True, "", cutoff


def get_close_price(
    ticker: str,
    mode: Literal["regular", "force"],
    now_utc: datetime,
    buy_price: float | None = None,
) -> tuple[float, str, str]:
    """Return (price, as_of_date_et, source)."""

    now_et = now_utc.astimezone(US_EASTERN)
    today_str = now_et.date().isoformat()

    t = ticker.strip().upper().translate(str.maketrans({c: "" for c in "'`\"“”‘’"}))
    if looks_invalid_ticker(t):
        app.logger.warning("invalid_ticker %s", ticker)
        if buy_price and buy_price > 0:
            return float(buy_price), today_str, "fallback_buy"
        return 0.0, today_str, "fallback_zero"

    target_date = now_et.date()
    if mode == "force" and not _is_trading_day(target_date):
        target_date = _prev_trading_day(target_date)

    # Extend download window to reduce Yahoo Finance empty responses on force
    # processing. A broader timeframe increases the chance of retrieving data
    # for symbols that might otherwise fail due to narrow ranges.
    start = target_date - timedelta(days=7)
    end = target_date + timedelta(days=2)
    df = _safe_download(t, start, end)
    if df is not None and not df.empty:
        try:
            df.index = df.index.tz_localize(ZoneInfo("UTC")).tz_convert(US_EASTERN)
        except TypeError:
            df.index = df.index.tz_convert(US_EASTERN)
        rows = df[df.index.date == target_date]
        if not rows.empty:
            price = float(rows["Close"].iloc[-1])
            return price, target_date.isoformat(), "close"
        prev_rows = df[df.index.date <= target_date]
        if not prev_rows.empty:
            row = prev_rows.iloc[-1]
            date_str = row.name.date().isoformat()
            source = "prev_close" if date_str < target_date.isoformat() else "close"
            close_val = row["Close"]
            if isinstance(close_val, pd.Series):
                close_val = close_val.iloc[0]
            return float(close_val), date_str, source

    if buy_price and buy_price > 0:
        return float(buy_price), today_str, "fallback_buy"
    return 0.0, today_str, "fallback_zero"


def process_portfolio(user_id: int, manual_trades: list[dict[str, object]] | None = None) -> None:
    """Wrapper to keep business logic isolated from the route."""
    portfolio, cash = ts.load_latest_portfolio_state("")
    portfolio_df = portfolio if isinstance(portfolio, pd.DataFrame) else pd.DataFrame(portfolio)
    ts.process_portfolio(portfolio_df, cash, manual_trades, user_id=user_id)

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username", "")
    email = data.get("email", "")
    password = data.get("password", "")
    if not username or not email or not password:
        return jsonify({"message": "Missing fields"}), 400
    hashed = bcrypt.generate_password_hash(password).decode("utf-8")
    try:
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO users (username, email, password) VALUES (?,?,?)",
                (username, email, hashed),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"message": "User exists"}), 400
    return jsonify({"message": "User registered"}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username", "")
    password = data.get("password", "")
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, password FROM users WHERE username=?", (username,))
        row = c.fetchone()
    if not row or not bcrypt.check_password_hash(row[1], password):
        return jsonify({"message": "Invalid credentials"}), 401
    token = jwt.encode(
        {"id": row[0], "exp": datetime.now(UTC) + timedelta(hours=24)},
        app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    return jsonify({"token": token})

@app.route("/api/needs-cash")
@token_required
def needs_cash(user_id):
    with begin_tx() as session:
        starting = get_setting(session, "starting_equity")
    return jsonify({"needs_cash": starting is None})

@app.route("/api/set-cash", methods=["POST"])
@token_required
def set_cash(user_id):
    data = request.get_json() or {}
    try:
        amount = Decimal(str(data.get("cash", 0)))
    except Exception:
        return jsonify({"message": "Invalid cash amount"}), 400
    with begin_tx() as session:
        apply_cash(session, amount, "DEPOSIT")
        set_setting(session, "starting_equity", str(amount))
    return jsonify({"cash": float(amount)}), 201

@app.route("/api/trade", methods=["POST"])
@token_required
def api_trade(user_id):
    data = request.get_json() or {}
    ticker = (data.get("ticker") or "").upper()
    side = (data.get("action") or data.get("side") or "").upper()
    try:
        price = float(data.get("price", 0))
        shares = float(data.get("shares", 0))
    except (TypeError, ValueError):
        return jsonify({"message": "Invalid price or shares"}), 400
    reason = data.get("reason", "")
    stop_loss = float(data.get("stop_loss", 0) or 0)
    if not ticker or side not in {"BUY", "SELL"} or price <= 0 or shares <= 0:
        return jsonify({"message": "Invalid trade data"}), 400
    try:
        if side == "BUY":
            with begin_tx() as session:
                balance = float(get_cash_balance(session))
            if price * shares > balance:
                return jsonify({"message": "You don't have enough cash to buy these shares"}), 400
            cash, _ = ts.log_manual_buy(price, shares, ticker, stop_loss, balance, pd.DataFrame(), reason)
        else:
            with begin_tx() as session:
                pos = get_position(session, ticker)
                if pos is None or float(pos.shares) < shares:
                    return jsonify({"message": "You're trying to sell more shares than you own"}), 400
            cash, _ = ts.log_manual_sell(price, shares, ticker, 0.0, pd.DataFrame(), reason)
    except ValueError as e:
        return jsonify({"message": str(e)}), 400
    return jsonify({"message": "Trade recorded", "cash": cash})

@app.route("/api/portfolio")
@token_required
def api_portfolio(user_id):
    with begin_tx() as session:
        positions = get_positions(session)
        cash = float(get_cash_balance(session))
        starting = get_setting(session, "starting_equity")
    pos_list = [
        {
            "ticker": p.ticker,
            "shares": float(p.shares),
            "buy_price": float(p.avg_price),
            "stop_loss": float(p.stop_loss or 0),
            "cost_basis": float(p.avg_price * p.shares),
        }
        for p in positions
    ]
    deployed_capital = sum(p["cost_basis"] for p in pos_list)
    total_equity = cash + deployed_capital
    return jsonify(
        {
            "positions": pos_list,
            "cash": cash,
            "starting_capital": float(starting) if starting else None,
            "total_equity": total_equity,
            "deployed_capital": deployed_capital,
        }
    )

@app.route("/api/trade-log")
@token_required
def api_trade_log(user_id):
    from models import Trade
    from sqlalchemy import select
    with begin_tx() as session:
        trades = session.execute(select(Trade).order_by(Trade.created_at)).scalars().all()
    rows = [
        {
            "date": t.created_at.strftime("%Y-%m-%d"),
            "ticker": t.ticker,
            "side": t.side,
            "shares": float(t.shares),
            "price": float(t.price),
            "reason": t.reason,
        }
        for t in trades
    ]
    return jsonify({"trades": rows})

@app.route("/api/portfolio-history")
@token_required
def api_portfolio_history(user_id):
    with begin_tx() as session:
        history = get_equity_series(session, user_id)
    rows = [
        {"date": h.date.isoformat(), "equity": float(h.portfolio_equity)}
        for h in history
    ]
    return jsonify(rows)

@app.route("/api/process-portfolio", methods=["POST"])
@token_required
def api_process_portfolio(user_id):
    """
    Process portfolio (default path)
    - One clean equity snapshot per trading day using final daily closes.
    - Runs only on valid US trading days and after 4:10 PM ET.
    - Idempotent: upsert on date, no duplicates.

    Force processing
    - Admin/backfill escape hatch when processing outside the window.
    - Skips time/holiday checks but logs a warning and marks "forced": true.
    - Still idempotent (same upsert rule).
    """

    data = request.get_json(silent=True) or {}
    raw_force = data.get("force", request.args.get("force"))
    force = str(raw_force).lower() == "true"

    if not force:
        allowed, reason, ref_dt = _check_market_window(datetime.now(US_EASTERN))
        if not allowed:
            if reason == "closed_day":
                return (
                    jsonify(
                        {
                            "message": "Market is closed (weekend/holiday).",
                            "reason": "closed_day",
                            "next_window_et": ref_dt.strftime("%Y-%m-%d %H:%M ET"),
                            "hint": "Try after market close on the next trading day or pass {\"force\": true} for a one-off run.",
                        }
                    ),
                    400,
                )
            if reason == "too_early":
                return (
                    jsonify(
                        {
                            "message": "Too early to process — wait for market close.",
                            "reason": "too_early",
                            "earliest_et": ref_dt.strftime("%Y-%m-%d %H:%M ET"),
                            "hint": "Retry after 4:10 PM ET or pass {\"force\": true} if you must.",
                        }
                    ),
                    400,
                )
    else:
        app.logger.warning("process-portfolio forced by user %s", user_id)

    now_utc = datetime.now(UTC)
    mode = "force" if force else "regular"

    with begin_tx() as session:
        positions = get_positions(session)
        cash = float(get_cash_balance(session))

    positions_out: list[dict[str, float | str]] = []
    total_positions_value = 0.0
    total_pnl = 0.0
    as_of_date: str | None = None

    for pos in positions:
        shares = float(pos.shares)
        buy_price = float(pos.avg_price)
        px, px_date, source = get_close_price(pos.ticker, mode, now_utc, buy_price)
        if as_of_date is None or px_date > as_of_date:
            as_of_date = px_date
        if source.startswith("fallback"):
            app.logger.warning("price_fallback %s %s", pos.ticker, source)
        position_value = shares * px
        pnl = (px - buy_price) * shares
        total_positions_value += position_value
        total_pnl += pnl
        positions_out.append(
            {
                "ticker": pos.ticker,
                "shares": shares,
                "buy_price": buy_price,
                "current_price": px,
                "position_value": position_value,
                "pnl": pnl,
                "price_source": source,
            }
        )

    totals = {
        "total_positions_value": total_positions_value,
        "total_pnl": total_pnl,
        "cash": cash,
        "total_equity": cash + total_positions_value,
    }

    if as_of_date is None:
        as_of_date = now_utc.astimezone(US_EASTERN).date().isoformat()

    as_of_date_obj = datetime.strptime(as_of_date, "%Y-%m-%d").date()
    with begin_tx() as session:
        upsert_equity(
            session,
            user_id,
            as_of_date_obj,
            Decimal(str(totals["total_equity"])),
            process_type="force" if force else "regular",
            is_final=not force,
        )

    return jsonify(
        {
            "message": "Portfolio processed",
            "forced": force,
            "date": datetime.now(US_EASTERN).date().isoformat(),
            "as_of_date_et": as_of_date,
            "positions": positions_out,
            "totals": totals,
        }
    )

if __name__ == "__main__":
    from db import init_db as init_models
    init_models()
    app.run(debug=True)
