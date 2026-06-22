#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

LOG_FILE = ".batch_rename_log.json"


class RenameResult(NamedTuple):
    original: str
    new: str
    success: bool
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch rename files using regex patterns with preview mode"
    )
    parser.add_argument("directory", help="Directory containing files to rename")
    parser.add_argument("pattern", help="Regex pattern to match")
    parser.add_argument("replacement", help="Replacement string")
    parser.add_argument("--preview", action="store_true", help="Show changes without applying")
    parser.add_argument("--dry-run", action="store_true", help="Simulate renaming without changes")
    parser.add_argument("files", nargs="*", help="Specific files to rename (optional)")
    return parser.parse_args()


def get_target_files(directory: Path, pattern: str, specific_files: list[str] | None = None) -> list[Path]:
    if specific_files:
        return [directory / f for f in specific_files if (directory / f).exists()]
    
    try:
        return [f for f in directory.iterdir() if f.is_file() and re.search(pattern, f.name)]
    except PermissionError:
        print(f"Error: Permission denied accessing {directory}")
        return []


def generate_new_name(filename: str, pattern: str, replacement: str) -> str | None:
    match = re.search(pattern, filename)
    if match:
        return re.sub(pattern, replacement, filename)
    return None


def rename_file(file_path: Path, pattern: str, replacement: str, dry_run: bool) -> RenameResult:
    new_name = generate_new_name(file_path.name, pattern, replacement)
    if not new_name:
        return RenameResult(file_path.name, file_path.name, False, "No match found")
    
    new_path = file_path.parent / new_name
    
    if dry_run:
        return RenameResult(file_path.name, new_name, True)
    
    try:
        file_path.rename(new_path)
        return RenameResult(file_path.name, new_name, True)
    except FileNotFoundError:
        return RenameResult(file_path.name, new_name, False, "File not found")
    except PermissionError:
        return RenameResult(file_path.name, new_name, False, "Permission denied")
    except OSError as e:
        return RenameResult(file_path.name, new_name, False, str(e))


def confirm_action(count: int) -> bool:
    response = input(f"\n{count} file(s) will be renamed. Continue? [y/N]: ").strip().lower()
    return response == 'y' or response == 'yes'


def write_log(results: list[RenameResult], directory: Path) -> None:
    log_path = directory / LOG_FILE
    log_entries = []
    
    if log_path.exists():
        try:
            with open(log_path, 'r') as f:
                log_entries = json.load(f)
        except (json.JSONDecodeError, PermissionError):
            log_entries = []
    
    for result in results:
        log_entries.append({
            "original": result.original,
            "new": result.new,
            "success": result.success,
            "error": result.error
        })
    
    try:
        with open(log_path, 'w') as f:
            json.dump(log_entries, f, indent=2)
    except PermissionError:
        print(f"Warning: Could not write log to {log_path}")


def display_results(results: list[RenameResult]) -> None:
    renamed = sum(1 for r in results if r.success)
    failed = len(results) - renamed
    
    for result in results:
        status = "✓" if result.success else "✗"
        print(f"{status} {result.original} → {result.new}")
        if result.error:
            print(f"  Error: {result.error}")
    
    print(f"\nSummary: {renamed} renamed, {failed} failed")


def main() -> int:
    args = parse_args()
    directory = Path(args.directory).resolve()
    
    if not directory.exists():
        print(f"Error: Directory '{directory}' does not exist")
        return 1
    
    if not directory.is_dir():
        print(f"Error: '{directory}' is not a directory")
        return 1
    
    target_files = get_target_files(directory, args.pattern, args.files or None)
    
    if not target_files:
        print("No files matched the pattern")
        return 0
    
    results = []
    successful_renames = []
    
    for file_path in target_files:
        result = rename_file(file_path, args.pattern, args.replacement, args.preview or args.dry_run)
        results.append(result)
        if result.success:
            successful_renames.append(result)
    
    if args.preview:
        print("Preview mode - no changes will be made:")
        for result in results:
            print(f"  {result.original} → {result.new}")
        return 0
    
    if successful_renames:
        if len(successful_renames) > 1:
            if not confirm_action(len(successful_renames)):
                print("Operation cancelled")
                results = [RenameResult(r.original, r.new, False, "Cancelled by user") for r in results]
            else:
                for file_path in target_files:
                    if generate_new_name(file_path.name, args.pattern, args.replacement):
                        try:
                            new_path = file_path.parent / generate_new_name(file_path.name, args.pattern, args.replacement)
                            file_path.rename(new_path)
                        except (OSError, PermissionError) as e:
                            for i, r in enumerate(results):
                                if r.original == file_path.name and r.success:
                                    results[i] = RenameResult(r.original, r.new, False, str(e))
                                    break
    
    display_results(results)
    write_log(results, directory)
    
    return 0 if all(r.success for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())