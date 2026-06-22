#!/usr/bin/env python3
"""Network Bandwidth Monitoring CLI Tool"""
import argparse
import sqlite3
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
import psutil
import sys

DATABASE_PATH = Path.home() / ".network_monitor" / "bandwidth.db"
LOG_PATH = Path.home() / ".network_monitor" / "monitor.log"

# Ensure directories exist before configuring logging
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class BandwidthStats(NamedTuple):
    timestamp: str
    bytes_sent: int
    bytes_recv: int
    sent_mb: float
    recv_mb: float

def init_database(db_path: Path) -> None:
    """Initialize SQLite database with required tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bandwidth_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                bytes_sent INTEGER NOT NULL,
                bytes_recv INTEGER NOT NULL,
                sent_mb REAL NOT NULL,
                recv_mb REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON bandwidth_logs(timestamp)")
        conn.commit()
        logger.info(f"Database initialized at {db_path}")
    except sqlite3.Error as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    finally:
        conn.close()

def get_network_stats() -> BandwidthStats:
    """Collect current network I/O statistics."""
    try:
        net_io = psutil.net_io_counters()
        timestamp = datetime.now().isoformat()
        return BandwidthStats(
            timestamp=timestamp,
            bytes_sent=net_io.bytes_sent,
            bytes_recv=net_io.bytes_recv,
            sent_mb=round(net_io.bytes_sent / (1024 * 1024), 2),
            recv_mb=round(net_io.bytes_recv / (1024 * 1024), 2)
        )
    except Exception as e:
        logger.error(f"Failed to collect network stats: {e}")
        raise

def log_to_database(db_path: Path, stats: BandwidthStats) -> None:
    """Store bandwidth statistics in SQLite database."""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO bandwidth_logs (timestamp, bytes_sent, bytes_recv, sent_mb, recv_mb) VALUES (?, ?, ?, ?, ?",
                (stats.timestamp, stats.bytes_sent, stats.bytes_recv, stats.sent_mb, stats.recv_mb)
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Failed to log to database: {e}")
        raise

def check_threshold(stats: BandwidthStats, threshold_mb: float, interval: int) -> bool:
    """Check if bandwidth usage exceeds threshold."""
    if threshold_mb <= 0:
        return False
    bytes_per_second = (stats.bytes_sent + stats.bytes_recv) / interval if interval > 0 else 0
    mbps = bytes_per_second / (1024 * 1024)
    if mbps > threshold_mb:
        logger.warning(f"ALERT: Bandwidth usage {mbps:.2f} MB/s exceeds threshold {threshold_mb} MB/s")
        return True
    return False

def monitor_continuous(db_path: Path, interval: int, threshold_mb: float) -> None:
    """Continuously monitor network bandwidth."""
    logger.info(f"Starting continuous monitoring (interval: {interval}s, threshold: {threshold_mb} MB/s)")
    try:
        while True:
            stats = get_network_stats()
            log_to_database(db_path, stats)
            check_threshold(stats, threshold_mb, interval)
            logger.info(f"Logged: Sent={stats.sent_mb}MB, Recv={stats.recv_mb}MB")
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    except Exception as e:
        logger.error(f"Monitoring error: {e}")
        raise

def monitor_once(db_path: Path, threshold_mb: float) -> BandwidthStats:
    """Monitor network bandwidth once."""
    stats = get_network_stats()
    log_to_database(db_path, stats)
    check_threshold(stats, threshold_mb, 1)
    return stats

def show_stats(db_path: Path, limit: int = 10) -> list[tuple]:
    """Retrieve recent bandwidth statistics from database."""
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT timestamp, bytes_sent, bytes_recv, sent_mb, recv_mb FROM bandwidth_logs ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve stats: {e}")
        return []

def validate_positive(value: str) -> float:
    """Validate positive numeric argument."""
    try:
        fval = float(value)
        if fval < 0:
            raise ValueError("Value must be non-negative")
        return fval
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Invalid value: {value}") from e

def validate_interval(value: str) -> int:
    """Validate positive integer interval."""
    try:
        ival = int(value)
        if ival <= 0:
            raise ValueError("Interval must be positive")
        return ival
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Invalid interval: {value}") from e

def print_stats(records: list[tuple]) -> None:
    """Print statistics in formatted table."""
    if not records:
        print("No records found")
        return
    print(f"{'Timestamp':<20} {'Sent (MB)':>12} {'Recv (MB)':>12} {'Total (MB)':>12}")
    print("-" * 56)
    for r in records:
        total = (r[1] + r[2]) / (1024 * 1024)
        print(f"{r[0]:<20} {r[3]:>12.2f} {r[4]:>12.2f} {total:>12.2f}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Network Bandwidth Monitoring CLI Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    init_parser = subparsers.add_parser("init", help="Initialize database")
    init_parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help="Database path")
    
    start_parser = subparsers.add_parser("start", help="Start continuous monitoring")
    start_parser.add_argument("--interval", type=validate_interval, default=60, help="Monitoring interval in seconds")
    start_parser.add_argument("--threshold", type=validate_positive, default=0.0, help="Alert threshold in MB/s")
    start_parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help="Database path")
    
    once_parser = subparsers.add_parser("once", help="Run monitoring once")
    once_parser.add_argument("--threshold", type=validate_positive, default=0.0, help="Alert threshold in MB/s")
    once_parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help="Database path")
    
    stats_parser = subparsers.add_parser("stats", help="Show recent statistics")
    stats_parser.add_argument("--limit", type=int, default=10, help="Number of records to show")
    stats_parser.add_argument("--db-path", type=Path, default=DATABASE_PATH, help="Database path")
    
    args = parser.parse_args()
    
    commands = {
        "init": lambda: init_database(args.db_path),
        "start": lambda: monitor_continuous(args.db_path, args.interval, args.threshold),
        "once": lambda: (print_stats([monitor_once(args.db_path, args.threshold)] if (monitor_once(args.db_path, args.threshold), True)[1] else None), logger.info("Single monitoring completed"))[1],
        "stats": lambda: print_stats(show_stats(args.db_path, args.limit))
    }
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        commands[args.command]()
    except KeyError:
        parser.print_help()

if __name__ == "__main__":
    main()