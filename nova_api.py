import sqlite3
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_PATH = "/home/pratik/nova/nova_runs.db"

@app.route("/runs")
def get_runs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM runs ORDER BY id ASC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/stats")
def get_stats():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT * FROM runs").fetchall()
    conn.close()
    total = len(rows)
    if total == 0:
        return jsonify({"total_runs": 0, "pass_rate": 0, "avg_time": 0, "avg_tokens": 0, "total_retries": 0})
    passed = sum(1 for r in rows if r[7])
    avg_time = round(sum(r[4] for r in rows) / total, 2)
    avg_tokens = round(sum(r[5] for r in rows) / total)
    total_retries = sum(r[8] for r in rows)
    return jsonify({"total_runs": total, "pass_rate": round(passed / total * 100), "avg_time": avg_time, "avg_tokens": avg_tokens, "total_retries": total_retries})

if __name__ == "__main__":
    app.run(port=5000, debug=False)
