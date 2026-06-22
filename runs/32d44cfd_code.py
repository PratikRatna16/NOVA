import argparse
import threading
import time
import sys
import os
import tempfile
import json
from pathlib import Path

try:
    import winsound
    HAS_WIN_SOUND = True
except ImportError:
    HAS_WIN_SOUND = False

timers = {}
lock = threading.Lock()

class Timer:
    def __init__(self, timer_id, duration_sec, alarm_file=None):
        self.timer_id = timer_id
        self.duration = duration_sec
        self.remaining = duration_sec
        self.alarm_file = alarm_file
        self.state = "INIT"
        self.last_tick = 0
        self.state_file = Path(tempfile.gettempdir()) / f"timer_{timer_id}.json"
        
    def save_state(self):
        data = {"state": self.state, "remaining": self.remaining}
        with open(self.state_file, 'w') as f:
            json.dump(data, f)
            
    def load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                self.state = data.get("state", "INIT")
                self.remaining = data.get("remaining", self.duration)
            except (json.JSONDecodeError, KeyError):
                pass
    
    def run(self):
        self.state = "RUNNING"
        self.save_state()
        start_time = time.time()
        
        while self.remaining > 0:
            if self.state == "PAUSED":
                time.sleep(0.1)
                continue
                
            elapsed = int(time.time() - start_time)
            self.remaining = max(0, self.duration - elapsed)
            
            mins, secs = divmod(self.remaining, 60)
            hours, mins = divmod(mins, 60)
            time_str = f"{hours:02}:{mins:02}:{secs:02}"
            print(f"Timer {self.timer_id}: {time_str}", end='\r')
            sys.stdout.flush()
            
            self.save_state()
            time.sleep(0.1)
            
        self.state = "ALARM"
        self.save_state()
        self.play_alarm()
        self.state = "EXIT"
        self.save_state()
        print(f"\nTimer {self.timer_id} finished!")
        self.cleanup()
        
    def play_alarm(self):
        if not self.alarm_file:
            print('\a', end='', file=sys.stderr)
            return
            
        alarm_path = Path(self.alarm_file)
        if not alarm_path.exists():
            print('\a', end='', file=sys.stderr)
            return
            
        try:
            if HAS_WIN_SOUND and os.name == "nt":
                winsound.PlaySound(str(alarm_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                os.system(f"afplay '{alarm_path}' 2>/dev/null || paplay '{alarm_path}' 2>/dev/null || aplay '{alarm_path}' 2>/dev/null &")
        except Exception:
            print('\a', end='', file=sys.stderr)
            
    def pause(self):
        if self.state == "RUNNING":
            self.state = "PAUSED"
            self.save_state()
            
    def resume(self):
        if self.state == "PAUSED":
            self.state = "RUNNING"
            self.save_state()
            
    def cleanup(self):
        with lock:
            if self.timer_id in timers:
                del timers[self.timer_id]
        if self.state_file.exists():
            self.state_file.unlink()

def get_or_create_timer(duration_sec, alarm_file):
    with lock:
        timer_id = len(timers) + 1
        timer = Timer(timer_id, duration_sec, alarm_file)
        timers[timer_id] = timer
    return timer_id, timer

def list_timers():
    with lock:
        if not timers:
            print("No active timers")
            return
        for tid, t in timers.items():
            mins, secs = divmod(t.remaining, 60)
            print(f"Timer {tid}: {t.state} - {mins:02}:{secs:02}")

def main():
    parser = argparse.ArgumentParser(description="CLI Countdown Timer")
    parser.add_argument("-d", "--duration", type=float, help="Duration in seconds")
    parser.add_argument("-m", "--minutes", type=float, help="Duration in minutes")
    parser.add_argument("-p", "--pause", type=int, help="Pause timer by ID")
    parser.add_argument("-r", "--resume", type=int, help="Resume timer by ID")
    parser.add_argument("-a", "--alarm", help="Alarm sound file path")
    parser.add_argument("-b", "--background", action="store_true", help="Run timer in background")
    parser.add_argument("-l", "--list", action="store_true", help="List active timers")
    
    args = parser.parse_args()
    
    if args.list:
        list_timers()
        return
        
    if args.pause or args.resume:
        if not args.pause and not args.resume:
            print("Error: Must provide timer ID to pause or resume")
            return
        timer_id = args.pause or args.resume
        state_file = Path(tempfile.gettempdir()) / f"timer_{timer_id}.json"
        if not state_file.exists():
            print(f"Error: Timer {timer_id} not found")
            return
        try:
            with open(state_file) as f:
                data = json.load(f)
            if args.pause:
                data["state"] = "PAUSED"
            else:
                data["state"] = "RUNNING"
            with open(state_file, 'w') as f:
                json.dump(data, f)
            print(f"Timer {timer_id} {'paused' if args.pause else 'resumed'}")
        except Exception as e:
            print(f"Error controlling timer: {e}")
        return
        
    if args.duration is None and args.minutes is None:
        print("Error: Must specify duration (-d) or minutes (-m)")
        return
        
    if args.duration and args.minutes:
        print("Error: Cannot specify both duration and minutes")
        return
        
    if args.minutes:
        if args.minutes <= 0:
            print("Error: Minutes must be positive")
            return
        duration_sec = int(args.minutes * 60)
    else:
        if args.duration <= 0:
            print("Error: Duration must be positive")
            return
        duration_sec = int(args.duration)
        
    if args.alarm and not Path(args.alarm).exists():
        print(f"Warning: Alarm file '{args.alarm}' not found, will use beep")
        
    timer_id, timer = get_or_create_timer(duration_sec, args.alarm)
    
    if not args.background:
        timer.run()
    else:
        thread = threading.Thread(target=timer.run, daemon=True)
        thread.start()
        print(f"Timer {timer_id} started in background. Use -p {timer_id} to pause, -r {timer_id} to resume.")

if __name__ == "__main__":
    main()