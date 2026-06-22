#!/usr/bin/env python3
"""CLI Log Monitor Tool - Monitors log files in real-time and alerts on error patterns."""

import argparse
import json
import re
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any


def load_config(config_path: str) -> dict[str, Any]:
    """Load and validate configuration from JSON file."""
    path = Path(config_path)
    if not path.exists():
        raise SystemExit(f"Configuration file not found: {config_path}")
    
    try:
        with open(path, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in configuration file: {e}")
    
    # Validate required configuration
    if 'log_file' not in config:
        raise SystemExit("Configuration error: 'log_file' is required")
    if not isinstance(config.get('error_patterns'), list):
        raise SystemExit("Configuration error: 'error_patterns' must be a list")
    
    config.setdefault('alert_settings', [])
    config.setdefault('alert_threshold', 1)
    config.setdefault('follow', True)
    
    return config


def compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    """Compile regex patterns with error handling."""
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error as e:
            raise SystemExit(f"Invalid regex pattern '{pattern}': {e}")
    return compiled


def send_email_alert(settings: dict[str, Any], subject: str, body: str) -> None:
    """Send email alert via SMTP."""
    msg = MIMEMultipart()
    msg['From'] = settings.get('from_address', settings.get('from'))
    msg['To'] = settings.get('to_address', settings.get('to'))
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    server_config = {
        'host': settings.get('smtp_server', settings.get('host')),
        'port': settings.get('smtp_port', settings.get('port', 587)),
        'username': settings.get('username'),
        'password': settings.get('password'),
        'use_tls': settings.get('use_tls', True),
    }
    
    try:
        server = smtplib.SMTP(server_config['host'], server_config['port'])
        if server_config['use_tls']:
            server.starttls()
        if server_config['username']:
            server.login(server_config['username'], server_config['password'])
        server.send_message(msg)
        server.quit()
        print(f"Email alert sent to {msg['To']}")
    except Exception as e:
        print(f"Failed to send email alert: {e}")


def send_console_alert(message: str) -> None:
    """Print alert message to console."""
    print(f"\n{'='*60}")
    print(f"ALERT: {message}")
    print(f"{'='*60}\n")


def check_line(line: str, patterns: list[re.Pattern]) -> list[str]:
    """Check a line against all patterns and return matched pattern strings."""
    matches = []
    for pattern in patterns:
        if pattern.search(line):
            matches.append(pattern.pattern)
    return matches


def monitor_log(config: dict[str, Any]) -> None:
    """Monitor log file in real-time and alert on matched patterns."""
    log_path = Path(config['log_file'])
    if not log_path.exists():
        raise SystemExit(f"Log file not found: {log_path}")
    
    patterns = compile_patterns(config['error_patterns'])
    alert_settings = config['alert_settings']
    threshold = config['alert_threshold']
    follow = config['follow']
    
    # Track counts and last alert time per pattern for throttling
    pattern_counts: dict[str, int] = {}
    last_alert_time: dict[str, float] = {}
    throttle_window = config.get('alert_throttle_seconds', 60)
    
    # Process existing content first if not following
    with open(log_path, 'r') as f:
        if not follow:
            for line in f:
                matches = check_line(line, patterns)
                for pattern_str in matches:
                    pattern_counts[pattern_str] = pattern_counts.get(pattern_str, 0) + 1
                    current_count = pattern_counts[pattern_str]
                    should_alert = current_count >= threshold
                    
                    if should_alert:
                        now = time.time()
                        time_since_last = now - last_alert_time.get(pattern_str, 0)
                        if time_since_last >= throttle_window:
                            last_alert_time[pattern_str] = now
                            trigger_alerts(alert_settings, pattern_str, line.strip(), current_count)
    
    if follow:
        print(f"Monitoring {log_path} for error patterns (Ctrl+C to stop)...")
        f = open(log_path, 'r')
        f.seek(0, 2)  # Go to end of file
        
        try:
            while True:
                line = f.readline()
                if line:
                    matches = check_line(line, patterns)
                    for pattern_str in matches:
                        pattern_counts[pattern_str] = pattern_counts.get(pattern_str, 0) + 1
                        current_count = pattern_counts[pattern_str]
                        should_alert = current_count >= threshold
                        
                        if should_alert:
                            now = time.time()
                            time_since_last = now - last_alert_time.get(pattern_str, 0)
                            if time_since_last >= throttle_window:
                                last_alert_time[pattern_str] = now
                                trigger_alerts(alert_settings, pattern_str, line.strip(), current_count)
                else:
                    # Check for file rotation
                    try:
                        if not log_path.exists() or log_path.stat().st_size < f.tell():
                            f.close()
                            f = open(log_path, 'r')
                            f.seek(0, 2)
                    except Exception:
                        pass
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
        finally:
            f.close()


def trigger_alerts(alert_settings: list[dict[str, Any]], pattern: str, 
                   line: str, count: int) -> None:
    """Trigger all configured alert mechanisms."""
    alert_handlers: dict[str, callable] = {
        'email': lambda a: send_email_alert(a, 
                             f"Log Error Alert: Pattern Matched",
                             f"Error pattern '{pattern}' matched {count} time(s).\nLine: {line}"),
        'console': lambda a: send_console_alert(
                             f"Pattern '{pattern}' matched (occurrence #{count}): {line}")
    }
    
    for alert in alert_settings:
        alert_type = alert.get('type', '').lower()
        handler = alert_handlers.get(alert_type)
        if handler:
            handler(alert)
        else:
            print(f"Unknown alert type: {alert_type}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI Log Monitor Tool - Monitor logs and alert on error patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration file format (config.json):
{
    "log_file": "/path/to/logfile.log",
    "error_patterns": ["ERROR", "Exception", "Failed"],
    "alert_settings": [
        {"type": "console"},
        {"type": "email", "smtp_server": "smtp.example.com", "smtp_port": 587,
         "from": "alert@example.com", "to": "user@example.com", 
         "username": "user", "password": "pass"}
    ],
    "alert_threshold": 1,
    "alert_throttle_seconds": 60,
    "follow": true
}
""")
    parser.add_argument('--config', '-c', required=True, 
                        help='Path to JSON configuration file')
    parser.add_argument('--validate', '-v', action='store_true',
                        help='Validate configuration file without starting monitor')
    
    args = parser.parse_args()
    
    try:
        config = load_config(args.config)
    except SystemExit as e:
        if args.validate:
            raise
        return
    
    if args.validate:
        patterns = compile_patterns(config['error_patterns'])
        print(f"Configuration valid. Monitoring: {config['log_file']}")
        print(f"Patterns: {[p.pattern for p in patterns]}")
        print(f"Alert settings: {len(config['alert_settings'])} configured")
        return
    
    if not config['alert_settings']:
        print("Warning: No alert settings configured. Use 'console' for basic output.")
    
    monitor_log(config)


if __name__ == "__main__":
    main()