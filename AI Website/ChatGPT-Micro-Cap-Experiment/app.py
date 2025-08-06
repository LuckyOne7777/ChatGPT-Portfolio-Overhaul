from flask import Flask, request, jsonify, send_from_directory
from flask_bcrypt import Bcrypt
import sqlite3
import jwt
from datetime import datetime, timedelta
from functools import wraps
import os
import csv

app = Flask(__name__, static_folder=None)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-this-secret')
bcrypt = Bcrypt(app)

DATABASE = 'users.db'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'Scripts and CSV Files')
PORTFOLIO_CSV = os.path.join(DATA_DIR, 'chatgpt_portfolio_update.csv')
TRADE_LOG_CSV = os.path.join(DATA_DIR, 'chatgpt_trade_log.csv')

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
        c.execute('SELECT id, password FROM users WHERE username=? OR email=?',
                  (identifier, identifier))
        row = c.fetchone()
    if row and bcrypt.check_password_hash(row[1], password):
        token = jwt.encode({'id': row[0], 'exp': datetime.utcnow() + timedelta(hours=1)},
                           app.config['SECRET_KEY'], algorithm='HS256')
        return jsonify({'token': token})
    return jsonify({'message': 'Invalid credentials'}), 401


@app.route('/protected')
@token_required
def protected(user_id):
    return jsonify({'message': 'Protected content', 'user_id': user_id})


def get_latest_portfolio():
    with open(PORTFOLIO_CSV, newline='') as f:
        rows = list(csv.DictReader(f))
    latest_date = max(row['Date'] for row in rows if row['Ticker'] != 'TOTAL')
    positions = []
    total_equity = None
    for row in rows:
        if row['Date'] == latest_date and row['Ticker'] != 'TOTAL':
            positions.append({
                'Ticker': row['Ticker'],
                'Shares': row['Shares'],
                'Cost_Basis': row['Cost Basis'],
                'Current_Price': row['Current Price'],
                'PnL': row['PnL'],
                'Stop_Loss': row['Stop Loss']
            })
        elif row['Date'] == latest_date and row['Ticker'] == 'TOTAL':
            total_equity = row.get('Total Equity')
    return positions, total_equity


@app.route('/api/portfolio')
def api_portfolio():
    positions, total_equity = get_latest_portfolio()
    return jsonify({'positions': positions, 'total_equity': total_equity})


def read_trade_log():
    with open(TRADE_LOG_CSV, newline='') as f:
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
                'Reason': row.get('Reason')
            })
    return entries


@app.route('/api/trade-log')
def api_trade_log():
    return jsonify(read_trade_log())


if __name__ == '__main__':
    app.run(debug=True)
