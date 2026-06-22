#!/usr/bin/env python3
"""System Resource Monitor CLI Tool"""

import argparse
import sqlite3
import json
import csv
import time
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

try:
    import psutil
except ImportError:
    print("Error: psutil library required. Install with: pip install psutil")
    exit(1)

# Configuration defaults
DEFAULT_CONFIG = {
    "monitoring_interval": 60,
    "thresholds": {"cpu": 80, "memory": 80, "disk": 80},
    "database_path": "resource_monitor.db",
    "report_format": "json",
    "reconnect_interval": 300
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class SystemMonitor:
    def __init__(self, config_path: Optional[Path] = None):
        self.config = self.load_config(config_path or Path("monitor_config.json"))
        self.db_path = Path(self.config["database_path"])
        self.db_connected = False
        self.db_connection: Optional[sqlite3.Connection] = None
        self.last_reconnect_attempt = 0
        self.init_database()

    def load_config(self, path: Path) -> Dict[str, Any]:
        try:
            if path.exists():
                with open(path, 'r') as f:
                    config = json.load(f)
                # Merge with defaults
                return {**DEFAULT_CONFIG, **config}
        except Exception as e:
            logger.error(f"Failed to load config: {e}. Using defaults.")
        return DEFAULT_CONFIG.copy()

    def init_database(self):
        try:
            self.db_connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.db_connection.execute("""
                CREATE TABLE IF NOT EXISTS resource_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    usage_percentage INTEGER NOT NULL,
                    threshold_percentage INTEGER NOT NULL
                )
            """)
            self.db_connection.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON resource_usage(timestamp)")
            self.db_connection.commit()
            self.db_connected = True
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            self.db_connected = False

    def reconnect_database(self) -> bool:
        current_time = time.time()
        if current_time - self.last_reconnect_attempt < self.config["reconnect_interval"]:
            return False
        
        self.last_reconnect_attempt = current_time
        if self.db_connection:
            try:
                self.db_connection.close()
            except:
                pass
        
        self.init_database()
        return self.db_connected

    @contextmanager
    def get_cursor(self):
        if not self.db_connected:
            yield None
            return
        
        try:
            cursor = self.db_connection.cursor()
            yield cursor
            self.db_connection.commit()
        except Exception as e:
            logger.error(f"Database operation failed: {e}")
            self.db_connected = False
            yield None

    def store_usage(self, resource_type: str, usage: int, threshold: int):
        if not self.db_connected:
            if not self.reconnect_database():
                logger.warning("Skipping data storage: database unavailable")
                return
        
        try:
            with self.get_cursor() as cursor:
                if cursor:
                    cursor.execute(
                        "INSERT INTO resource_usage (timestamp, resource_type, usage_percentage, threshold_percentage) VALUES (?, ?, ?, ?)",
                        (datetime.now().isoformat(), resource_type, usage, threshold)
                    )
        except Exception as e:
            logger.error(f"Failed to store usage data: {e}")

    def log_alert(self, resource_type: str, usage: int, threshold: int):
        try:
            logger.warning(f"ALERT: {resource_type} usage {usage}% exceeds threshold {threshold}%")
            self.store_usage(resource_type, usage, threshold)
        except Exception as e:
            logger.error(f"Failed to log alert: {e}")

    def get_cpu_usage(self) -> int:
        try:
            return int(psutil.cpu_percent(interval=1))
        except Exception as e:
            logger.error(f"Failed to get CPU usage: {e}")
            return 0

    def get_memory_usage(self) -> int:
        try:
            return int(psutil.virtual_memory().percent)
        except Exception as e:
            logger.error(f"Failed to get memory usage: {e}")
            return 0

    def get_disk_usage(self) -> int:
        try:
            return int(psutil.disk_usage('/').percent)
        except Exception as e:
            logger.error(f"Failed to get disk usage: {e}")
            return 0

    def check_thresholds(self, cpu: int, memory: int, disk: int):
        thresholds = self.config["thresholds"]
        
        if cpu > thresholds.get("cpu", 80):
            self.log_alert("CPU", cpu, thresholds["cpu"])
        
        if memory > thresholds.get("memory", 80):
            self.log_alert("memory", memory, thresholds["memory"])
        
        if disk > thresholds.get("disk", 80):
            self.log_alert("disk", disk, thresholds["disk"])

    def collect_sample(self):
        cpu = self.get_cpu_usage()
        memory = self.get_memory_usage()
        disk = self.get_disk_usage()
        
        thresholds = self.config["thresholds"]
        
        # Store all samples
        self.store_usage("CPU", cpu, thresholds.get("cpu", 80))
        self.store_usage("memory", memory, thresholds.get("memory", 80))
        self.store_usage("disk", disk, thresholds.get("disk", 80))
        
        # Check and alert if thresholds exceeded
        self.check_thresholds(cpu, memory, disk)
        
        logger.info(f"Collected: CPU={cpu}%, Memory={memory}%, Disk={disk}%")

    def monitor_loop(self, duration: Optional[int] = None):
        start_time = time.time()
        interval = self.config.get("monitoring_interval", 60)
        
        while True:
            if duration and (time.time() - start_time) >= duration:
                logger.info("Monitoring duration completed")
                break
            
            self.collect_sample()
            time.sleep(interval)

    def generate_report(self, hours: int = 24, output_path: Optional[Path] = None) -> str:
        if not self.db_connected:
            if not self.reconnect_database():
                logger.error("Cannot generate report: database unavailable")
                return ""
        
        try:
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            with self.get_cursor() as cursor:
                if not cursor:
                    logger.error("Cannot generate report: no database cursor")
                    return ""
                
                stats = {}
                for resource in ["CPU", "memory", "disk"]:
                    cursor.execute(
                        """SELECT MAX(usage_percentage), AVG(usage_percentage) 
                           FROM resource_usage 
                           WHERE timestamp >= ? AND resource_type = ?""",
                        (cutoff, resource)
                    )
                    row = cursor.fetchone()
                    stats[resource] = {"peak": row[0] or 0, "average": round(row[1] or 0, 2)}
            
            report_data = {
                "period_hours": hours,
                "generated_at": datetime.now().isoformat(),
                "statistics": {
                    "cpu": stats["CPU"],
                    "memory": stats["memory"],
                    "disk": stats["disk"]
                }
            }
            
            if self.config["report_format"] == "json":
                report = json.dumps(report_data, indent=2)
            else:
                output = []
                output.append("resource_type,peak_usage,average_usage")
                for resource, key in [("cpu", "CPU"), ("memory", "memory"), ("disk", "disk")]:
                    output.append(f"{resource},{stats[key]['peak']},{stats[key]['average']}")
                report = "\n".join(output)
            
            if output_path:
                output_path = Path(output_path)
                output_path.write_text(report)
                logger.info(f"Report saved to {output_path}")
            
            return report
            
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return ""

    def cleanup(self):
        if self.db_connection:
            try:
                self.db_connection.close()
            except Exception as e:
                logger.error(f"Database cleanup failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="System Resource Monitor CLI Tool")
    parser.add_argument("--duration", type=int, help="Monitoring duration in seconds")
    parser.add_argument("--interval", type=int, help="Monitoring interval in seconds")
    parser.add_argument("--cpu-threshold", type=int, help="CPU alert threshold percentage")
    parser.add_argument("--memory-threshold", type=int, help="Memory alert threshold percentage")
    parser.add_argument("--disk-threshold", type=int, help="Disk alert threshold percentage")
    parser.add_argument("--report", action="store_true", help="Generate summary report")
    parser.add_argument("--report-hours", type=int, default=24, help="Hours of data for report")
    parser.add_argument("--report-output", type=str, help="Output file path for report")
    parser.add_argument("--report-format", choices=["json", "csv"], help="Report format")
    parser.add_argument("--config", type=str, help="Custom configuration file path")
    
    args = parser.parse_args()
    
    config_path = Path(args.config) if args.config else Path("monitor_config.json")
    monitor = SystemMonitor(config_path)
    
    # Apply command-line overrides
    if args.interval:
        monitor.config["monitoring_interval"] = args.interval
    if args.cpu_threshold:
        monitor.config["thresholds"]["cpu"] = args.cpu_threshold
    if args.memory_threshold:
        monitor.config["thresholds"]["memory"] = args.memory_threshold
    if args.disk_threshold:
        monitor.config["thresholds"]["disk"] = args.disk_threshold
    if args.report_format:
        monitor.config["report_format"] = args.report_format
    
    # Handle report generation
    if args.report:
        report = monitor.generate_report(
            hours=args.report_hours,
            output_path=Path(args.report_output) if args.report_output else None
        )
        if report:
            print(report)
        return
    
    try:
        monitor.monitor_loop(duration=args.duration)
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    finally:
        monitor.cleanup()


if __name__ == "__main__":
    main()