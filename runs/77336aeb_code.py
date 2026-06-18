#!/usr/bin/env python3
"""CLI File Organizer - Watches directory, sorts files, handles duplicates, logs activity, supports undo."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    print("Warning: watchdog library not found. Using polling fallback. Install with: pip install watchdog", file=sys.stderr)

ACTIVITY_LOG_PATH = Path.home() / ".cli_organizer_activity.json"
UNDO_STACK_PATH = Path.home() / ".cli_organizer_undo.json"


def compute_md5(file_path: Path) -> Optional[str]:
    """Compute MD5 hash of file. Returns None on error."""
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except (OSError, IOError):
        return None


def load_json(path: Path, default):
    """Load JSON file or return default."""
    try:
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return default


def save_json(path: Path, data) -> None:
    """Save data to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_file_category(file_path: Path) -> str:
    """Determine file category based on extension."""
    ext = file_path.suffix.lower()
    categories = {
        ".doc": "documents", ".docx": "documents", ".pdf": "documents",
        ".txt": "documents", ".rtf": "documents", ".odt": "documents",
        ".xls": "documents", ".xlsx": "documents", ".ppt": "documents", ".pptx": "documents",
        ".jpg": "images", ".jpeg": "images", ".png": "images", ".gif": "images", ".bmp": "images", ".tiff": "images",
        ".mp3": "audio", ".wav": "audio", ".flac": "audio", ".aac": "audio", ".ogg": "audio",
        ".mp4": "video", ".avi": "video", ".mkv": "video", ".mov": "video", ".wmv": "video",
        ".zip": "archives", ".tar": "archives", ".gz": "archives", ".rar": "archives", ".7z": "archives",
        ".py": "code", ".js": "code", ".html": "code", ".css": "code", ".java": "code", ".cpp": "code", ".c": "code",
        ".exe": "programs", ".dmg": "programs", ".app": "programs", ".sh": "programs",
    }
    return categories.get(ext, "others")


def generate_unique_destination(dest_path: Path) -> Path:
    """Generate unique destination path by adding suffix if needed."""
    counter = 1
    final_path = dest_path
    while final_path.exists():
        stem = dest_path.stem
        suffix = dest_path.suffix
        final_path = dest_path.parent / f"{stem}_{counter}{suffix}"
        counter += 1
    return final_path


class FileOrganizerHandler(FileSystemEventHandler):
    """Handles file creation events and organizes files."""

    def __init__(self, watch_dir: Path, log_path: Path, undo_path: Path, handle_duplicates: bool = True):
        self.watch_dir = watch_dir.resolve()
        self.log_path = log_path
        self.undo_path = undo_path
        self.handle_duplicates = handle_duplicates
        self.activity_log = load_json(log_path, [])

    def on_created(self, event):
        if not isinstance(event, FileCreatedEvent):
            return
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        # Wait briefly for file to be fully written
        time.sleep(0.1)
        
        if not file_path.exists() or file_path.is_dir():
            return
            
        try:
            self.organize_file(file_path)
        except Exception as e:
            print(f"Error organizing {file_path}: {e}", file=sys.stderr)

    def organize_file(self, file_path: Path) -> None:
        """Organize a single file into appropriate subfolder."""
        if self.handle_duplicates:
            existing_dest = self.find_duplicate(file_path)
            if existing_dest:
                self._handle_duplicate_as_delete(file_path, existing_dest)
                return

        category = get_file_category(file_path)
        today = datetime.now().strftime("%Y-%m-%d")
        dest_dir = self.watch_dir / category / today

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = generate_unique_destination(dest_dir / file_path.name)

        shutil.move(str(file_path), str(dest_path))
        
        file_hash = compute_md5(dest_path)
        
        operation = {
            "timestamp": datetime.now().isoformat(),
            "operation": "move",
            "source": str(file_path),
            "destination": str(dest_path),
            "hash": file_hash
        }
        
        self.activity_log.append(operation)
        save_json(self.log_path, self.activity_log)
        
        undo_entry = {"operation": "move", "source": str(dest_path), "destination": str(file_path)}
        undo_stack = load_json(self.undo_path, [])
        undo_stack.append(undo_entry)
        save_json(self.undo_path, undo_stack)
        
        print(f"Moved: {file_path.name} -> {dest_path}")

    def find_duplicate(self, file_path: Path) -> Optional[Path]:
        """Find duplicate file in organized folders."""
        file_hash = compute_md5(file_path)
        if not file_hash:
            return None

        for log_entry in self.activity_log:
            if log_entry.get("hash") == file_hash:
                dest = Path(log_entry.get("destination", ""))
                if dest.exists():
                    return dest
        return None

    def _handle_duplicate_as_delete(self, file_path: Path, existing: Path) -> None:
        """Handle duplicate by deleting the new file."""
        file_path.unlink()
        operation = {
            "timestamp": datetime.now().isoformat(),
            "operation": "delete_duplicate",
            "source": str(file_path),
            "duplicate_of": str(existing)
        }
        self.activity_log.append(operation)
        save_json(self.log_path, self.activity_log)
        print(f"Deleted duplicate: {file_path.name} (duplicate of {existing.name})")


def undo_last_operation(undo_path: Path, log_path: Path) -> bool:
    """Undo the last file operation. Returns True if successful."""
    undo_stack = load_json(undo_path, [])
    activity_log = load_json(log_path, [])
    
    if not undo_stack:
        print("No operations to undo.")
        return False

    last_op = undo_stack.pop()
    src = Path(last_op["source"])
    dst = Path(last_op["destination"])

    try:
        if last_op["operation"] == "move":
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                print(f"Undone: moved {src} back to {dst}")
            else:
                print(f"Cannot undo: source {src} no longer exists")
                undo_stack.append(last_op)
                save_json(undo_path, undo_stack)
                return False
        else:
            print(f"Unknown operation type: {last_op['operation']}")
            undo_stack.append(last_op)
            save_json(undo_path, undo_stack)
            return False
            
        save_json(undo_path, undo_stack)
        
        # Remove corresponding log entry
        if activity_log:
            activity_log.pop()
            save_json(log_path, activity_log)
            
        return True
    except (OSError, shutil.Error) as e:
        print(f"Error during undo: {e}", file=sys.stderr)
        undo_stack.append(last_op)
        save_json(undo_path, undo_stack)
        return False


def watch_with_polling(directory: Path, handle_duplicates: bool, stop_event=None) -> None:
    """Poll directory for new files when watchdog is unavailable."""
    seen_files = set()
    log_path = ACTIVITY_LOG_PATH
    undo_path = UNDO_STACK_PATH
    handler = FileOrganizerHandler(directory, log_path, undo_path, handle_duplicates)
    
    while stop_event is None or not stop_event.is_set():
        try:
            for item in directory.iterdir():
                if item.is_file() and item.name not in seen_files:
                    seen_files.add(item.name)
                    handler.organize_file(item)
        except Exception as e:
            print(f"Polling error: {e}", file=sys.stderr)
        
        time.sleep(2)


def start_watching(directory: str, handle_duplicates: bool = True) -> None:
    """Start watching directory for new files."""
    watch_path = Path(directory).resolve()
    if not watch_path.exists():
        print(f"Error: Directory {watch_path} does not exist.", file=sys.stderr)
        sys.exit(1)
    if not watch_path.is_dir():
        print(f"Error: {watch_path} is not a directory.", file=sys.stderr)
        sys.exit(1)

    print(f"Watching directory: {watch_path}")
    print("Press Ctrl+C to stop...")

    try:
        if WATCHDOG_AVAILABLE:
            event_handler = FileOrganizerHandler(watch_path, ACTIVITY_LOG_PATH, UNDO_STACK_PATH, handle_duplicates)
            observer = Observer()
            observer.schedule(event_handler, str(watch_path), recursive=False)
            observer.start()
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
                print("\nStopped watching.")
            observer.join()
        else:
            import threading
            stop_event = threading.Event()
            watch_thread = threading.Thread(target=watch_with_polling, args=(watch_path, handle_duplicates, stop_event))
            watch_thread.daemon = True
            watch_thread.start()
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                stop_event.set()
                print("\nStopped watching.")
                watch_thread.join(timeout=5)
    except Exception as e:
        print(f"Watch error: {e}", file=sys.stderr)
        if not WATCHDOG_AVAILABLE:
            print("Try installing watchdog for better performance: pip install watchdog")


def show_activity_log(log_path: Path) -> None:
    """Display the activity log."""
    log = load_json(log_path, [])
    if not log:
        print("Activity log is empty.")
        return
    
    print(f"\nActivity Log ({len(log)} entries):")
    print("-" * 60)
    for entry in reversed(log):
        ts = entry.get("timestamp", "unknown")
        op = entry.get("operation", "unknown")
        src = entry.get("source", "unknown")
        dst = entry.get("destination", "unknown")
        dup = entry.get("duplicate_of", "")
        print(f"[{ts}] {op}: {src} -> {dst}{f' (duplicate of {dup})' if dup else ''}")


def process_existing_files(directory: str, handle_duplicates: bool = True) -> None:
    """Process existing files in directory (one-time sort)."""
    watch_path = Path(directory).resolve()
    if not watch_path.exists() or not watch_path.is_dir():
        print(f"Error: Invalid directory {watch_path}", file=sys.stderr)
        sys.exit(1)

    handler = FileOrganizerHandler(watch_path, ACTIVITY_LOG_PATH, UNDO_STACK_PATH, handle_duplicates)
    
    print(f"Processing existing files in: {watch_path}")
    for item in watch_path.iterdir():
        if item.is_file():
            try:
                handler.organize_file(item)
            except Exception as e:
                print(f"Error processing {item}: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="CLI File Organizer - Watch and sort files by type/date",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s watch /path/to/directory     Watch directory for new files
  %(prog)s sort /path/to/directory      Sort existing files once
  %(prog)s undo                         Undo last operation
  %(prog)s log                          Show activity log
  %(prog)s watch ~/Downloads --no-dupes Skip duplicate detection
"""
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Watch command
    watch_parser = subparsers.add_parser("watch", help="Watch directory for new files")
    watch_parser.add_argument("directory", help="Directory to watch")
    watch_parser.add_argument("--no-dupes", action="store_true", help="Skip duplicate detection")

    # Sort command
    sort_parser = subparsers.add_parser("sort", help="Sort existing files once")
    sort_parser.add_argument("directory", help="Directory to process")
    sort_parser.add_argument("--no-dupes", action="store_true", help="Skip duplicate detection")

    # Undo command
    subparsers.add_parser("undo", help="Undo last file operation")

    # Log command
    subparsers.add_parser("log", help="Show activity log")

    args = parser.parse_args()

    commands: dict[str, Callable[[], None]] = {
        "watch": lambda: start_watching(args.directory, not args.no_dupes),
        "sort": lambda: process_existing_files(args.directory, not args.no_dupes),
        "undo": lambda: undo_last_operation(UNDO_STACK_PATH, ACTIVITY_LOG_PATH) or None,
        "log": lambda: show_activity_log(ACTIVITY_LOG_PATH),
    }

    if args.command not in commands:
        parser.print_help()
        sys.exit(1)

    commands[args.command]()


if __name__ == "__main__":
    main()