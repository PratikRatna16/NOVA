#!/usr/bin/env python3
import argparse
import sqlite3
import time
import sys
import os
from datetime import datetime, date, timedelta

DB_PATH = os.path.expanduser("~/.pomodoro.db")
WORK_DURATION = 25 * 60  # 25 minutes in seconds
BREAK_DURATION = 5 * 60  # 5 minutes in seconds

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT,
        status TEXT DEFAULT 'active',
        paused_at INTEGER,
        total_worked INTEGER DEFAULT 0
    )""")
    conn.commit()
    return conn

def get_active_session(conn):
    cursor = conn.execute("SELECT * FROM sessions WHERE status = 'active' ORDER BY id DESC LIMIT 1")
    return cursor.fetchone()

def start_session(conn, task):
    if get_active_session(conn):
        print("Error: Active session already exists. Complete or reset it first.")
        return False
    now = datetime.now().isoformat()
    conn.execute("INSERT INTO sessions (task, start_time) VALUES (?, ?)", (task, now))
    conn.commit()
    return True

def complete_session(conn, session_id, worked_seconds):
    now = datetime.now().isoformat()
    conn.execute("UPDATE sessions SET end_time = ?, status = 'completed', total_worked = ? WHERE id = ?",
                 (now, worked_seconds, session_id))
    conn.commit()

def pause_session(conn, session_id, elapsed):
    conn.execute("UPDATE sessions SET paused_at = ?, total_worked = ? WHERE id = ?",
                 (int(time.time()), elapsed, session_id))
    conn.commit()

def resume_session(conn, session_id, paused_at, total_worked):
    conn.execute("UPDATE sessions SET paused_at = NULL WHERE id = ?", (session_id,))

def reset_session(conn, session_id):
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()

def format_time(seconds):
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

def run_timer(conn, session_id, task, total_duration, is_break=False):
    session = conn.execute("SELECT paused_at, total_worked FROM sessions WHERE id = ?", (session_id,)).fetchone()
    paused_at = session[0] if session[0] else None
    worked = session[1] or 0
    
    if paused_at and not is_break:
        worked += int(time.time()) - paused_at
        conn.execute("UPDATE sessions SET total_worked = ?, paused_at = NULL WHERE id = ?", (worked, session_id))
        conn.commit()
    
    start_time = time.time()
    while worked < total_duration:
        remaining = total_duration - worked - (time.time() - start_time)
        if remaining <= 0:
            break
        print(f"\r{'BREAK' if is_break else 'WORK'}: {task} - {format_time(remaining)} remaining", end="", flush=True)
        time.sleep(1)
        
        try:
            import select
            if select.select([sys.stdin], [], [], 0.0)[0]:
                cmd = sys.stdin.read(1).strip().lower()
                if cmd == 'p':
                    pause_session(conn, session_id, int(total_duration - worked - (time.time() - start_time)))
                    print("\nPaused. Press Enter to resume, 'r' to reset...")
                    action = input().strip().lower()
                    if action == 'r':
                        reset_session(conn, session_id)
                        return
                    resume_session(conn, session_id, None, None)
                    return run_timer(conn, session_id, task, total_duration, is_break)
                elif cmd == 'r':
                    reset_session(conn, session_id)
                    return
        except:
            pass
    
    print(f"\r{'BREAK' if is_break else 'WORK'}: {task} - Completed! {'🎉' if not is_break else '⏰'}")

def generate_report(conn, report_date=None):
    target_date = report_date or date.today().isoformat()
    sessions = conn.execute("""SELECT task, total_worked, start_time, end_time FROM sessions 
                              WHERE date(start_time) = ?""", (target_date,)).fetchall()
    
    if not sessions:
        print(f"No sessions found for {target_date}")
        return
    
    total_sessions = len(sessions)
    total_time = sum(s[1] or 0 for s in sessions)
    tasks = sorted(set(s[0] for s in sessions))
    
    print(f"\n📊 Daily Productivity Report for {target_date}")
    print("=" * 40)
    print(f"Total Pomodoro sessions: {total_sessions}")
    print(f"Total time worked: {format_time(total_time)}")
    print(f"Tasks completed: {len(tasks)}")
    for task in tasks:
        task_sessions = sum(1 for s in sessions if s[0] == task)
        task_time = sum(s[1] or 0 for s in sessions if s[0] == task)
        print(f"  • {task}: {task_sessions} session(s), {format_time(task_time)}")

def main():
    parser = argparse.ArgumentParser(description="CLI Pomodoro Timer")
    parser.add_argument("command", choices=["start", "status", "report", "list", "reset"])
    parser.add_argument("--task", "-t", help="Task description for pomodoro session")
    parser.add_argument("--date", "-d", help="Date for report (YYYY-MM-DD)")
    args = parser.parse_args()
    
    conn = init_db()
    active = get_active_session(conn)
    
    if args.command == "start":
        if not args.task:
            print("Error: --task is required to start a session")
            sys.exit(1)
        if active:
            print(f"Error: Active session exists (task: {active[1]})")
            sys.exit(1)
        if start_session(conn, args.task):
            session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            print(f"🍅 Pomodoro started for: {args.task}")
            print("Press Ctrl+C to complete early, 'p' to pause, 'r' to reset")
            try:
                run_timer(conn, session_id, args.task, WORK_DURATION)
                run_timer(conn, session_id, args.task, BREAK_DURATION, is_break=True)
                complete_session(conn, session_id, WORK_DURATION)
            except KeyboardInterrupt:
                worked = int(time.time() - datetime.fromisoformat(
                    conn.execute("SELECT start_time FROM sessions WHERE id = ?", (session_id,)).fetchone()[0]).timestamp())
                worked = min(worked, WORK_DURATION)
                complete_session(conn, session_id, worked)
                print(f"\nSession completed early ({format_time(worked)} worked)")
    
    elif args.command == "status":
        if active:
            elapsed = int(time.time() - datetime.fromisoformat(active[2]).timestamp())
            print(f"Active session: {active[1]}")
            print(f"Started: {active[2]}")
            print(f"Elapsed: {format_time(elapsed)}")
        else:
            print("No active session")
    
    elif args.command == "report":
        generate_report(conn, args.date)
    
    elif args.command == "list":
        sessions = conn.execute("SELECT id, task, start_time, end_time, status FROM sessions ORDER BY id DESC LIMIT 10").fetchall()
        for s in sessions:
            end = s[3] or "in progress"
            print(f"#{s[0]}: {s[1]} ({s[2][:19]} - {end}) [{s[4]}]")
    
    elif args.command == "reset":
        if active:
            reset_session(conn, active[0])
            print("Session reset")
        else:
            print("No active session to reset")
    
    conn.close()

if __name__ == "__main__":
    main()