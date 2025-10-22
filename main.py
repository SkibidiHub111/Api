from flask import Flask, request, jsonify, abort
import sqlite3, threading, time, datetime, os

DB = "/var/data/keys.db"
app = Flask(__name__)

def init_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL,
        hwid TEXT,
        months INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    ''')
    conn.commit()
    conn.close()

def add_key_to_db(key, hwid, months):
    created = datetime.datetime.utcnow()
    expires = created + datetime.timedelta(days=30 * months)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('INSERT INTO keys (key, hwid, months, created_at, expires_at) VALUES (?,?,?,?,?)',
              (key, hwid, months, created.isoformat(), expires.isoformat()))
    conn.commit()
    key_id = c.lastrowid
    conn.close()
    return key_id

def get_all_keys():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id,key,hwid,months,created_at,expires_at FROM keys')
    rows = c.fetchall()
    conn.close()
    keys = []
    for r in rows:
        keys.append({
            "id": r[0],
            "key": r[1],
            "hwid": r[2],
            "months": r[3],
            "created_at": r[4],
            "expires_at": r[5]
        })
    return keys

def delete_key(key_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('DELETE FROM keys WHERE id = ?', (key_id,))
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return jsonify({"status": "ok", "message": "API online"}), 200

@app.route('/keys', methods=['POST'])
def post_key():
    j = request.get_json()
    if not j: abort(400)
    key = j.get('key')
    months = int(j.get('months', 1))
    hwid_bypass = bool(j.get('hwid_bypass', False))
    if not key:
        return jsonify({"error": "key required"}), 400
    hwid = "BYPASS" if hwid_bypass else None
    key_id = add_key_to_db(key, hwid, months)
    return jsonify({"status": "ok", "id": key_id}), 201

@app.route('/keys', methods=['GET'])
def list_keys():
    keys = get_all_keys()
    return jsonify(keys), 200

@app.route('/keys/<int:key_id>', methods=['PATCH'])
def patch_key(key_id):
    j = request.get_json()
    if not j: abort(400)
    if 'hwid' in j:
        hw = j['hwid']
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('UPDATE keys SET hwid = ? WHERE id = ?', (hw, key_id))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"}), 200
    return jsonify({"error": "no valid field"}), 400

@app.route('/keys/<int:key_id>', methods=['DELETE'])
def del_key(key_id):
    delete_key(key_id)
    return jsonify({"status": "deleted"}), 200

@app.route('/verify', methods=['GET'])
def verify_key():
    key = request.args.get('key')
    hwid = request.args.get('hwid')
    if not key:
        return jsonify({"status": "error", "message": "missing key"}), 400
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT id, hwid, expires_at FROM keys WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"status": "invalid", "message": "key not found"}), 404
    key_id, saved_hwid, exp = row
    if datetime.datetime.fromisoformat(exp) < datetime.datetime.utcnow():
        return jsonify({"status": "expired", "message": "key expired"}), 403
    if saved_hwid == "BYPASS":
        return jsonify({"status": "ok", "message": "key valid (bypass)", "id": key_id}), 200
    if saved_hwid and hwid and saved_hwid != hwid:
        return jsonify({"status": "invalid", "message": "hwid mismatch"}), 403
    if not saved_hwid and hwid:
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute('UPDATE keys SET hwid = ? WHERE id = ?', (hwid, key_id))
        conn.commit()
        conn.close()
    return jsonify({"status": "ok", "message": "key valid", "id": key_id}), 200

def cleanup_loop():
    while True:
        try:
            now = datetime.datetime.utcnow().isoformat()
            conn = sqlite3.connect(DB)
            c = conn.cursor()
            c.execute('DELETE FROM keys WHERE expires_at <= ?', (now,))
            conn.commit()
            conn.close()
        except Exception:
            pass
        time.sleep(3600)

if __name__ == '__main__':
    init_db()
    threading.Thread(target=cleanup_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
