from flask import Flask, request, jsonify, send_from_directory, send_file, render_template
from flask_bcrypt import Bcrypt
import sqlite3
import jwt
from datetime import datetime, timedelta
from functools import wraps
import os
import csv
from typing import Tuple, Any
import yfinance as yf
from pathlib import Path

import pandas as pd
import trading_script as ts

try:  # Optional Streamlit integration for session state
    import streamlit as st
except Exception:  # pragma: no cover - streamlit is optional
    st = None

app = Flask(__name__, static_folder=None)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-this-secret')
bcrypt = Bcrypt(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'Scripts and CSV Files')
DATABASE = os.path.join(BASE_DIR, 'users.db')
# Use ChatGPT's actual logs as the publicly viewable samples
SAMPLE_PORTFOLIO = os.path.join(DATA_DIR, 'chatgpt_portfolio.csv')
SAMPLE_TRADE_LOG = os.path.join(DATA_DIR, 'chatgpt_trade_log.csv')


def ensure_user_files(username: str) -> Tuple[str, str, str]:
    """Create per-user portfolio, trade log, and cash files if missing."""

    os.makedirs(DATA_DIR, exist_ok=True)
    portfolio = os.path.join(DATA_DIR, f"{username}_portfolio.csv")
    trade_log = os.path.join(DATA_DIR, f"{username}_trade_log.csv")
    cash_file = os.path.join(DATA_DIR, f"{username}_cash.txt")

    if not os.path.exists(portfolio):
        with open(portfolio, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Date',
                'Ticker',
                'Shares',
                'Cost Basis',
                'Stop Loss',
                'Current Price',
                'Total Value',
                'PnL',
                'Action',
                'Cash Balance',
                'Total Equity',
            ])

    if not os.path.exists(trade_log):
        with open(trade_log, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Date',
                'Ticker',
                'Shares Bought',
                'Buy Price',
                'Cost Basis',
                'PnL',
                'Reason',
                'Shares Sold',
                'Sell Price',
            ])

    if not os.path.exists(cash_file):
        # Create an empty cash file. A starting balance will be set later
        # if the user has no trading history.
        open(cash_file, 'w').close()

    if st is not None:
        st.session_state.setdefault(username, {})
        st.session_state[username]['cash_file'] = cash_file

    return portfolio, trade_log, cash_file


def get_user_files(user_id: int) -> Tuple[str, str, str, str]:
    """Return username and related data file paths for a user."""

    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('SELECT username FROM users WHERE id=?', (user_id,))
        row = c.fetchone()

    if not row:
        raise ValueError('User not found')

    username = row[0]
    portfolio = os.path.join(DATA_DIR, f"{username}_portfolio.csv")
    trade_log = os.path.join(DATA_DIR, f"{username}_trade_log.csv")
    cash_file = os.path.join(DATA_DIR, f"{username}_cash.txt")
    return username, portfolio, trade_log, cash_file


def user_needs_cash(user_id: int) -> bool:
    """Return True if the user has no trade history and no starting cash."""

    _, _, trade_log, cash_file = get_user_files(user_id)

    has_trades = False
    if os.path.exists(trade_log) and os.path.getsize(trade_log) > 0:
        with open(trade_log, newline='') as f:
            reader = csv.DictReader(f)
            has_trades = any(True for _ in reader)

    has_cash = os.path.exists(cash_file) and os.path.getsize(cash_file) > 0
    return (not has_trades) and (not has_cash)


def is_valid_ticker(ticker: str) -> bool:
    """Return True if ``ticker`` has market data via yfinance."""

    try:
        data = yf.Ticker(ticker).history(period="1d")
        return not data.empty
    except Exception:
        return False


def init_db():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute(
            'CREATE TABLE IF NOT EXISTS users ('
            'id INTEGER PRIMARY KEY AUTOINCREMENT, '
            'username TEXT UNIQUE, '
            'email TEXT UNIQUE, '
            'password TEXT)'
        )
        conn.commit()

init_db()


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        parts = auth_header.split()
        token = parts[1] if len(parts) == 2 and parts[0] == 'Bearer' else None
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except Exception:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(data['id'], *args, **kwargs)
    return decorated


@app.route('/')
def serve_home():
    return send_from_directory('templates', 'home.html')


@app.route('/dashboard')
def serve_dashboard():
    return send_from_directory('.', 'index.html')


@app.route('/script.js')
def serve_script():
    return send_from_directory('.', 'script.js')


@app.route('/styles.css')
def serve_styles():
    return send_from_directory('.', 'styles.css')


@app.route('/login.css')
def serve_login_css():
    return send_from_directory('.', 'login.css')


@app.route('/sample-portfolio')
def sample_portfolio_page():
    return send_from_directory('templates', 'sample_portfolio.html')


@app.route('/sample_portfolio.js')
def serve_sample_portfolio_js():
    return send_from_directory('.', 'sample_portfolio.js')

@app.route('/sample_trade_log.js')
def serve_sample_trade_log_js():
    return send_from_directory('.', 'sample_trade_log.js')


@app.route('/sample')
def sample_page():
    return render_template('sample.html')


@app.route('/sample_chart.png')
def sample_chart_png():
    """Generate the same comparison chart as ``Generate_Graph.py`` as a PNG."""
    import importlib.util
    from io import BytesIO
    from pathlib import Path

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    data_dir = Path(__file__).resolve().parent / 'Scripts and CSV Files'
    script_path = data_dir / 'Generate_Graph.py'

    spec = importlib.util.spec_from_file_location('generate_graph', script_path)
    generate_graph = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generate_graph)

    chatgpt_totals = generate_graph.load_portfolio_details(100.0, None)
    start_date = chatgpt_totals['Date'].min()
    end_date = chatgpt_totals['Date'].max()

    fallback = Path(__file__).resolve().parent / 'week4_performance.png'
    try:
        sp500 = generate_graph.download_sp500(start_date, end_date)
        if sp500.empty:
            raise ValueError('Empty SP500 data')
    except Exception:
        # Fall back to a pre-generated chart so the sample page always works
        return send_file(fallback, mimetype='image/png')

    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(
        chatgpt_totals['Date'],
        chatgpt_totals['Total Equity'],
        label='ChatGPT ($100 Invested)',
        marker='o',
        color='blue',
        linewidth=2,
    )
    ax.plot(
        sp500['Date'],
        sp500['SPX Value ($100 Invested)'],
        label='S&P 500 ($100 Invested)',
        marker='o',
        color='orange',
        linestyle='--',
        linewidth=2,
    )

    final_date = chatgpt_totals['Date'].iloc[-1]
    final_chatgpt = float(chatgpt_totals['Total Equity'].iloc[-1])
    final_spx = sp500['SPX Value ($100 Invested)'].iloc[-1]
    ax.text(final_date, final_chatgpt + 0.3, f"+{final_chatgpt - 100:.1f}%", color='blue', fontsize=9)
    ax.text(final_date, final_spx + 0.9, f"+{final_spx - 100:.1f}%", color='orange', fontsize=9)

    ax.set_title("ChatGPT's Micro Cap Portfolio vs. S&P 500")
    ax.set_xlabel('Date')
    ax.set_ylabel('Value of $100 Investment')
    ax.legend()
    ax.grid(True)
    fig.autofmt_xdate()

    buf = BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    if not username or not email or not password:
        return jsonify({'message': 'Missing fields'}), 400
    pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    try:
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                      (username, email, pw_hash))
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({'message': 'User already exists'}), 409
    return jsonify({'message': 'User registered successfully'}), 201


@app.route('/login', methods=['GET'])
def login_page():
    return send_from_directory('templates', 'login.html')


@app.route('/signin', methods=['GET'])
def signin_page():
    return send_from_directory('templates', 'signin.html')


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    # Allow users to log in with either their username or email.
    identifier = data.get('identifier') or data.get('username')
    password = data.get('password')
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('SELECT id, username, password FROM users WHERE username=? OR email=?',
                  (identifier, identifier))
        row = c.fetchone()
    if row and bcrypt.check_password_hash(row[2], password):
        ensure_user_files(row[1])
        token = jwt.encode(
            {'id': row[0], 'exp': datetime.utcnow() + timedelta(hours=1)},
            app.config['SECRET_KEY'],
            algorithm='HS256',
        )
        return jsonify({'token': token})
    return jsonify({'message': 'Invalid credentials'}), 401


@app.route('/protected')
@token_required
def protected(user_id):
    return jsonify({'message': 'Protected content', 'user_id': user_id})


@app.route('/api/needs-cash')
@token_required
def api_needs_cash(user_id):
    """Check if the user must provide an initial cash balance."""
    return jsonify({'needs_cash': user_needs_cash(user_id)})


@app.route('/api/set-cash', methods=['POST'])
@token_required
def api_set_cash(user_id):
    """Persist a starting cash balance for a user (up to 100k)."""

    data = request.get_json() or {}
    try:
        amount = float(data.get('cash', 0))
    except (TypeError, ValueError):
        return jsonify({'message': 'Invalid cash amount'}), 400
    if amount < 0 or amount >= 100_000:
        return jsonify({'message': 'Cash must be between 0 and 100000'}), 400

    _, _, _, cash_file = get_user_files(user_id)
    with open(cash_file, 'w') as f:
        f.write(str(round(amount, 2)))
    return jsonify({'message': 'Cash balance set'})


def get_latest_portfolio(user_id: int):
    _, portfolio_csv, _, cash_file = get_user_files(user_id)
    if not os.path.exists(portfolio_csv) or os.path.getsize(portfolio_csv) == 0:
        cash = '0'
        if os.path.exists(cash_file):
            with open(cash_file) as f:
                cash = f.read().strip() or '0'
        return [], cash

    with open(portfolio_csv, newline='') as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return [], '0'

    non_total = [r for r in rows if r['Ticker'] != 'TOTAL']
    latest_date = max(r['Date'] for r in non_total) if non_total else rows[-1]['Date']
    positions: list[dict[str, str]] = []
    total_equity = None
    for row in rows:
        if row['Date'] == latest_date and row['Ticker'] != 'TOTAL':
            positions.append({
                'Ticker': row['Ticker'],
                'Shares': row['Shares'],
                'Cost_Basis': row['Cost Basis'],
                'Current_Price': row['Current Price'],
                'PnL': row['PnL'],
                'Stop_Loss': row['Stop Loss'],
            })
        elif row['Date'] == latest_date and row['Ticker'] == 'TOTAL':
            total_equity = row.get('Total Equity') or row.get('Cash Balance')

    if total_equity is None and os.path.exists(cash_file):
        with open(cash_file) as f:
            total_equity = f.read().strip() or '0'

    return positions, total_equity


def read_sample_portfolio():
    if not os.path.exists(SAMPLE_PORTFOLIO):
        return [], '0'
    with open(SAMPLE_PORTFOLIO, newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return [], '0'
    non_total = [r for r in rows if r['Ticker'] != 'TOTAL']
    latest_date = max(r['Date'] for r in non_total) if non_total else rows[-1]['Date']
    positions: list[dict[str, str]] = []
    total_equity = None
    for row in rows:
        if row['Date'] == latest_date and row['Ticker'] != 'TOTAL':
            positions.append({
                'Ticker': row['Ticker'],
                'Shares': row['Shares'],
                'Cost_Basis': row['Cost Basis'],
                'Current_Price': row['Current Price'],
                'PnL': row['PnL'],
            })
        elif row['Date'] == latest_date and row['Ticker'] == 'TOTAL':
            total_equity = row.get('Total Equity') or row.get('Cash Balance')
    return positions, total_equity


def read_sample_trade_log():
    if not os.path.exists(SAMPLE_TRADE_LOG):
        return []
    with open(SAMPLE_TRADE_LOG, newline='') as f:
        return list(csv.DictReader(f))


def read_sample_equity_history():
    history = []
    if os.path.exists(SAMPLE_PORTFOLIO):
        with open(SAMPLE_PORTFOLIO, newline='') as f:
            for row in csv.DictReader(f):
                if row.get('Ticker') == 'TOTAL':
                    history.append({'Date': row.get('Date'), 'Total Equity': row.get('Total Equity')})
    return history


@app.route('/api/trade', methods=['POST'])
@token_required
def api_trade(user_id):
    """Record a buy or sell trade for the logged-in user."""
    data = request.get_json() or {}
    ticker = (data.get('ticker') or '').upper()
    action = (data.get('action') or '').lower()
    try:
        price = float(data.get('price', 0))
        shares = float(data.get('shares', 0))
    except (TypeError, ValueError):
        return jsonify({'message': 'Invalid price or shares'}), 400
    reason = data.get('reason', '')
    stop_loss = data.get('stop_loss')
    if not ticker or action not in {'buy', 'sell'} or price <= 0 or shares <= 0:
        return jsonify({'message': 'Invalid trade data'}), 400
    if action == 'sell' and stop_loss not in (None, ''):
        return jsonify({'message': 'Cannot set a stop loss on a sell order'}), 400
    if action == 'buy':
        if stop_loss not in (None, ''):
            stop_loss_str = str(stop_loss).strip()
            if stop_loss_str.endswith('%'):
                try:
                    float(stop_loss_str[:-1])
                except ValueError:
                    return jsonify({'message': 'Invalid stop loss value'}), 400
            else:
                try:
                    float(stop_loss_str)
                except (TypeError, ValueError):
                    return jsonify({'message': 'Invalid stop loss value'}), 400
            stop_loss = stop_loss_str
        else:
            stop_loss = ''
    else:
        stop_loss = ''
    if not is_valid_ticker(ticker):
        return jsonify({'message': 'Invalid ticker'}), 400

    _, portfolio_csv, trade_log_csv, cash_file = get_user_files(user_id)

    cash = 0.0
    if os.path.exists(cash_file) and os.path.getsize(cash_file) > 0:
        with open(cash_file) as f:
            cash = float(f.read().strip() or 0)

    positions: dict[str, dict[str, Any]] = {}
    if os.path.exists(portfolio_csv) and os.path.getsize(portfolio_csv) > 0:
        with open(portfolio_csv, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Ticker') and row['Ticker'] != 'TOTAL':
                    positions[row['Ticker']] = {
                        'shares': float(row.get('Shares', 0) or 0),
                        'cost_basis': float(row.get('Cost Basis', 0) or 0),
                        'stop_loss': row.get('Stop Loss', ''),
                    }

    date = datetime.utcnow().strftime('%Y-%m-%d')
    if action == 'buy':
        cost = price * shares
        if cost > cash:
            return jsonify({'message': "You don't have enough cash to buy these shares"}), 400
        pos = positions.setdefault(ticker, {'shares': 0.0, 'cost_basis': 0.0, 'stop_loss': ''})
        pos['shares'] += shares
        pos['cost_basis'] += cost
        if stop_loss:
            pos['stop_loss'] = stop_loss
        cash -= cost
        log = {
            'Date': date,
            'Ticker': ticker,
            'Shares Bought': shares,
            'Buy Price': price,
            'Cost Basis': cost,
            'PnL': '',
            'Reason': reason,
            'Shares Sold': '',
            'Sell Price': '',
        }
    else:  # sell
        pos = positions.get(ticker)
        if not pos:
            return jsonify({'message': "You don't own this ticker"}), 400
        if pos['shares'] < shares:
            return jsonify({'message': "You're trying to sell more shares than you own"}), 400
        total_shares = pos['shares']
        cost_basis_per_share = pos['cost_basis'] / total_shares
        cost_basis = cost_basis_per_share * shares
        pnl = price * shares - cost_basis
        pos['shares'] -= shares
        pos['cost_basis'] -= cost_basis
        if pos['shares'] == 0:
            del positions[ticker]
        cash += price * shares
        log = {
            'Date': date,
            'Ticker': ticker,
            'Shares Bought': '',
            'Buy Price': '',
            'Cost Basis': cost_basis,
            'PnL': pnl,
            'Reason': reason,
            'Shares Sold': shares,
            'Sell Price': price,
        }

    file_exists = os.path.exists(trade_log_csv) and os.path.getsize(trade_log_csv) > 0
    with open(trade_log_csv, 'a', newline='') as f:
        fieldnames = ['Date', 'Ticker', 'Shares Bought', 'Buy Price', 'Cost Basis', 'PnL', 'Reason', 'Shares Sold', 'Sell Price']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(log)

    with open(cash_file, 'w') as f:
        f.write(str(round(cash, 2)))

    with open(portfolio_csv, 'w', newline='') as f:
        fieldnames = ['Date', 'Ticker', 'Shares', 'Cost Basis', 'Stop Loss', 'Current Price', 'Total Value', 'PnL', 'Action', 'Cash Balance', 'Total Equity']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        total_equity = cash
        for t, info in positions.items():
            total_equity += info['cost_basis']
            writer.writerow({
                'Date': date,
                'Ticker': t,
                'Shares': info['shares'],
                'Cost Basis': info['cost_basis'],
                'Stop Loss': info.get('stop_loss', ''),
                'Current Price': '',
                'Total Value': '',
                'PnL': '',
                'Action': 'BUY' if action == 'buy' and t == ticker else 'HOLD',
            })
        writer.writerow({
            'Date': date,
            'Ticker': 'TOTAL',
            'Shares': '',
            'Cost Basis': '',
            'Stop Loss': '',
            'Current Price': '',
            'Total Value': '',
            'PnL': '',
            'Action': '',
            'Cash Balance': cash,
            'Total Equity': total_equity,
        })

    return jsonify({'message': 'Trade recorded', 'cash': cash})


@app.route('/api/sample-portfolio')
def api_sample_portfolio():
    positions, total_equity = read_sample_portfolio()
    return jsonify({'positions': positions, 'total_equity': total_equity})


@app.route('/api/sample-trade-log')
def api_sample_trade_log():
    trades = read_sample_trade_log()
    return jsonify({'trades': trades})


@app.route('/api/sample-equity-history')
def api_sample_equity_history():
    return jsonify(read_sample_equity_history())


@app.route('/api/portfolio')
@token_required
def api_portfolio(user_id):
    positions, total_equity = get_latest_portfolio(user_id)
    return jsonify({'positions': positions, 'total_equity': total_equity})


def read_trade_log(user_id: int):
    _, _, trade_log_csv, _ = get_user_files(user_id)
    if not os.path.exists(trade_log_csv) or os.path.getsize(trade_log_csv) == 0:
        return []

    with open(trade_log_csv, newline='') as f:
        reader = csv.DictReader(f)
        entries = []
        for row in reader:
            if row.get('Shares Bought'):
                action = 'Buy'
                price = row.get('Buy Price')
                quantity = row.get('Shares Bought')
            else:
                action = 'Sell'
                price = row.get('Sell Price')
                quantity = row.get('Shares Sold')
            entries.append({
                'Date': row.get('Date'),
                'Ticker': row.get('Ticker'),
                'Action': action,
                'Price': price,
                'Quantity': quantity,
                'Reason': row.get('Reason'),
                'PnL': row.get('PnL'),
            })
    return entries


@app.route('/api/trade-log')
@token_required
def api_trade_log(user_id):
    return jsonify(read_trade_log(user_id))


def get_equity_history(user_id: int):
    _, portfolio_csv, _, cash_file = get_user_files(user_id)
    history = []
    if os.path.exists(portfolio_csv) and os.path.getsize(portfolio_csv) > 0:
        with open(portfolio_csv, newline='') as f:
            for row in csv.DictReader(f):
                if row['Ticker'] == 'TOTAL':
                    history.append({'Date': row['Date'], 'Total Equity': row.get('Total Equity')})
    else:
        cash = '0'
        if os.path.exists(cash_file):
            with open(cash_file) as f:
                cash = f.read().strip() or '0'
        history.append({'Date': datetime.today().strftime('%Y-%m-%d'), 'Total Equity': cash})
    return history


@app.route('/api/equity-history')
@token_required
def api_equity_history(user_id):
    return jsonify(get_equity_history(user_id))


def process_portfolio(user_id: int) -> None:
    """Process a user's portfolio using the trading script."""

    _, portfolio_csv, trade_log_csv, cash_file = get_user_files(user_id)

    # Ensure trading_script writes to the user's files
    ts.DATA_DIR = Path(os.path.dirname(portfolio_csv))
    ts.PORTFOLIO_CSV = Path(portfolio_csv)
    ts.TRADE_LOG_CSV = Path(trade_log_csv)

    holdings: list[dict[str, float | str]] = []
    if os.path.exists(portfolio_csv) and os.path.getsize(portfolio_csv) > 0:
        with open(portfolio_csv, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Ticker") and row["Ticker"] != "TOTAL":
                    shares = float(row.get("Shares", 0) or 0)
                    cost_basis = float(row.get("Cost Basis", 0) or 0)
                    stop_loss = float(row.get("Stop Loss", 0) or 0)
                    buy_price = cost_basis / shares if shares else 0.0
                    holdings.append(
                        {
                            "ticker": row["Ticker"],
                            "shares": shares,
                            "buy_price": buy_price,
                            "stop_loss": stop_loss,
                            "cost_basis": cost_basis,
                        }
                    )

    portfolio_df = pd.DataFrame(holdings)

    cash = 0.0
    if os.path.exists(cash_file) and os.path.getsize(cash_file) > 0:
        with open(cash_file) as f:
            cash = float(f.read().strip() or 0)

    # Process portfolio and update cash balance
    _, updated_cash = ts.process_portfolio(portfolio_df, cash)

    with open(cash_file, "w") as f:
        f.write(str(round(updated_cash, 2)))


@app.route('/api/process-portfolio', methods=['POST'])
@token_required
def api_process_portfolio(user_id):
    """Trigger portfolio processing for the authenticated user."""
    process_portfolio(user_id)
    return jsonify({'message': 'Portfolio processed'})


if __name__ == '__main__':
    app.run(debug=True)
