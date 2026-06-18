#!/usr/bin/env python3
"""Directory monitoring CLI tool that logs file changes with timestamps."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent
from watchdog.observers import Observer


class FileChangeHandler(FileSystemEventHandler):
    """Handler for file system events with logging capability."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def on_any_event(self, event):
        if event.is_directory:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        event_map = {
            'created': f"{event.src_path} - NEW",
            'modified': f"{event.src_path} - MODIFIED",
            'deleted': f"{event.src_path} - DELETED",
        }
        action = event_map.get(event.event_type)
        if action:
            self.logger.info(f"{timestamp} - {action}")


def setup_logging(log_file: Path) -> logging.Logger:
    """Configure logging to write to specified file."""
    logger = logging.getLogger('file_monitor')
    logger.setLevel(logging.INFO)
    logger.handlers = []
    handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
    return logger


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Monitor a directory for file changes and log them with timestamps.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Example: python cli_tool.py --directory /path/to/dir --log-file /path/to/log.log'
    )
    parser.add_argument(
        '--directory',
        required=True,
        type=Path,
        help='Directory to monitor for file changes'
    )
    parser.add_argument(
        '--log-file',
        required=True,
        type=Path,
        help='Log file to write file changes to'
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point for the CLI tool."""
    args = parse_args()
    
    if not args.directory.exists():
        print(f"Error: Directory '{args.directory}' does not exist.", file=sys.stderr)
        return 1
    if not args.directory.is_dir():
        print(f"Error: '{args.directory}' is not a directory.", file=sys.stderr)
        return 1
    
    try:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        args.log_file.touch(exist_ok=True)
    except PermissionError as e:
        print(f"Error: Cannot create/access log file '{args.log_file}': {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: Failed to create log file '{args.log_file}': {e}", file=sys.stderr)
        return 1
    
    logger = setup_logging(args.log_file)
    handler = FileChangeHandler(logger)
    observer = Observer()
    
    try:
        observer.schedule(handler, str(args.directory), recursive=False)
        observer.start()
        print(f"Monitoring '{args.directory}' - logging to '{args.log_file}' (Press Ctrl+C to stop)")
        
        while observer.is_alive():
            observer.join(1)
    except KeyboardInterrupt:
        print("\nStopping monitor...")
        observer.stop()
        observer.join()
        return 0
    except Exception as e:
        print(f"Error: Failed to start observer: {e}", file=sys.stderr)
        return 1
    finally:
        if observer.is_alive():
            observer.stop()


if __name__ == '__main__':
    sys.exit(main())