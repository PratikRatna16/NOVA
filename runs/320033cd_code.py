#!/usr/bin/env python3
"""CLI Countdown Timer with pause/resume and alarm sound functionality."""

import argparse
import sys
import threading
import time
from pathlib import Path
from typing import Optional

try:
    import playsound
    HAS_PLAYSOUND = True
except ImportError:
    HAS_PLAYSOUND = False

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False


class CountdownTimer:
    """Manages countdown timer with pause/resume functionality."""
    
    _instance: Optional['CountdownTimer'] = None
    _lock = threading.Lock()
    
    def __init__(self, duration: int = 0, sound_file: Optional[str] = None):
        self.duration = duration
        self.remaining = duration
        self.paused = False
        self.running = False
        self.sound_file = sound_file
        self._thread: Optional[threading.Thread] = None
        self._start_time: Optional[float] = None
        self._elapsed_before_pause: float = 0
    
    @classmethod
    def get_instance(cls) -> 'CountdownTimer':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @staticmethod
    def format_time(seconds: int) -> str:
        """Format seconds into HH:MM:SS display."""
        hours, remainder = divmod(max(0, seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _countdown(self):
        """Internal countdown loop running in separate thread."""
        self.running = True
        while self.remaining > 0 and self.running:
            if not self.paused:
                print(f"\r{self.format_time(self.remaining)} remaining", end="", flush=True)
                time.sleep(1)
                self.remaining -= 1
            else:
                time.sleep(0.1)
        
        if self.remaining <= 0 and self.running:
            print("\r" + " " * 30 + f"\r{self.format_time(0)} remaining", flush=True)
            print("\n⏰ Time's up!")
            self._play_alarm()
        self.running = False
    
    def start(self, duration: int, sound_file: Optional[str] = None) -> str:
        """Start or restart the countdown timer."""
        if duration <= 0:
            return "Error: Duration must be a positive integer."
        
        with self._lock:
            if self.running:
                self.running = False
                self._thread.join(timeout=2)
            
            self.duration = duration
            self.remaining = duration
            self.paused = False
            self._elapsed_before_pause = 0
            if sound_file:
                self.sound_file = sound_file
            
            self._thread = threading.Thread(target=self._countdown, daemon=True)
            self._thread.start()
        return f"Timer started for {self.format_time(self.duration)}"
    
    def pause(self) -> str:
        """Pause the countdown timer."""
        with self._lock:
            if self.running and not self.paused:
                self.paused = True
                return "Timer paused"
            elif not self.running:
                return "Error: No timer is running"
            return "Timer already paused"
    
    def resume(self) -> str:
        """Resume a paused countdown timer."""
        with self._lock:
            if self.running and self.paused:
                self.paused = False
                return f"Timer resumed - {self.format_time(self.remaining)} remaining"
            elif not self.running:
                return "Error: No timer is running"
            return "Timer not paused"
    
    def stop(self) -> str:
        """Stop the countdown timer."""
        with self._lock:
            if self.running:
                self.running = False
                self._thread.join(timeout=2)
                self.remaining = self.duration
                return "Timer stopped"
            return "No timer is running"
    
    def status(self) -> str:
        """Get current timer status."""
        if not self.running:
            return "No timer running"
        state = "paused" if self.paused else "running"
        return f"Timer {state} - {self.format_time(self.remaining)} remaining"
    
    def _play_alarm(self):
        """Play alarm sound in a separate thread."""
        threading.Thread(target=self._play_sound_internal, daemon=True).start()
    
    def _play_sound_internal(self):
        """Internal method to play sound with fallback options."""
        sound_file = self.sound_file
        
        # Try custom sound file first
        if sound_file and Path(sound_file).exists():
            try:
                if HAS_PLAYSOUND:
                    playsound.playsound(sound_file, block=False)
                    return
            except Exception:
                pass
        
        # Platform-specific fallback
        if HAS_WINSOUND:
            try:
                winsound.Beep(800, 1000)  # frequency, duration (ms)
                return
            except Exception:
                pass
        
        # Cross-platform fallback: print bell character
        print("\a", end="", flush=True)


def main():
    """Main entry point for CLI application."""
    parser = argparse.ArgumentParser(
        description="CLI Countdown Timer with pause/resume and alarm sound",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python countdown_timer.py -t 300      # 5-minute timer
  python countdown_timer.py -t 600 -s custom.wav  # With custom sound
  python countdown_timer.py -p          # Pause running timer
  python countdown_timer.py -r          # Resume paused timer
  python countdown_timer.py --status    # Show timer status
  python countdown_timer.py --stop      # Stop the timer
        """
    )
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-t", "--time", type=int, help="Set countdown duration in seconds")
    group.add_argument("-p", "--pause", action="store_true", help="Pause the running timer")
    group.add_argument("-r", "--resume", action="store_true", help="Resume the paused timer")
    group.add_argument("--status", action="store_true", help="Show current timer status")
    group.add_argument("--stop", action="store_true", help="Stop the running timer")
    
    parser.add_argument("-s", "--sound", type=str, help="Custom alarm sound file (.wav)")
    
    args = parser.parse_args()
    timer = CountdownTimer.get_instance()
    
    commands = {
        args.time is not None: lambda: timer.start(args.time, args.sound),
        args.pause: timer.pause,
        args.resume: timer.resume,
        args.status: timer.status,
        args.stop: timer.stop,
    }
    
    # Execute the matching command (only one due to mutex group)
    for condition, action in commands.items():
        if condition:
            print(action())
            return
    
    # Default: interactive mode
    parser.print_help()


if __name__ == "__main__":
    try:
        main()
        # Keep process alive while timer is running
        timer = CountdownTimer.get_instance()
        while timer.running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)