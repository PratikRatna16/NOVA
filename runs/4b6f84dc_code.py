#!/usr/bin/env python3
"""Network Bandwidth Monitor CLI Tool"""

import argparse
import json
import sqlite3
import smtplib
import time
import sys
from pathlib import Path
from datetime import datetime
from email.message import EmailMessage
from dataclasses import dataclass
from typing import Optional

import psutil

DEFAULT_CONFIG = {
    "interval": 10,
    "threshold": 100,
    "alert_email": "",
    "smtp_server": "localhost",
    "smtp_port": 25,
    "db_path": "bandwidth.db"
}

MAX_RETRIES = 3


@dataclass
class Config:
    interval: int
    threshold: int
    alert_email: str
    smtp_server: str
    smtp_port: int
    db_path: str


def load_config(config_path: Optional[str] = None) -> Config:
    config = DEFAULT_CONFIG.copy()
    if config_path and Path(config_path).exists():
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                config.update({k: v for k, v in user_config.items() if k in config})
        except (json.JSONDecodeError, IOError):
            pass
    return Config(**config)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Network Bandwidth Monitor")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument("--interval", type=int, help="Override logging interval in seconds")
    parser.add_argument("--threshold", type=int, help="Override bandwidth threshold in MB/s")
    parser.add_argument("--once", action="store_true", help="Run single monitoring cycle")
    return parser.parse_args()


def init_database(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bandwidth_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            bytes_sent INTEGER NOT NULL,
            bytes_recv INTEGER NOT NULL,
            bandwidth REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            message TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def log_bandwidth(conn: sqlite3.Connection, bytes_sent: int, bytes_recv: int, bandwidth: float) -> None:
    conn.execute(
        "INSERT INTO bandwidth_log (timestamp, bytes_sent, bytes_recv, bandwidth) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), bytes_sent, bytes_recv, bandwidth)
    )
    conn.commit()


def log_alert(conn: sqlite3.Connection, message: str) -> None:
    conn.execute(
        "INSERT INTO alerts (timestamp, message) VALUES (?, ?)",
        (datetime.now().isoformat(), message)
    )
    conn.commit()


def send_alert(config: Config, message: str) -> bool:
    if not config.alert_email or not config.smtp_server:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = "Network Bandwidth Alert"
        msg["From"] = f"bandwidth-monitor@{datetime.now().strftime('%Y%m%d')}"
        msg["To"] = config.alert_email
        msg.set_content(message)
        with smtplib.SMTP(config.smtp_server, config.smtp_port, timeout=10) as server:
            server.send_message(msg)
        return True
    except Exception:
        return False


def get_network_stats() -> tuple[int, int]:
    try:
        net = psutil.net_io_counters()
        return net.bytes_sent, net.bytes_recv
    except Exception:
        return 0, 0


def monitor_cycle(config: Config, conn: sqlite3.Connection, prev_stats: tuple[int, int]) -> float:
    bytes_sent, bytes_recv = get_network_stats()
    if prev_stats != (0, 0):  # Skip first iteration
        bandwidth = ((bytes_sent + bytes_recv) - (prev_stats[0] + prev_stats[1])) / config.interval / (1024 * 1024)
        bandwidth = max(0, bandwidth)  # Ensure non-negative
        log_bandwidth(conn, bytes_sent, bytes_recv, bandwidth)
        if bandwidth > config.threshold:
            alert_msg = f"Bandwidth {bandwidth:.2f} MB/s exceeds threshold {config.threshold} MB/s"
            log_alert(conn, alert_msg)
            send_alert(config, alert_msg)
        return bandwidth
    return 0.0


def run_monitor(config: Config, once: bool = False) -> None:
    conn = None
    for attempt in range(MAX_RETRIES):
        try:
            conn = init_database(config.db_path)
            break
        except sqlite3.Error:
            if attempt == MAX_RETRIES - 1:
                print("Failed to initialize database after retries", file=sys.stderr)
                sys.exit(1)
            time.sleep(1)
    
    prev_stats = (0, 0)
    try:
        while True:
            bandwidth = monitor_cycle(config, conn, prev_stats)
            prev_stats = get_network_stats()
            if bandwidth > 0:
                print(f"{datetime.now().isoformat()} - Bandwidth: {bandwidth:.2f} MB/s")
            if once:
                break
            time.sleep(config.interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    finally:
        if conn:
            conn.close()


def show_stats(config: Config) -> None:
    try:
        conn = sqlite3.connect(config.db_path)
        cur = conn.execute("SELECT COUNT(*), AVG(bandwidth), MAX(bandwidth) FROM bandwidth_log")
        count, avg, max_bw = cur.fetchone()
        print(f"Total samples: {count or 0}")
        print(f"Average bandwidth: {(avg or 0):.2f} MB/s")
        print(f"Peak bandwidth: {(max_bw or 0):.2f} MB/s")
        
        cur = conn.execute("SELECT COUNT(*) FROM alerts")
        alert_count = cur.fetchone()[0]
        print(f"Total alerts: {alert_count}")
        conn.close()
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)


def main():
    args = parse_args()
    config = load_config(args.config)
    
    if args.interval:
        config.interval = args.interval
    if args.threshold:
        config.threshold = args.threshold
    
    if args.once:
        run_monitor(config, once=True)
    else:
        run_monitor(config)


if __name__ == "__main__":
    main()