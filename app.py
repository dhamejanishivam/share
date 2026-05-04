from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room
import sqlite3
import random
import string
from datetime import datetime, timedelta

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=120, ping_interval=25)

DB_FILE = "instadrop.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS shared_text
                     (pin TEXT PRIMARY KEY, content TEXT, expires_at DATETIME)''')
        conn.commit()

init_db()

def clean_db(conn):
    c = conn.cursor()
    c.execute("DELETE FROM shared_text WHERE expires_at <= datetime('now', 'utc')")
    conn.commit()

def generate_pin(conn):
    c = conn.cursor()
    while True:
        pin = ''.join(random.choices(string.digits, k=6))
        c.execute("SELECT 1 FROM shared_text WHERE pin = ?", (pin,))
        if not c.fetchone():
            return pin

@app.route('/')
def index():
    return render_template('index.html')

# --- TEXT SHARE API --- #
@app.route('/api/text/send', methods=['POST'])
def send_text():
    data = request.json
    content = data.get('text', '').strip()
    hours = float(data.get('hours', 1))

    if not content:
        return jsonify({'error': 'No text provided'}), 400
    if hours > 24 or hours < 0.1:
        hours = 1

    with sqlite3.connect(DB_FILE) as conn:
        clean_db(conn)
        pin = generate_pin(conn)
        expires_at = (datetime.utcnow() + timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
        
        c = conn.cursor()
        c.execute("INSERT INTO shared_text (pin, content, expires_at) VALUES (?, ?, ?)", 
                  (pin, content, expires_at))
        conn.commit()
        
    return jsonify({'pin': pin})


@app.route('/api/text/receive/<pin>', methods=['GET'])
def receive_text(pin):
    with sqlite3.connect(DB_FILE) as conn:
        clean_db(conn)
        c = conn.cursor()
        c.execute("SELECT content FROM shared_text WHERE pin = ?", (pin,))
        row = c.fetchone()
        
        if row:
            return jsonify({'text': row[0]})
        else:
            return jsonify({'error': 'Invalid or expired PIN'}), 404
        


# --- WEBRTC SIGNALING LOGIC --- #
@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    emit('peer_joined', data, to=room)


@socketio.on('signal')
def on_signal(data):
    emit('signal', data, to=data['room'])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5003)