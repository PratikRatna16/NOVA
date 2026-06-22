#!/usr/bin/env python3
"""System Resource Monitor CLI Tool"""

import argparse
import sqlite3
import logging
import time
import shutil
import threading
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
import psutil

# Configuration defaults
DEFAULT_INTERVAL = 5
DEFAULT_THRESHOLDS = {"CPU": 80.0, "Memory": 80.0, "Disk": 90.0}
DEFAULT_DB_PATH = Path.home() / ".resource_monitor" / "monitor.db"
DEFAULT_LOG_PATH = Path.home() / ".resource_monitor" / "alerts.log"

# Database schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS Resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    unit TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    value REAL NOT NULL,
    FOREIGN KEY (resource_id) REFERENCES Resources(id)
);

CREATE TABLE IF NOT EXISTS Alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    threshold REAL NOT NULL,
    value REAL NOT NULL,
    FOREIGN KEY (resource_id) REFERENCES Resources(id)
);

CREATE TABLE IF NOT EXISTS Config (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class ResourceMonitor:
    """Monitors system resources (CPU, Memory, Disk)"""
    
    def __init__(self, db_path: Path, log_path: Path, thresholds: dict = None):
        self.db_path = db_path
        self.thresholds = thresholds or DEFAULT_THRESHOLDS.copy()
        self._running = False
        self._monitor_thread = None
        self._setup_logging(log_path)
        self._init_database()
    
    def _setup_logging(self, log_path: Path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.FileHandler(log_path), logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)
    
    @contextmanager
    def _get_db_connection(self, retries: int = 3):
        conn = None
        for attempt in range(retries):
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(self.db_path))
                conn.row_factory = sqlite3.Row
                yield conn
                break
            except sqlite3.Error as e:
                if attempt == retries - 1:
                    self.logger.error(f"Database connection failed after {retries} attempts: {e}")
                    raise
                time.sleep(0.5)
        else:
            yield None
    
    def _init_database(self):
        with self._get_db_connection() as conn:
            if conn:
                conn.executescript(SCHEMA)
                resources = [
                    ("CPU", "percentage"),
                    ("Memory", "percentage"),
                    ("Disk", "percentage")
                ]
                conn.executemany("INSERT OR IGNORE INTO Resources (name, unit) VALUES (?, ?)", resources)
                conn.commit()
    
    def _get_resource_id(self, name: str) -> int:
        with self._get_db_connection() as conn:
            if conn:
                cur = conn.execute("SELECT id FROM Resources WHERE name = ?", (name,))
                row = cur.fetchone()
                return row["id"] if row else None
    
    def collect_metrics(self) -> dict:
        try:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/").percent
            return {"CPU": cpu, "Memory": memory, "Disk": disk}
        except Exception as e:
            self.logger.error(f"Failed to collect metrics: {e}")
            return {}
    
    def _check_thresholds(self, metrics: dict):
        for name, value in metrics.items():
            threshold = self.thresholds.get(name)
            if threshold and value > threshold:
                resource_id = self._get_resource_id(name)
                if resource_id:
                    with self._get_db_connection() as conn:
                        if conn:
                            conn.execute(
                                "INSERT INTO Alerts (resource_id, timestamp, threshold, value) VALUES (?, ?, ?, ?)",
                                (resource_id, datetime.now().isoformat(), threshold, value)
                            )
                            conn.commit()
                    self.logger.warning(f"{name} usage {value:.1f}% exceeds threshold {threshold}%")
    
    def _store_metrics(self, metrics: dict):
        timestamp = datetime.now().isoformat()
        with self._get_db_connection() as conn:
            if conn:
                for name, value in metrics.items():
                    resource_id = self._get_resource_id(name)
                    if resource_id:
                        conn.execute(
                            "INSERT INTO Measurements (resource_id, timestamp, value) VALUES (?, ?, ?)",
                            (resource_id, timestamp, value)
                        )
                conn.commit()
    
    def _monitor_loop(self, interval: int):
        while self._running:
            metrics = self.collect_metrics()
            if metrics:
                self._store_metrics(metrics)
                self._check_thresholds(metrics)
            time.sleep(interval)
    
    def start(self, interval: int = DEFAULT_INTERVAL):
        if self._running:
            print("Monitor already running")
            return
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval,), daemon=True)
        self._monitor_thread.start()
        print(f"Monitoring started with {interval}s interval")
    
    def stop(self):
        if not self._running:
            print("Monitor not running")
            return
        self._running = False
        self._monitor_thread.join(timeout=2)
        print("Monitoring stopped")
    
    def status(self) -> dict:
        return {"running": self._running}
    
    def set_threshold(self, name: str, value: float):
        if name not in self.thresholds:
            print(f"Unknown resource: {name}")
            return
        self.thresholds[name] = value
        print(f"Threshold set: {name} = {value}%")
    
    def get_current_metrics(self) -> dict:
        return self.collect_metrics()
    
    def get_alerts(self, limit: int = 10) -> list:
        with self._get_db_connection() as conn:
            if conn:
                cur = conn.execute("""
                    SELECT r.name, a.timestamp, a.threshold, a.value 
                    FROM Alerts a 
                    JOIN Resources r ON a.resource_id = r.id 
                    ORDER BY a.timestamp DESC LIMIT ?
                """, (limit,))
                return [dict(row) for row in cur.fetchall()]
        return []
    
    def get_measurements(self, limit: int = 100) -> list:
        with self._get_db_connection() as conn:
            if conn:
                cur = conn.execute("""
                    SELECT r.name, m.timestamp, m.value 
                    FROM Measurements m 
                    JOIN Resources r ON m.resource_id = r.id 
                    ORDER BY m.timestamp DESC LIMIT ?
                """, (limit,))
                return [dict(row) for row in cur.fetchall()]
        return []


def generate_report(monitor: ResourceMonitor, hours: int = 24) -> str:
    measurements = monitor.get_measurements(limit=hours * 120)  # ~2 samples per minute
    
    if not measurements:
        return "No data available for report"
    
    from collections import defaultdict
    import statistics
    
    data_by_resource = defaultdict(list)
    for m in measurements:
        data_by_resource[m["name"]].append(m["value"])
    
    lines = [f"\n{'='*50}", f"Resource Usage Report (Last {hours} hours)", f"{'='*50}"]
    
    for resource in ["CPU", "Memory", "Disk"]:
        values = data_by_resource.get(resource, [])
        if values:
            peak = max(values)
            avg = statistics.mean(values)
            min_val = min(values)
            lines.append(f"\n{resource}:")
            lines.append(f"  Peak:   {peak:.1f}%")
            lines.append(f"  Average: {avg:.1f}%")
            lines.append(f"  Minimum: {min_val:.1f}%")
        else:
            lines.append(f"\n{resource}: No data available")
    
    alerts = monitor.get_alerts(limit=20)
    if alerts:
        lines.append(f"\nRecent Alerts ({len(alerts)} shown):")
        for alert in alerts[:10]:
            lines.append(f"  [{alert['name']}] {alert['timestamp']}: {alert['value']:.1f}% > {alert['threshold']}%")
    
    lines.append(f"\n{'='*50}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="System Resource Monitor CLI Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start monitoring")
    start_parser.add_argument("-i", "--interval", type=int, default=DEFAULT_INTERVAL,
                              help=f"Monitoring interval in seconds (default: {DEFAULT_INTERVAL})")
    
    # Stop command
    subparsers.add_parser("stop", help="Stop monitoring")
    
    # Status command
    subparsers.add_parser("status", help="Show monitor status")
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Generate summary report")
    report_parser.add_argument("-H", "--hours", type=int, default=24,
                               help="Hours of data to include in report (default: 24)")
    
    # Set threshold command
    threshold_parser = subparsers.add_parser("set-threshold", help="Set resource threshold")
    threshold_parser.add_argument("resource", choices=["CPU", "Memory", "Disk"],
                                  help="Resource name")
    threshold_parser.add_argument("value", type=float, help="Threshold value (percentage)")
    
    # Metrics command
    subparsers.add_parser("metrics", help="Show current resource metrics")
    
    # Alerts command
    alerts_parser = subparsers.add_parser("alerts", help="Show recent alerts")
    alerts_parser.add_argument("-n", "--number", type=int, default=10,
                               help="Number of alerts to show (default: 10)")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    monitor = ResourceMonitor(DEFAULT_DB_PATH, DEFAULT_LOG_PATH)
    
    command_handlers = {
        "start": lambda: monitor.start(args.interval),
        "stop": lambda: monitor.stop(),
        "status": lambda: print(f"Status: {'Running' if monitor.status()['running'] else 'Stopped'}"),
        "report": lambda: print(generate_report(monitor, args.hours)),
        "set-threshold": lambda: monitor.set_threshold(args.resource, args.value),
        "metrics": lambda: print(monitor.get_current_metrics()),
        "alerts": lambda: print(monitor.get_alerts(args.number)),
    }
    
    try:
        handler = command_handlers.get(args.command)
        if handler:
            handler()
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()