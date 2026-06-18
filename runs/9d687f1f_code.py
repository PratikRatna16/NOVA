#!/usr/bin/env python3
"""CLI File Organizer - Watches directories and sorts files by type and date."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


ACTIVITY_LOG_PATH = Path.home() / ".file_organizer_activity.json"
SUPPORTED_TYPES = {
    '.txt': 'documents', '.pdf': 'documents', '.doc': 'documents', '.docx': 'documents',
    '.jpg': 'images', '.jpeg': 'images', '.png': 'images', '.gif': 'images', '.bmp': 'images',
    '.mp3': 'audio', '.wav': 'audio', '.flac': 'audio', '.aac': 'audio',
    '.mp4': 'video', '.avi': 'video', '.mkv': 'video', '.mov': 'video',
    '.zip': 'archives', '.rar': 'archives', '.7z': 'archives', '.tar': 'archives', '.gz': 'archives',
    '.py': 'code', '.js': 'code', '.html': 'code', '.css': 'code', '.json': 'code',
    '.xls': 'spreadsheets', '.xlsx': 'spreadsheets', '.csv': 'spreadsheets',
}


def calculate_md5(file_path: Path) -> str:
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def load_activity_log() -> list[dict]:
    """Load the activity log from disk."""
    if ACTIVITY_LOG_PATH.exists():
        with open(ACTIVITY_LOG_PATH, "r") as f:
            return json.load(f)
    return []


def save_activity_log(log: list[dict]) -> None:
    """Save the activity log to disk."""
    with open(ACTIVITY_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def get_file_category(file_path: Path) -> str:
    """Determine the category/folder for a file based on extension."""
    ext = file_path.suffix.lower()
    return SUPPORTED_TYPES.get(ext, "other")


def get_date_folder() -> str:
    """Get current date folder name (YYYY-MM-DD format)."""
    return datetime.now().strftime("%Y-%m-%d")


def is_duplicate(dest_file: Path, current_hash: str) -> bool:
    """Check if a file with same hash already exists in destination."""
    if not dest_file.exists():
        return False
    try:
        existing_hash = calculate_md5(dest_file)
        return existing_hash == current_hash
    except (OSError, IOError):
        return False


def process_file(file_path: Path, watch_dir: Path, dry_run: bool = False) -> Optional[dict]:
    """Process a single file: calculate hash, determine destination, move file."""
    try:
        if not file_path.is_file():
            return None
        
        file_hash = calculate_md5(file_path)
        category = get_file_category(file_path)
        date_folder = get_date_folder()
        dest_dir = watch_dir / category / date_folder
        
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / file_path.name
        
        if is_duplicate(dest_file, file_hash):
            if dry_run:
                print(f"[DRY-RUN] Duplicate detected: {file_path.name}")
                return {"action": "skipped", "file": file_path.name, "reason": "duplicate"}
            file_path.unlink()
            return {"action": "deleted", "file": file_path.name, "reason": "duplicate"}
        
        if dry_run:
            print(f"[DRY-RUN] Would move: {file_path} -> {dest_file}")
            return {"action": "moved", "file": file_path.name, "source": str(file_path), "dest": str(dest_file), "dry_run": True}
        
        shutil.move(str(file_path), str(dest_file))
        return {
            "action": "moved",
            "file": file_path.name,
            "source": str(file_path),
            "dest": str(dest_file),
            "timestamp": datetime.now().isoformat(),
            "hash": file_hash
        }
    except (OSError, IOError, shutil.Error) as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return {"action": "error", "file": file_path.name, "error": str(e)}


def sort_directory(directory: Path, dry_run: bool = False) -> list[dict]:
    """Sort all existing files in a directory."""
    results = []
    if not directory.exists():
        print(f"Directory does not exist: {directory}", file=sys.stderr)
        return results
    
    for item in directory.iterdir():
        if item.is_file() and item.name != ACTIVITY_LOG_PATH.name:
            result = process_file(item, directory, dry_run)
            if result:
                results.append(result)
    return results


def undo_last_operation() -> bool:
    """Undo the last file operation."""
    log = load_activity_log()
    if not log:
        print("No operations to undo.")
        return False
    
    last_op = log.pop()
    save_activity_log(log)
    
    if last_op.get("dry_run"):
        print("Last operation was a dry-run. No undo needed.")
        return True
    
    if last_op.get("action") == "deleted":
        print(f"Cannot undo deletion of duplicate file: {last_op['file']}")
        return False
    
    try:
        dest = Path(last_op["dest"])
        source = Path(last_op["source"])
        if dest.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(source))
            print(f"Undid move: {dest} -> {source}")
            return True
        else:
            print(f"Destination file no longer exists: {dest}")
            return False
    except (OSError, IOError, shutil.Error) as e:
        print(f"Undo failed: {e}", file=sys.stderr)
        return False


def start_watcher(directory: Path, dry_run: bool = False) -> None:
    """Start watching a directory for new files."""
    if not WATCHDOG_AVAILABLE:
        print("watchdog package not installed. Installing...")
        os.system("pip install watchdog")
        print("Please run the command again after installation.")
        return
    
    if not directory.exists():
        print(f"Directory does not exist: {directory}", file=sys.stderr)
        return
    
    class FileHandler(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory:
                time.sleep(0.1)  # Wait for file to be written
                file_path = Path(event.src_path)
                result = process_file(file_path, directory, dry_run)
                if result and not dry_run:
                    log = load_activity_log()
                    log.append(result)
                    save_activity_log(log)
    
    event_handler = FileHandler()
    observer = Observer()
    observer.schedule(event_handler, str(directory), recursive=False)
    observer.start()
    
    print(f"Watching directory: {directory}")
    print("Press Ctrl+C to stop...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def show_log(limit: int = 10) -> None:
    """Display the activity log."""
    log = load_activity_log()
    if not log:
        print("Activity log is empty.")
        return
    
    for entry in log[-limit:]:
        print(json.dumps(entry, indent=2))


def main():
    parser = argparse.ArgumentParser(description="CLI File Organizer - Sort files by type and date")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Sort command
    sort_parser = subparsers.add_parser("sort", help="Sort existing files in a directory")
    sort_parser.add_argument("directory", type=Path, help="Directory to sort")
    sort_parser.add_argument("--dry-run", action="store_true", help="Show what would happen without moving")
    
    # Watch command
    watch_parser = subparsers.add_parser("watch", help="Watch a directory for new files")
    watch_parser.add_argument("directory", type=Path, help="Directory to watch")
    watch_parser.add_argument("--dry-run", action="store_true", help="Show what would happen without moving")
    
    # Undo command
    subparsers.add_parser("undo", help="Undo the last file operation")
    
    # Log command
    log_parser = subparsers.add_parser("log", help="Show activity log")
    log_parser.add_argument("--limit", type=int, default=10, help="Number of entries to show")
    
    # Sort and watch command
    sortwatch_parser = subparsers.add_parser("sort-watch", help="Sort existing files then watch for new ones")
    sortwatch_parser.add_argument("directory", type=Path, help="Directory to sort and watch")
    sortwatch_parser.add_argument("--dry-run", action="store_true", help="Show what would happen without moving")
    
    args = parser.parse_args()
    
    if args.command == "sort":
        results = sort_directory(args.directory, args.dry_run)
        if not args.dry_run:
            log = load_activity_log()
            log.extend([r for r in results if r.get("action") == "moved"])
            save_activity_log(log)
        print(f"Processed {len(results)} files")
    elif args.command == "watch":
        start_watcher(args.directory, args.dry_run)
    elif args.command == "undo":
        undo_last_operation()
    elif args.command == "log":
        show_log(args.limit)
    elif args.command == "sort-watch":
        results = sort_directory(args.directory, args.dry_run)
        if not args.dry_run:
            log = load_activity_log()
            log.extend([r for r in results if r.get("action") == "moved"])
            save_activity_log(log)
        print(f"Processed {len(results)} existing files")
        start_watcher(args.directory, args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()