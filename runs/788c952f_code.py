#!/usr/bin/env python3
import argparse
import re
import time
import sys
import os
import signal
import json
from pathlib import Path

LOCK_PATH = Path.home() / ".cli_timer.lock"
STATE_PATH = Path.home() / ".cli_timer.state"
MAX_SECONDS = 86400
MIN_SECONDS = 1

def parse_duration(value):
    match = re.match(r'^(\d+)(s|m|h)?$', str(value).lower())
    if not match:
        raise ValueError(f"Invalid duration format: {value}")
    num, unit = match.groups()
    multipliers = {'s': 1, 'm': 60, 'h': 3600}
    return int(num) * multipliers.get((unit or 's'), 1)

def validate(seconds):
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise ValueError(f"Duration must be {MIN_SECONDS}-{MAX_SECONDS} seconds (1 sec to 24 hrs)")
    return seconds

def play_alarm(alarm_type, custom_path=None):
    if alarm_type == "custom" and custom_path and Path(custom_path).exists():
        try:
            import subprocess
            subprocess.run(["afplay" if sys.platform == "darwin" else "aplay" if sys.platform.startswith("linux") else "start", str(custom_path)], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
    print(f"\a\a\a⏰ TIME'S UP! ⏰\a\a\a", flush=True)

def countdown(total_seconds, alarm_type, custom_path):
    try:
        while total_seconds > 0:
            hours, rem = divmod(total_seconds, 3600)
            mins, secs = divmod(rem, 60)
            print(f"\r⏳ {hours:02d}:{mins:02d}:{secs:02d}", end="", flush=True)
            time.sleep(1)
            total_seconds -= 1
        print()
        play_alarm(alarm_type, custom_path)
    finally:
        cleanup()

def cleanup():
    for p in [LOCK_PATH, STATE_PATH]:
        if p.exists():
            p.unlink()

def kill_timer():
    if not STATE_PATH.exists():
        print("ℹ️ No timer running")
        return
    try:
        state = json.loads(STATE_PATH.read_text())
        pid = state.get('pid')
        if pid:
            os.kill(pid, signal.SIGTERM)
            print(f"✅ Killed timer process {pid}")
    except (ProcessLookupError, ValueError, json.JSONDecodeError):
        print("ℹ️ No active timer found")
    finally:
        cleanup()

def start_background(total_seconds, alarm_type, custom_path):
    if LOCK_PATH.exists() or STATE_PATH.exists():
        print("⚠️ Timer already running in background")
        return
    
    # Write state for background process
    STATE_PATH.write_text(json.dumps({'pid': os.getpid(), 'seconds': total_seconds}))
    LOCK_PATH.touch()
    print(f"🚀 Timer started in background (PID: {os.getpid()})")
    print("💡 Use --kill to stop this timer")
    
    try:
        countdown(total_seconds, alarm_type, custom_path)
    except KeyboardInterrupt:
        cleanup()

def main():
    parser = argparse.ArgumentParser(description="CLI Countdown Timer with Background Mode")
    parser.add_argument('duration', nargs='?', help='Duration (e.g., 30, 1m, 2h)')
    parser.add_argument('-d', '--duration-arg', dest='dur', help='Duration explicitly')
    parser.add_argument('-u', '--unit', choices=['s', 'm', 'h'], default='s', help='Unit')
    parser.add_argument('-a', '--alarm', choices=['bell', 'custom'], default='bell', help='Alarm type')
    parser.add_argument('-b', '--background', action='store_true', help='Background mode')
    parser.add_argument('--sound', help='Custom alarm sound path')
    parser.add_argument('--kill', action='store_true', help='Kill background timer')
    
    args = parser.parse_args()
    
    if args.kill:
        kill_timer()
        return
    
    duration_input = args.dur or args.duration
    if not duration_input:
        parser.error("Duration required")
    
    try:
        seconds = validate(parse_duration(duration_input))
    except ValueError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.background:
        start_background(seconds, args.alarm, args.sound)
    else:
        countdown(seconds, args.alarm, args.sound)

if __name__ == "__main__":
    main()