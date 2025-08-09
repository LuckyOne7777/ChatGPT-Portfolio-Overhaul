from __future__ import annotations

from datetime import datetime, date, time, timedelta
from decimal import Decimal
from functools import wraps
import io
import os
import sqlite3

import jwt
import pandas as pd
import matplotlib.pyplot as plt
from flask import Flask, jsonify, request, render_template, send_file
from zoneinfo import ZoneInfo
from flask_bcrypt import Bcrypt

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


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=((weekday - first.weekday()) % 7) + (n - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    first_next = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
    last = first_next - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(dt: date) -> date:
    if dt.weekday() == 5:
        return dt - timedelta(days=1)
    if dt.weekday() == 6:
        return dt + timedelta(days=1)
    return dt


def _easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def is_us_market_holiday(d: date) -> bool:
    """Return True if *d* is a major U.S. market holiday."""
    year = d.year
    holidays = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed(date(year, 6, 19)),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed(date(year, 12, 25)),
    }
    return d in holidays


def process_portfolio(user_id: int, manual_trades: list[dict[str, object]] | None = None) -> None:
    """Wrapper to keep business logic isolated from the route."""
    portfolio, cash = ts.load_latest_portfolio_state("")
    portfolio_df = portfolio if isinstance(portfolio, pd.DataFrame) else pd.DataFrame(portfolio)
    ts.process_portfolio(portfolio_df, cash, manual_trades)

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
        {"id": row[0], "exp": datetime.utcnow() + timedelta(hours=24)},
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

@app.route("/api/equity-history")
@token_required
def api_equity_history(user_id):
    with begin_tx() as session:
        history = get_equity_series(session)
    rows = [
        {"date": h.date.isoformat(), "equity": float(h.portfolio_equity)} for h in history
    ]
    return jsonify({"history": rows})


@app.route("/api/equity-chart.png")
@token_required
def api_equity_chart(user_id):
    with begin_tx() as session:
        history = get_equity_series(session)
    if not history:
        return jsonify({"message": "No equity history"}), 404
    dates = [h.date for h in history]
    equity = [float(h.portfolio_equity) for h in history]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, equity, label="Portfolio")
    ax.set_xlabel("Date")
    ax.set_ylabel("Portfolio Equity ($)")
    fig.autofmt_xdate()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/api/process-portfolio", methods=["POST"])
@token_required
def api_process_portfolio(user_id):
    data = request.get_json(silent=True) or {}
    force = bool(data.get("force"))
    if not force:
        now = datetime.now(US_EASTERN)
        today = now.date()
        # Reject weekends and official market holidays.
        if now.weekday() >= 5 or is_us_market_holiday(today):
            return (
                jsonify({"error": "Market is closed today. Try the next trading day."}),
                400,
            )
        cutoff = datetime.combine(today, time(16, 10), tzinfo=US_EASTERN)
        # Ensure market has fully closed with a small buffer.
        if now < cutoff:
            return (
                jsonify({"error": "Market has not closed yet. Try again after 4:10 PM ET."}),
                400,
            )
    manual_trades = data.get("manual_trades")
    process_portfolio(user_id, manual_trades)
    return jsonify({"message": "Portfolio processed"})

if __name__ == "__main__":
    from db import init_db as init_models
    init_models()
    app.run(debug=True)
