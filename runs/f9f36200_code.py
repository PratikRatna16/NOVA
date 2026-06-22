import argparse
import sqlite3
import threading
import time
import re
from datetime import datetime
from queue import Queue
from typing import Optional, List, Tuple
import requests
from requests.exceptions import RequestException

DB_NAME = "website_monitor.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS websites (
            id INTEGER PRIMARY KEY,
            url TEXT NOT NULL UNIQUE,
            title TEXT,
            uptime REAL,
            response_time REAL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_results (
            id INTEGER PRIMARY KEY,
            website_id INTEGER,
            uptime REAL,
            response_time REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (website_id) REFERENCES websites (id)
        )
    """)
    conn.commit()
    conn.close()

def get_or_create_website(url: str) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM websites WHERE url = ?", (url,))
    result = cursor.fetchone()
    if result:
        website_id = result[0]
    else:
        cursor.execute(
            "INSERT INTO websites (url, title, uptime, response_time) VALUES (?, ?, 0, 0)",
            (url, None)
        )
        website_id = cursor.lastrowid
        conn.commit()
    conn.close()
    return website_id

def extract_title(html: str) -> Optional[str]:
    match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None

def monitor_website(url: str, timeout: int, retries: int) -> Tuple[bool, float]:
    for attempt in range(retries):
        try:
            start_time = time.time()
            response = requests.get(url, timeout=timeout)
            response_time = time.time() - start_time
            is_up = response.status_code < 400
            title = extract_title(response.text) if is_up and response.text else None
            return is_up, response_time, title
        except RequestException:
            if attempt == retries - 1:
                return False, 0.0, None
            time.sleep(1)
    return False, 0.0, None

def apply_limit(website_id: int, limit: Optional[int]):
    if limit is None or limit <= 0:
        return
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM monitoring_results WHERE website_id = ?",
        (website_id,)
    )
    count = cursor.fetchone()[0]
    if count > limit:
        excess = count - limit
        cursor.execute(
            """DELETE FROM monitoring_results WHERE id IN (
                SELECT id FROM monitoring_results WHERE website_id = ?
                ORDER BY timestamp ASC LIMIT ?
            )""",
            (website_id, excess)
        )
        conn.commit()
    conn.close()

def log_result(website_id: int, is_up: bool, response_time: float, limit: Optional[int]):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO monitoring_results (website_id, uptime, response_time) VALUES (?, ?, ?)",
        (website_id, float(is_up), response_time)
    )
    conn.commit()
    apply_limit(website_id, limit)
    
    cursor.execute(
        """SELECT AVG(uptime), AVG(response_time) FROM monitoring_results WHERE website_id = ?""",
        (website_id,)
    )
    avg_uptime, avg_response = cursor.fetchone()
    avg_uptime = float(avg_uptime) if avg_uptime else 0.0
    avg_response = float(avg_response) if avg_response else 0.0
    
    cursor.execute(
        "UPDATE websites SET uptime = ?, response_time = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?",
        (avg_uptime, avg_response, website_id)
    )
    conn.commit()
    conn.close()

def monitor_worker(url: str, interval: int, timeout: int, retries: int, 
                   duration: Optional[int], limit: Optional[int], results_queue: Queue):
    end_time = time.time() + (duration * 60) if duration else float('inf')
    while time.time() < end_time:
        result = monitor_website(url, timeout, retries)
        results_queue.put((url, result[0], result[1], result[2], limit))
        time.sleep(interval * 60)

def process_results(results_queue: Queue, stop_event: threading.Event):
    while not stop_event.is_set() or not results_queue.empty():
        try:
            url, is_up, response_time, title, limit = results_queue.get(timeout=0.5)
            website_id = get_or_create_website(url)
            if title:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("UPDATE websites SET title = ? WHERE id = ?", (title, website_id))
                conn.commit()
                conn.close()
            log_result(website_id, is_up, response_time, limit)
            results_queue.task_done()
        except Exception:
            continue

def validate_positive_int(value: str) -> int:
    try:
        int_value = int(value)
        if int_value <= 0:
            raise argparse.ArgumentTypeError(f"{value} must be a positive integer")
        return int_value
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} is not a valid integer")

def parse_args():
    parser = argparse.ArgumentParser(description="Website Uptime and Response Time Monitor")
    parser.add_argument("--websites", nargs="+", required=True, help="Websites to monitor")
    parser.add_argument("--timeout", type=int, default=5, help="Request timeout in seconds (default: 5)")
    parser.add_argument("--interval", type=int, default=1, help="Monitoring interval in minutes (default: 1)")
    parser.add_argument("--retries", type=int, default=3, help="Number of retries before considering down (default: 3)")
    parser.add_argument("--duration", type=int, default=None, help="Duration of monitoring in minutes (default: indefinitely)")
    parser.add_argument("--limit", type=validate_positive_int, default=None, help="Max results to store per website")
    args = parser.parse_args()
    
    # Validate ranges
    if args.timeout <= 0:
        parser.error("--timeout must be a positive integer")
    if args.interval <= 0:
        parser.error("--interval must be a positive integer")
    if args.retries <= 0:
        parser.error("--retries must be a positive integer")
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be a positive integer")
    
    return args

def main():
    args = parse_args()
    init_db()
    
    results_queue = Queue()
    stop_event = threading.Event()
    
    # Start results processor thread
    processor = threading.Thread(target=process_results, args=(results_queue, stop_event))
    processor.start()
    
    # Start monitoring threads
    monitors = []
    for url in args.websites:
        thread = threading.Thread(
            target=monitor_worker,
            args=(url, args.interval, args.timeout, args.retries, 
                  args.duration, args.limit, results_queue)
        )
        thread.daemon = True
        thread.start()
        monitors.append(thread)
    
    # Wait for duration or indefinitely
    if args.duration:
        time.sleep(args.duration * 60)
        stop_event.set()
    else:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_event.set()
    
    # Wait for threads to finish
    processor.join(timeout=5)

if __name__ == "__main__":
    main()