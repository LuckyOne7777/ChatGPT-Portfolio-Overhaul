from flask import Flask, request, jsonify, send_from_directory
from flask_bcrypt import Bcrypt
import sqlite3
import jwt
from datetime import datetime, timedelta
from functools import wraps
import os

app = Flask(__name__, static_folder=None)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-this-secret')
bcrypt = Bcrypt(app)

DATABASE = 'users.db'

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
def serve_index():
    return send_from_directory('templates', 'login.html')


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


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('SELECT id, password FROM users WHERE email=?', (email,))
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


if __name__ == '__main__':
    app.run(debug=True)
